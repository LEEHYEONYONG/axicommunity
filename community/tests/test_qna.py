"""Q&A — 질문 · 답변 · 채택 · 삭제"""

from django.urls import reverse

from ..models import Notification, Post
from .base import CommunityTestCase


class QnaTestCase(CommunityTestCase):
    def setUp(self):
        self.question = self.make_post(self.qna, self.student, title="이력서 질문")
        self.detail_url = reverse("qna_detail", args=[self.question.post_id])

    def answer(self, writer, title="답변", **extra):
        return self.make_post(self.qna, writer, title=title, parent=self.question, **extra)

    def accept_url(self, answer):
        return reverse("qna_accept_answer", args=[self.question.post_id, answer.post_id])


class QnaAskTests(QnaTestCase):
    def test_수강생은_질문할_수_있다(self):
        self.client.force_login(self.student2)

        self.client.post(reverse("qna_ask"), {"title": "새 질문", "content": "내용"})

        question = Post.objects.get(title="새 질문")
        self.assertEqual(question.board, self.qna)
        self.assertIsNone(question.parent)

    def test_강사는_질문할_수_없다(self):
        self.client.force_login(self.teacher)

        response = self.client.post(reverse("qna_ask"), {"title": "새 질문", "content": "내용"})

        self.assertRedirects(response, reverse("qna_list"))
        self.assertFalse(Post.objects.filter(title="새 질문").exists())

    def test_목록은_질문_단위로_세고_답변은_그_아래에_붙인다(self):
        self.answer(self.mentor, title="남은 답변")
        self.answer(self.teacher, title="지운 답변").soft_delete()

        response = self.client.get(reverse("qna_list"))

        questions = list(response.context["page"])
        self.assertEqual(questions, [self.question])
        self.assertEqual(questions[0].answer_count, 1)
        self.assertEqual([a.title for a in questions[0].visible_answers], ["남은 답변"])

    def test_답변_내용으로도_질문을_찾는다(self):
        self.answer(self.mentor, title="답변", content="문제와 해결을 적으세요")
        self.make_post(self.qna, self.student2, title="무관한 질문")

        response = self.client.get(reverse("qna_list"), {"q": "문제와 해결"})

        self.assertEqual(list(response.context["page"]), [self.question])


class QnaAnswerTests(QnaTestCase):
    def setUp(self):
        super().setUp()
        self.answer_url = reverse("qna_answer", args=[self.question.post_id])

    def test_멘토와_강사는_답변할_수_있다(self):
        for member in (self.mentor, self.teacher):
            with self.subTest(member=member):
                self.client.force_login(member)

                self.client.post(self.answer_url, {"title": "답변", "content": "내용"})

                self.assertTrue(
                    Post.objects.filter(parent=self.question, writer=member).exists()
                )

    def test_수강생은_답변할_수_없다(self):
        self.client.force_login(self.student2)

        response = self.client.post(self.answer_url, {"title": "답변", "content": "내용"})

        self.assertRedirects(response, self.detail_url)
        self.assertEqual(self.question.answers.count(), 0)

    def test_답변이_달리면_질문자에게_알림이_간다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.answer_url, {"title": "답변", "content": "내용"})

        notification = Notification.objects.get(receiver=self.student)
        self.assertEqual(notification.kind, Notification.Kind.ANSWER)
        self.assertEqual(notification.link, self.detail_url)

    def test_한_질문에_한_사람이_두_번_답변할_수_없다(self):
        self.answer(self.mentor)
        self.client.force_login(self.mentor)

        response = self.client.post(self.answer_url, {"title": "또 답변", "content": "내용"})

        self.assertEqual(self.question.answers.count(), 1)
        self.assertIn("이미 이 질문에 답변", self.message_texts(response)[0])

    def test_지운_답변이_있으면_다시_답변할_수_있다(self):
        self.answer(self.mentor).soft_delete()
        self.client.force_login(self.mentor)

        self.client.post(self.answer_url, {"title": "다시 답변", "content": "내용"})

        self.assertEqual(self.question.answers.filter(is_deleted=False).count(), 1)

    def test_빈_답변은_조용히_넘어가지_않고_이유를_알려준다(self):
        self.client.force_login(self.mentor)

        response = self.client.post(self.answer_url, {"title": "제목만", "content": "  "})

        self.assertEqual(self.question.answers.count(), 0)
        self.assertIn("제목과 내용을 모두", self.message_texts(response)[0])

    def test_지운_질문에는_답변할_수_없다(self):
        self.question.soft_delete()
        self.client.force_login(self.mentor)

        response = self.client.post(self.answer_url, {"title": "답변", "content": "내용"})

        self.assertEqual(response.status_code, 404)


class QnaAcceptTests(QnaTestCase):
    def setUp(self):
        super().setUp()
        self.first = self.answer(self.mentor, title="첫 답변")
        self.second = self.answer(self.teacher, title="둘째 답변")

    def test_질문자가_채택하면_해결로_표시된다(self):
        self.client.force_login(self.student)

        self.client.post(self.accept_url(self.first))

        self.question.refresh_from_db()
        self.assertEqual(self.question.accepted_answer, self.first)

    def test_채택되면_답변자에게_알림이_간다(self):
        self.client.force_login(self.student)

        self.client.post(self.accept_url(self.first))

        self.assertTrue(
            Notification.objects.filter(receiver=self.mentor, message__contains="채택").exists()
        )

    def test_질문자가_아니면_채택할_수_없다(self):
        for member in (self.student2, self.mentor):
            with self.subTest(member=member):
                self.client.force_login(member)

                self.client.post(self.accept_url(self.first))

                self.question.refresh_from_db()
                self.assertIsNone(self.question.accepted_answer)

    def test_이미_채택했으면_다른_답변으로_바꿀_수_없다(self):
        self.client.force_login(self.student)
        self.client.post(self.accept_url(self.first))

        response = self.client.post(self.accept_url(self.second))

        self.question.refresh_from_db()
        self.assertEqual(self.question.accepted_answer, self.first)
        self.assertIn("이미 채택된 답변", self.message_texts(response)[-1])

    def test_다른_질문의_답변은_채택할_수_없다(self):
        other_question = self.make_post(self.qna, self.student2, title="다른 질문")
        other_answer = self.make_post(self.qna, self.mentor, parent=other_question)
        self.client.force_login(self.student)

        response = self.client.post(self.accept_url(other_answer))

        self.assertEqual(response.status_code, 404)

    def test_주소를_여는_것만으로는_채택되지_않는다(self):
        self.client.force_login(self.student)

        response = self.client.get(self.accept_url(self.first))

        self.assertEqual(response.status_code, 405)


class QnaDeleteTests(QnaTestCase):
    def setUp(self):
        super().setUp()
        self.mentor_answer = self.answer(self.mentor)

    def delete_answer_url(self, answer):
        return reverse("qna_delete_answer", args=[self.question.post_id, answer.post_id])

    def test_질문을_지우면_답변도_함께_지워진다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.detail_url, {"action": "delete"})

        self.assertRedirects(response, reverse("qna_list"))
        self.question.refresh_from_db()
        self.mentor_answer.refresh_from_db()
        self.assertTrue(self.question.is_deleted)
        self.assertTrue(self.mentor_answer.is_deleted)

    def test_질문자가_아니면_질문을_지울_수_없다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.detail_url, {"action": "delete"})

        self.question.refresh_from_db()
        self.assertFalse(self.question.is_deleted)

    def test_답변만_지우면_질문은_남는다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.delete_answer_url(self.mentor_answer))

        self.question.refresh_from_db()
        self.mentor_answer.refresh_from_db()
        self.assertTrue(self.mentor_answer.is_deleted)
        self.assertFalse(self.question.is_deleted)

    def test_남의_답변은_지울_수_없다(self):
        self.client.force_login(self.teacher)

        response = self.client.post(self.delete_answer_url(self.mentor_answer))

        self.assertEqual(response.status_code, 404)
        self.mentor_answer.refresh_from_db()
        self.assertFalse(self.mentor_answer.is_deleted)

    def test_채택된_답변은_지울_수_없다(self):
        self.question.accepted_answer = self.mentor_answer
        self.question.save()
        self.client.force_login(self.mentor)

        response = self.client.post(self.delete_answer_url(self.mentor_answer))

        self.mentor_answer.refresh_from_db()
        self.assertFalse(self.mentor_answer.is_deleted)
        self.assertIn("채택된 답변은 삭제할 수 없습니다", self.message_texts(response)[0])


class QnaDetailTests(QnaTestCase):
    def test_일반_상세_주소로_들어오면_qna_상세로_보낸다(self):
        response = self.client.get(reverse("post_detail", args=[self.question.post_id]))

        self.assertRedirects(response, self.detail_url)

    def test_답변_번호로_들어오면_원_질문으로_보낸다(self):
        answer = self.answer(self.mentor)

        response = self.client.get(reverse("post_detail", args=[answer.post_id]))

        self.assertRedirects(response, self.detail_url)

    def test_답변_번호로는_qna_상세를_열_수_없다(self):
        answer = self.answer(self.mentor)

        response = self.client.get(reverse("qna_detail", args=[answer.post_id]))

        self.assertEqual(response.status_code, 404)

    def test_조회수를_한_번만_센다(self):
        self.client.get(self.detail_url)
        self.client.get(self.detail_url)

        self.question.refresh_from_db()
        self.assertEqual(self.question.view_count, 1)

    def test_지운_답변은_화면에_나오지_않는다(self):
        self.answer(self.mentor, title="남은 답변")
        self.answer(self.teacher, title="지운 답변").soft_delete()

        response = self.client.get(self.detail_url)

        self.assertEqual([a.title for a in response.context["answers"]], ["남은 답변"])
