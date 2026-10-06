"""프로젝트 팀원 모집 — 모집글 · 지원 · 승인/거절 · 마감"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ..models import Notification, Recruit, RecruitApplication
from .base import CommunityTestCase

WAITING = RecruitApplication.Status.WAITING
APPROVED = RecruitApplication.Status.APPROVED
REJECTED = RecruitApplication.Status.REJECTED


class RecruitTestCase(CommunityTestCase):
    def setUp(self):
        self.recruit = self.make_recruit(self.student)
        self.detail_url = reverse("recruit_detail", args=[self.recruit.recruit_id])
        self.apply_url = reverse("recruit_apply", args=[self.recruit.recruit_id])

    @staticmethod
    def days_later(days):
        return timezone.now().date() + timedelta(days=days)

    def make_recruit(self, writer, headcount=1, days=7, **extra):
        return Recruit.objects.create(
            writer=writer,
            title="장고 스터디",
            content="매주 토요일",
            field="백엔드",
            headcount=headcount,
            deadline=self.days_later(days),
            **extra,
        )

    def apply(self, applicant, status=WAITING):
        return RecruitApplication.objects.create(
            recruit=self.recruit, applicant=applicant, status=status
        )

    def decide_url(self, application, status):
        return reverse("recruit_app_decide", args=[application.application_id, status])


class RecruitCreateTests(RecruitTestCase):
    def form_data(self, **override):
        data = {
            "title": "사이드 프로젝트 팀원",
            "field": "프론트엔드",
            "headcount": 3,
            "deadline": self.days_later(10).isoformat(),
            "content": "함께 만들어요",
        }
        data.update(override)
        return data

    def test_모집글을_올리면_작성자가_기록된다(self):
        self.client.force_login(self.mentor)

        self.client.post(reverse("recruit_create"), self.form_data())

        self.assertEqual(Recruit.objects.get(title="사이드 프로젝트 팀원").writer, self.mentor)

    def test_잘못된_값은_500_대신_폼_오류로_돌려준다(self):
        self.client.force_login(self.mentor)
        bad_values = [
            {"title": ""},
            {"headcount": 0},
            {"headcount": "세 명"},
            {"deadline": "내일"},
            {"deadline": ""},
        ]

        for override in bad_values:
            with self.subTest(override=override):
                response = self.client.post(
                    reverse("recruit_create"), self.form_data(**override)
                )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)

        self.assertEqual(Recruit.objects.count(), 1)   # setUp 에서 만든 한 건뿐


class RecruitApplyTests(RecruitTestCase):
    def test_지원하면_작성자에게_알림이_간다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.apply_url, {"message": "참여하고 싶습니다"})

        application = RecruitApplication.objects.get()
        self.assertEqual(application.applicant, self.mentor)
        self.assertEqual(application.status, WAITING)
        notification = Notification.objects.get(receiver=self.student)
        self.assertEqual(notification.link, self.detail_url)

    def test_내가_올린_모집에는_지원할_수_없다(self):
        self.client.force_login(self.student)

        response = self.client.post(self.apply_url, {"message": "셀프 지원"})

        self.assertEqual(RecruitApplication.objects.count(), 0)
        self.assertIn("내가 올린 모집", self.message_texts(response)[0])

    def test_같은_모집에_두_번_지원해도_한_건만_남는다(self):
        self.client.force_login(self.mentor)

        self.client.post(self.apply_url, {"message": "첫 지원"})
        self.client.post(self.apply_url, {"message": "또 지원"})

        self.assertEqual(RecruitApplication.objects.get().message, "첫 지원")
        self.assertEqual(Notification.objects.count(), 1)

    def test_작성자가_마감한_모집에는_지원할_수_없다(self):
        self.recruit.is_closed = True
        self.recruit.save()
        self.client.force_login(self.mentor)

        self.client.post(self.apply_url, {"message": "늦은 지원"})

        self.assertEqual(RecruitApplication.objects.count(), 0)

    def test_마감일이_지난_모집에는_지원할_수_없다(self):
        self.recruit.deadline = self.days_later(-1)
        self.recruit.save()
        self.client.force_login(self.mentor)

        response = self.client.post(self.apply_url, {"message": "늦은 지원"})

        self.assertEqual(RecruitApplication.objects.count(), 0)
        self.assertIn("이미 마감된 모집", self.message_texts(response)[0])

    def test_마감일_당일까지는_모집중이다(self):
        self.recruit.deadline = self.days_later(0)

        self.assertTrue(self.recruit.is_recruiting)

    def test_대기_중인_지원만_취소할_수_있다(self):
        cancel_url = reverse("recruit_cancel", args=[self.recruit.recruit_id])
        waiting = self.apply(self.mentor)
        approved = self.apply(self.teacher, APPROVED)

        self.client.force_login(self.mentor)
        self.client.post(cancel_url)
        self.client.force_login(self.teacher)
        self.client.post(cancel_url)

        self.assertFalse(RecruitApplication.objects.filter(pk=waiting.pk).exists())
        self.assertTrue(RecruitApplication.objects.filter(pk=approved.pk).exists())


class RecruitDecideTests(RecruitTestCase):
    def test_승인하면_지원자에게_알림이_간다(self):
        application = self.apply(self.mentor)
        self.client.force_login(self.student)

        self.client.post(self.decide_url(application, APPROVED))

        application.refresh_from_db()
        self.assertEqual(application.status, APPROVED)
        self.assertIsNotNone(application.decided_at)
        self.assertTrue(
            Notification.objects.filter(receiver=self.mentor, message__contains="승인").exists()
        )

    def test_정원이_차면_더_승인할_수_없다(self):
        self.apply(self.mentor, APPROVED)          # 정원 1명이 이미 참
        late = self.apply(self.teacher)
        self.client.force_login(self.student)

        response = self.client.post(self.decide_url(late, APPROVED))

        late.refresh_from_db()
        self.assertEqual(late.status, WAITING)
        self.assertIn("이미 다 채웠습니다", self.message_texts(response)[0])

    def test_정원이_차도_거절과_승인_번복은_된다(self):
        approved = self.apply(self.mentor, APPROVED)
        late = self.apply(self.teacher)
        self.client.force_login(self.student)

        self.client.post(self.decide_url(late, REJECTED))
        self.client.post(self.decide_url(approved, WAITING))

        late.refresh_from_db()
        approved.refresh_from_db()
        self.assertEqual(late.status, REJECTED)
        self.assertEqual(approved.status, WAITING)
        self.assertIsNone(approved.decided_at)

    def test_작성자가_아니면_처리할_수_없다(self):
        application = self.apply(self.mentor)

        for member in (self.mentor, self.teacher):
            with self.subTest(member=member):
                self.client.force_login(member)

                self.client.post(self.decide_url(application, APPROVED))

                application.refresh_from_db()
                self.assertEqual(application.status, WAITING)

    def test_주소를_여는_것만으로는_상태가_바뀌지_않는다(self):
        application = self.apply(self.mentor)
        self.client.force_login(self.student)

        response = self.client.get(self.decide_url(application, APPROVED))

        self.assertEqual(response.status_code, 405)
        application.refresh_from_db()
        self.assertEqual(application.status, WAITING)

    def test_모르는_상태값은_무시한다(self):
        application = self.apply(self.mentor)
        self.client.force_login(self.student)

        self.client.post(self.decide_url(application, "합격"))

        application.refresh_from_db()
        self.assertEqual(application.status, WAITING)


class RecruitOwnerTests(RecruitTestCase):
    def test_지원자_목록은_작성자에게만_보인다(self):
        self.apply(self.mentor)

        self.client.force_login(self.student)
        owner_view = self.client.get(self.detail_url)
        self.client.force_login(self.teacher)
        other_view = self.client.get(self.detail_url)

        self.assertEqual(len(owner_view.context["applications"]), 1)
        self.assertIsNone(other_view.context["applications"])

    def test_작성자만_마감할_수_있다(self):
        close_url = reverse("recruit_close", args=[self.recruit.recruit_id])

        self.client.force_login(self.mentor)
        response = self.client.post(close_url)
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.student)
        self.client.post(close_url)

        self.recruit.refresh_from_db()
        self.assertTrue(self.recruit.is_closed)

    def test_작성자만_지울_수_있고_지운_글은_목록에서_빠진다(self):
        delete_url = reverse("recruit_delete", args=[self.recruit.recruit_id])

        self.client.force_login(self.mentor)
        self.client.post(delete_url)
        self.recruit.refresh_from_db()
        self.assertFalse(self.recruit.is_deleted)

        self.client.force_login(self.student)
        self.client.post(delete_url)

        response = self.client.get(reverse("recruit_list"))
        self.assertEqual(len(response.context["page"]), 0)
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_제목_소개_분야로_검색한다(self):
        for keyword in ("장고", "토요일", "백엔드"):
            with self.subTest(keyword=keyword):
                response = self.client.get(reverse("recruit_list"), {"q": keyword})

                self.assertEqual(len(response.context["page"]), 1)

        response = self.client.get(reverse("recruit_list"), {"q": "없는말"})
        self.assertEqual(len(response.context["page"]), 0)
