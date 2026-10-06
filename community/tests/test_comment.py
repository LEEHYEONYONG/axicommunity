"""댓글 · 대댓글"""

from django.urls import reverse

from ..models import Notification, PostComment
from ..views.post import visible_comments
from .base import CommunityTestCase


class CommentTestCase(CommunityTestCase):
    def setUp(self):
        self.post = self.make_post(self.free, self.student)
        self.create_url = reverse("comment_create", args=[self.post.post_id])

    def comment(self, writer, content="댓글", **extra):
        return PostComment.objects.create(
            post=self.post, writer=writer, content=content, **extra
        )


class CommentCreateTests(CommentTestCase):
    def test_댓글을_달면_글쓴이에게_알림이_간다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.create_url, {"content": "좋은 글이네요"})

        self.assertEqual(self.post.comments.get().writer, self.mentor)
        self.assertEqual(
            Notification.objects.get(receiver=self.student).kind, Notification.Kind.COMMENT
        )

    def test_내_글에_내가_단_댓글은_알림을_만들지_않는다(self):
        self.client.force_login(self.student)

        self.client.post(self.create_url, {"content": "덧붙입니다"})

        self.assertEqual(self.post.comments.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_공백만_있는_댓글은_등록되지_않는다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.create_url, {"content": "   "})

        self.assertEqual(self.post.comments.count(), 0)

    def test_비로그인은_댓글을_달_수_없다(self):
        response = self.client.post(self.create_url, {"content": "댓글"})

        self.assertRedirects(response, f"{reverse('login')}?next={self.create_url}")
        self.assertEqual(self.post.comments.count(), 0)

    def test_댓글을_막은_게시판에는_달_수_없다(self):
        question = self.make_post(self.qna, self.student)
        self.client.force_login(self.mentor)

        self.client.post(
            reverse("comment_create", args=[question.post_id]), {"content": "댓글"}
        )

        self.assertEqual(question.comments.count(), 0)

    def test_지운_글에는_댓글을_달_수_없다(self):
        self.post.soft_delete()
        self.client.force_login(self.mentor)

        response = self.client.post(self.create_url, {"content": "댓글"})

        self.assertEqual(response.status_code, 404)


class ReplyTests(CommentTestCase):
    def setUp(self):
        super().setUp()
        self.parent = self.comment(self.mentor, "원 댓글")

    def test_대댓글을_달면_원_댓글_작성자에게_알림이_간다(self):
        self.client.force_login(self.student)

        self.client.post(
            self.create_url, {"content": "답글", "parent_id": self.parent.comment_id}
        )

        self.assertEqual(self.parent.replies.get().content, "답글")
        self.assertTrue(Notification.objects.filter(receiver=self.mentor).exists())

    def test_대댓글에는_다시_답글을_달_수_없다(self):
        reply = self.comment(self.student, "답글", parent=self.parent)
        self.client.force_login(self.mentor)

        self.client.post(
            self.create_url, {"content": "답글의 답글", "parent_id": reply.comment_id}
        )

        self.assertFalse(PostComment.objects.filter(content="답글의 답글").exists())

    def test_다른_글의_댓글에는_답글을_달_수_없다(self):
        other_post = self.make_post(self.free, self.student2)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("comment_create", args=[other_post.post_id]),
            {"content": "답글", "parent_id": self.parent.comment_id},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_post.comments.count(), 0)


class CommentDeleteTests(CommentTestCase):
    def test_작성자가_지우면_지움_표시만_한다(self):
        comment = self.comment(self.mentor)
        self.client.force_login(self.mentor)

        self.client.post(reverse("comment_delete", args=[comment.comment_id]))

        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)

    def test_남의_댓글은_지우거나_고칠_수_없다(self):
        comment = self.comment(self.mentor, "원래 내용")
        self.client.force_login(self.student)

        self.client.post(reverse("comment_delete", args=[comment.comment_id]))
        self.client.post(
            reverse("comment_update", args=[comment.comment_id]), {"content": "바꿔치기"}
        )

        comment.refresh_from_db()
        self.assertFalse(comment.is_deleted)
        self.assertEqual(comment.content, "원래 내용")


class VisibleCommentsTests(CommentTestCase):
    def test_지운_댓글은_화면에서_빠진다(self):
        kept = self.comment(self.mentor, "남은 댓글")
        self.comment(self.mentor, "지운 댓글", is_deleted=True)

        self.assertEqual(visible_comments(self.post), [kept])

    def test_답글이_살아_있으면_지운_원_댓글도_자리를_남긴다(self):
        # 원 댓글을 목록에서 빼면 그 아래에 그려지는 답글까지 화면에서 사라집니다
        parent = self.comment(self.mentor, "지운 원 댓글", is_deleted=True)
        reply = self.comment(self.student, "남은 답글", parent=parent)

        self.assertEqual(visible_comments(self.post), [parent, reply])

    def test_답글까지_모두_지웠으면_원_댓글도_빠진다(self):
        parent = self.comment(self.mentor, "지운 원 댓글", is_deleted=True)
        self.comment(self.student, "지운 답글", parent=parent, is_deleted=True)

        self.assertEqual(visible_comments(self.post), [])

    def test_상세_화면의_댓글수는_살아_있는_댓글만_센다(self):
        parent = self.comment(self.mentor, "지운 원 댓글", is_deleted=True)
        self.comment(self.student, "남은 답글", parent=parent)

        response = self.client.get(reverse("post_detail", args=[self.post.post_id]))

        self.assertEqual(response.context["comment_count"], 1)
