"""게시글 — 글쓰기 · 수정 · 삭제 · 첨부파일 · 조회수 · 추천"""

from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ..models import Attachment, Post, PostLike
from ..views.post import MAX_UPLOAD_SIZE
from .base import CommunityTestCase


def upload(name="학습계획표.csv", content=b"a,b,c"):
    return SimpleUploadedFile(name, content)


class PostCreateTests(CommunityTestCase):
    def write_url(self, board):
        return reverse("post_create", args=[board.board_id])

    def test_비로그인은_로그인_화면으로_보낸다(self):
        url = self.write_url(self.free)

        response = self.client.post(url, {"title": "제목", "content": "내용"})

        self.assertRedirects(response, f"{reverse('login')}?next={url}")
        self.assertEqual(Post.objects.count(), 0)

    def test_권한이_있으면_글이_등록된다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.write_url(self.free), {"title": " 제목 ", "content": "내용"})

        post = Post.objects.get()
        self.assertRedirects(response, reverse("post_detail", args=[post.post_id]))
        self.assertEqual(post.title, "제목")
        self.assertEqual(post.writer, self.student)
        self.assertEqual(post.board, self.free)

    def test_권한이_없으면_주소로_직접_들어와도_등록되지_않는다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.write_url(self.notice), {"title": "제목", "content": "내용"})

        self.assertRedirects(response, reverse("board_list", args=[self.notice.board_id]))
        self.assertEqual(Post.objects.count(), 0)
        self.assertIn("직원", self.message_texts(response)[0])

    def test_공백만_입력하면_등록되지_않고_입력값을_돌려준다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.write_url(self.free), {"title": "   ", "content": "쓰던 내용"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(response.context["content"], "쓰던 내용")

    def test_첨부파일이_함께_저장된다(self):
        self.client.force_login(self.student)

        self.client.post(
            self.write_url(self.free),
            {"title": "제목", "content": "내용", "files": [upload("a.csv"), upload("b.PDF")]},
        )

        post = Post.objects.get()
        self.assertCountEqual(
            post.attachments.values_list("origin_name", flat=True), ["a.csv", "b.PDF"]
        )
        self.assertEqual(post.attachments.first().file_size, 5)

    def test_허용하지_않는_확장자는_글까지_등록하지_않는다(self):
        self.client.force_login(self.student)

        for name in ("virus.exe", "shell.py", "확장자없음"):
            with self.subTest(name=name):
                response = self.client.post(
                    self.write_url(self.free),
                    {"title": "제목", "content": "내용", "files": [upload(name)]},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(Post.objects.count(), 0)
                self.assertEqual(Attachment.objects.count(), 0)

    def test_10MB_를_넘는_파일은_거부한다(self):
        self.client.force_login(self.student)
        too_big = upload("big.zip", b"0" * (MAX_UPLOAD_SIZE + 1))

        response = self.client.post(
            self.write_url(self.free),
            {"title": "제목", "content": "내용", "files": [too_big]},
        )

        self.assertEqual(Post.objects.count(), 0)
        self.assertIn("10MB", self.message_texts(response)[0])


class PostUpdateDeleteTests(CommunityTestCase):
    def setUp(self):
        self.post = self.make_post(self.free, self.student, title="원래 제목")
        self.detail_url = reverse("post_detail", args=[self.post.post_id])

    def test_작성자는_수정할_수_있다(self):
        self.client.force_login(self.student)

        self.client.post(
            reverse("post_update", args=[self.post.post_id]),
            {"title": "바뀐 제목", "content": "바뀐 내용"},
        )

        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "바뀐 제목")
        self.assertIsNotNone(self.post.updated_at)

    def test_남의_글은_수정할_수_없다(self):
        self.client.force_login(self.student2)

        response = self.client.post(
            reverse("post_update", args=[self.post.post_id]),
            {"title": "가로챈 제목", "content": "가로챈 내용"},
        )

        self.assertRedirects(response, self.detail_url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "원래 제목")

    def test_작성자가_지우면_지움_표시만_한다(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("post_delete", args=[self.post.post_id]))

        self.assertRedirects(response, reverse("board_list", args=[self.free.board_id]))
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_deleted)

    def test_남의_글은_지울_수_없다(self):
        self.client.force_login(self.student2)

        self.client.post(reverse("post_delete", args=[self.post.post_id]))

        self.post.refresh_from_db()
        self.assertFalse(self.post.is_deleted)

    def test_주소를_여는_것만으로는_지워지지_않는다(self):
        self.client.force_login(self.student)

        self.client.get(reverse("post_delete", args=[self.post.post_id]))

        self.post.refresh_from_db()
        self.assertFalse(self.post.is_deleted)

    def test_지운_글의_상세는_404(self):
        self.post.soft_delete()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 404)


class AttachmentTests(CommunityTestCase):
    def setUp(self):
        self.post = self.make_post(self.free, self.student)
        self.attachment = self.attach(self.post)

    def attach(self, post, name="자료.txt"):
        return Attachment.objects.create(
            post=post, origin_name=name, stored_path=upload(name, b"hello"), file_size=5
        )

    def test_원본_파일명으로_내려받는다(self):
        response = self.client.get(
            reverse("attachment_download", args=[self.attachment.attachment_id])
        )

        self.assertEqual(b"".join(response.streaming_content), b"hello")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_지운_글의_첨부는_주소를_알아도_받을_수_없다(self):
        self.post.soft_delete()

        response = self.client.get(
            reverse("attachment_download", args=[self.attachment.attachment_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_디스크에_파일이_없으면_오류_대신_안내한다(self):
        Path(self.attachment.stored_path.path).unlink()

        with self.assertLogs("community.views.post", level="WARNING"):
            response = self.client.get(
                reverse("attachment_download", args=[self.attachment.attachment_id])
            )

        self.assertRedirects(response, reverse("post_detail", args=[self.post.post_id]))
        self.assertIn("파일을 찾을 수 없습니다", self.message_texts(response)[0])

    def test_수정에서_첨부를_지우면_디스크_파일도_지운다(self):
        path = Path(self.attachment.stored_path.path)
        self.assertTrue(path.exists())
        self.client.force_login(self.student)

        self.client.post(
            reverse("post_update", args=[self.post.post_id]),
            {"title": "제목", "content": "내용", "delete_files": [self.attachment.attachment_id]},
        )

        self.assertFalse(Attachment.objects.filter(pk=self.attachment.pk).exists())
        self.assertFalse(path.exists())

    def test_남의_글_첨부_번호를_넣어도_지워지지_않는다(self):
        others_post = self.make_post(self.free, self.student2)
        others_file = self.attach(others_post, "남의자료.txt")
        self.client.force_login(self.student)

        self.client.post(
            reverse("post_update", args=[self.post.post_id]),
            {"title": "제목", "content": "내용", "delete_files": [others_file.attachment_id]},
        )

        self.assertTrue(Attachment.objects.filter(pk=others_file.pk).exists())
        self.assertTrue(Path(others_file.stored_path.path).exists())

    def test_수정에서_새_첨부를_추가한다(self):
        self.client.force_login(self.student)

        self.client.post(
            reverse("post_update", args=[self.post.post_id]),
            {"title": "제목", "content": "내용", "files": [upload("추가.pdf")]},
        )

        self.assertEqual(self.post.attachments.count(), 2)


class ViewCountTests(CommunityTestCase):
    def setUp(self):
        self.post = self.make_post(self.free, self.student)
        self.url = reverse("post_detail", args=[self.post.post_id])

    def test_같은_브라우저에서는_한_번만_센다(self):
        self.client.get(self.url)
        self.client.get(self.url)

        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 1)

    def test_다른_브라우저는_따로_센다(self):
        self.client.get(self.url)
        self.client_class().get(self.url)

        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 2)


class PostLikeTests(CommunityTestCase):
    def setUp(self):
        self.post = self.make_post(self.free, self.student)
        self.url = reverse("post_like", args=[self.post.post_id])

    def test_누르면_추천되고_다시_누르면_취소된다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.url)
        self.assertEqual(PostLike.objects.filter(post=self.post).count(), 1)

        self.client.post(self.url)
        self.assertEqual(PostLike.objects.filter(post=self.post).count(), 0)

    def test_내_글은_추천할_수_없다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.url)

        self.assertEqual(PostLike.objects.count(), 0)
        self.assertIn("본인이 작성한 글", self.message_texts(response)[0])

    def test_주소를_여는_것만으로는_추천되지_않는다(self):
        self.client.force_login(self.mentor)

        self.client.get(self.url)

        self.assertEqual(PostLike.objects.count(), 0)

    def test_지운_글은_추천할_수_없다(self):
        self.post.soft_delete()
        self.client.force_login(self.mentor)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(PostLike.objects.count(), 0)
