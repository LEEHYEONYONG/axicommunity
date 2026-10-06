"""게시판 목록 — 검색 · 정렬 · 페이지 나누기 · 익명 게시판"""

from django.urls import reverse

from ..models import PostLike
from .base import CommunityTestCase


class BoardListTests(CommunityTestCase):
    def list_url(self, board):
        return reverse("board_list", args=[board.board_id])

    def titles(self, response):
        return [p.title for p in response.context["page"]]

    def test_삭제된_글은_목록에_나오지_않는다(self):
        self.make_post(self.free, self.student, title="남은 글")
        self.make_post(self.free, self.student, title="지운 글", is_deleted=True)

        response = self.client.get(self.list_url(self.free))

        self.assertEqual(self.titles(response), ["남은 글"])

    def test_다른_게시판_글은_섞이지_않는다(self):
        self.make_post(self.free, self.student, title="자유글")
        self.make_post(self.job, self.mentor, title="취업글")

        response = self.client.get(self.list_url(self.free))

        self.assertEqual(self.titles(response), ["자유글"])

    def test_qna_게시판은_전용_목록으로_보낸다(self):
        response = self.client.get(self.list_url(self.qna))

        self.assertRedirects(response, reverse("qna_list"))

    def test_없는_게시판은_404(self):
        response = self.client.get(reverse("board_list", args=[9999]))

        self.assertEqual(response.status_code, 404)

    def test_제목과_내용으로_검색한다(self):
        self.make_post(self.free, self.student, title="장고 질문", content="본문")
        self.make_post(self.free, self.student, title="점심", content="장고 얘기는 아님")
        self.make_post(self.free, self.student, title="무관", content="무관")

        response = self.client.get(self.list_url(self.free), {"q": "장고"})

        self.assertCountEqual(self.titles(response), ["장고 질문", "점심"])

    def test_작성자_이름으로_검색한다(self):
        self.make_post(self.free, self.student, title="한수강의 글")
        self.make_post(self.free, self.mentor, title="최멘토의 글")

        response = self.client.get(self.list_url(self.free), {"q": "최멘토", "type": "writer"})

        self.assertEqual(self.titles(response), ["최멘토의 글"])

    def test_한_쪽에_10개씩_나눈다(self):
        for i in range(13):
            self.make_post(self.free, self.student, title=f"글 {i}")

        first = self.client.get(self.list_url(self.free))
        second = self.client.get(self.list_url(self.free), {"page": 2})

        self.assertEqual(len(first.context["page"]), 10)
        self.assertEqual(len(second.context["page"]), 3)

    def test_추천순으로_정렬한다(self):
        self.make_post(self.free, self.student, title="추천 없음")
        liked = self.make_post(self.free, self.student, title="추천 둘")
        PostLike.objects.create(member=self.mentor, post=liked)
        PostLike.objects.create(member=self.teacher, post=liked)

        response = self.client.get(self.list_url(self.free), {"sort": "like"})

        self.assertEqual(self.titles(response), ["추천 둘", "추천 없음"])

    def test_조회순과_제목순으로_정렬한다(self):
        self.make_post(self.free, self.student, title="가", view_count=1)
        self.make_post(self.free, self.student, title="나", view_count=9)

        by_view = self.client.get(self.list_url(self.free), {"sort": "view"})
        by_title = self.client.get(self.list_url(self.free), {"sort": "title"})

        self.assertEqual(self.titles(by_view), ["나", "가"])
        self.assertEqual(self.titles(by_title), ["가", "나"])

    def test_모르는_정렬값은_최신순으로_돌린다(self):
        self.make_post(self.free, self.student)

        response = self.client.get(self.list_url(self.free), {"sort": "drop table"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort"], "new")

    def test_댓글수는_삭제된_댓글을_빼고_센다(self):
        post = self.make_post(self.free, self.student)
        post.comments.create(writer=self.mentor, content="남은 댓글")
        post.comments.create(writer=self.mentor, content="지운 댓글", is_deleted=True)

        response = self.client.get(self.list_url(self.free))

        self.assertEqual(response.context["page"][0].comment_count, 1)

    def test_권한이_없으면_글쓰기_대신_이유를_알려준다(self):
        self.client.force_login(self.student)

        response = self.client.get(self.list_url(self.notice))

        self.assertFalse(response.context["can_write"])
        self.assertIn("직원", response.context["denied_reason"])


class AnonymousBoardTests(CommunityTestCase):
    """멘토의 취업비밀 — 글쓴이가 어디에서도 드러나지 않아야 합니다"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.post = cls.make_post(cls.secret, cls.mentor, title="첫 회사 고르는 법")

    def test_목록에_글쓴이_이름과_아이디가_나오지_않는다(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("board_list", args=[self.secret.board_id]))

        self.assertContains(response, "첫 회사 고르는 법")
        self.assertNotContains(response, self.mentor.member_name)
        self.assertNotContains(response, self.mentor.username)

    def test_상세에_글쓴이_이름과_아이디가_나오지_않는다(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("post_detail", args=[self.post.post_id]))

        self.assertContains(response, "익명")
        self.assertNotContains(response, self.mentor.member_name)
        self.assertNotContains(response, self.mentor.username)

    def test_홈_화면에도_글쓴이_이름이_나오지_않는다(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "첫 회사 고르는 법")
        self.assertNotContains(response, self.mentor.member_name)

    def test_글쓴이_본인에게는_내_글임을_표시한다(self):
        self.client.force_login(self.mentor)

        response = self.client.get(reverse("post_detail", args=[self.post.post_id]))

        self.assertContains(response, "(나)")

    def test_작성자_검색은_서버에서_무시한다(self):
        # 이름으로 검색되면 '이 사람이 쓴 글'이 드러나 익명이 깨집니다
        response = self.client.get(
            reverse("board_list", args=[self.secret.board_id]),
            {"q": self.mentor.member_name, "type": "writer"},
        )

        self.assertEqual(response.context["search_type"], "all")
        self.assertEqual(len(response.context["page"]), 0)
