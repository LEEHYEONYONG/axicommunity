"""쪽지 — 보내기 · 읽음 · 삭제 · 발송 취소"""

from django.urls import reverse

from ..models import Message, Notification
from .base import CommunityTestCase


class MessageTestCase(CommunityTestCase):
    def send(self, sender, receiver, content="안녕하세요"):
        return Message.objects.create(sender=sender, receiver=receiver, content=content)

    def detail_url(self, message):
        return reverse("message_detail", args=[message.message_id])


class MessageSendTests(MessageTestCase):
    def setUp(self):
        self.url = reverse("message_send")
        self.client.force_login(self.student)

    def test_보내면_받는_사람에게_알림이_간다(self):
        self.client.post(self.url, {"receiver": self.mentor.username, "content": "질문 있습니다"})

        message = Message.objects.get()
        self.assertEqual((message.sender, message.receiver), (self.student, self.mentor))
        notification = Notification.objects.get(receiver=self.mentor)
        self.assertEqual(notification.link, self.detail_url(message))

    def test_나에게는_보낼_수_없다(self):
        response = self.client.post(self.url, {"receiver": self.student.username, "content": "메모"})

        self.assertEqual(Message.objects.count(), 0)
        self.assertIn("자기 자신에게는", self.message_texts(response)[0])

    def test_탈퇴한_회원에게는_보낼_수_없다(self):
        self.mentor2.is_active = False
        self.mentor2.save()

        self.client.post(self.url, {"receiver": self.mentor2.username, "content": "안녕하세요"})

        self.assertEqual(Message.objects.count(), 0)

    def test_내용이나_받는_사람이_비면_보내지_않는다(self):
        self.client.post(self.url, {"receiver": self.mentor.username, "content": "  "})
        self.client.post(self.url, {"receiver": "", "content": "내용"})

        self.assertEqual(Message.objects.count(), 0)

    def test_팝업에서는_없는_아이디를_404_대신_이유로_돌려준다(self):
        response = self.client.post(
            self.url,
            {"receiver": "no_such_user", "content": "안녕하세요"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"ok": False, "error": "그런 아이디의 회원이 없습니다."}
        )

    def test_팝업에서_연달아_두_번_보낼_수_있다(self):
        for content in ("첫 쪽지", "둘째 쪽지"):
            response = self.client.post(
                self.url,
                {"receiver": self.mentor.username, "content": content},
                headers={"x-requested-with": "XMLHttpRequest"},
            )
            self.assertEqual(response.json(), {"ok": True})

        self.assertEqual(Message.objects.count(), 2)


class MessageReadTests(MessageTestCase):
    def setUp(self):
        self.message = self.send(self.student, self.mentor)

    def test_받는_사람이_열면_읽음으로_바뀐다(self):
        self.client.force_login(self.mentor)

        self.client.get(self.detail_url(self.message))

        self.message.refresh_from_db()
        self.assertTrue(self.message.is_read)

    def test_보낸_사람이_열어도_읽음으로_바뀌지_않는다(self):
        self.client.force_login(self.student)

        self.client.get(self.detail_url(self.message))

        self.message.refresh_from_db()
        self.assertFalse(self.message.is_read)

    def test_남의_쪽지는_열어볼_수_없다(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.detail_url(self.message))

        self.assertRedirects(response, reverse("message_box"))
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_read)


class MessageDeleteTests(MessageTestCase):
    def setUp(self):
        self.message = self.send(self.student, self.mentor)

    def test_한쪽이_지워도_상대_쪽지함에는_남는다(self):
        self.message.delete_for(self.mentor)

        self.message.refresh_from_db()
        self.assertTrue(self.message.receiver_deleted)
        self.assertFalse(self.message.sender_deleted)

    def test_양쪽이_모두_지우면_행을_실제로_지운다(self):
        self.message.delete_for(self.mentor)
        self.message.delete_for(self.student)

        self.assertFalse(Message.objects.filter(pk=self.message.pk).exists())

    def test_제3자가_불러도_아무_일도_일어나지_않는다(self):
        self.message.delete_for(self.teacher)

        self.message.refresh_from_db()
        self.assertFalse(self.message.sender_deleted)
        self.assertFalse(self.message.receiver_deleted)

    def test_내가_지운_쪽지는_목록과_상세에서_사라진다(self):
        self.client.force_login(self.mentor)
        self.client.post(self.detail_url(self.message), {"action": "delete"})

        box = self.client.get(reverse("message_box"))
        detail = self.client.get(self.detail_url(self.message))

        self.assertEqual(len(box.context["message_page"]), 0)
        self.assertRedirects(detail, reverse("message_box"))

    def test_받는_사람이_지워도_보낸_쪽지함에는_남는다(self):
        self.message.delete_for(self.mentor)
        self.client.force_login(self.student)

        box = self.client.get(reverse("message_box"), {"tab": "sent"})

        self.assertEqual(list(box.context["message_page"]), [self.message])

    def test_안_읽고_지운_쪽지는_안_읽은_수에서_뺀다(self):
        self.send(self.teacher, self.mentor)
        self.assertEqual(Message.objects.unread_for(self.mentor).count(), 2)

        self.message.delete_for(self.mentor)

        self.assertEqual(Message.objects.unread_for(self.mentor).count(), 1)


class MessageCancelTests(MessageTestCase):
    def setUp(self):
        self.message = self.send(self.student, self.mentor)
        Notification.notify(
            self.mentor, Notification.Kind.MESSAGE, "새 쪽지", self.detail_url(self.message)
        )

    def test_읽기_전에는_발송을_취소할_수_있고_알림도_지운다(self):
        self.client.force_login(self.student)

        self.client.post(self.detail_url(self.message), {"action": "cancel"})

        self.assertFalse(Message.objects.filter(pk=self.message.pk).exists())
        self.assertEqual(Notification.objects.filter(receiver=self.mentor).count(), 0)

    def test_상대가_읽은_뒤에는_취소하거나_고칠_수_없다(self):
        reader = self.client_class()
        reader.force_login(self.mentor)
        reader.get(self.detail_url(self.message))
        self.client.force_login(self.student)

        self.client.post(self.detail_url(self.message), {"action": "cancel"})
        self.client.post(self.detail_url(self.message), {"action": "edit", "content": "고친 내용"})

        self.message.refresh_from_db()
        self.assertEqual(self.message.content, "안녕하세요")

    def test_받는_사람은_취소하거나_고칠_수_없다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.detail_url(self.message), {"action": "cancel"})
        self.client.post(self.detail_url(self.message), {"action": "edit", "content": "고친 내용"})

        self.message.refresh_from_db()
        self.assertEqual(self.message.content, "안녕하세요")
