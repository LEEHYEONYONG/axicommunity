"""로그인 · 로그아웃 · 아이디 중복확인"""

from django.urls import reverse

from .base import CommunityTestCase


class LoginTests(CommunityTestCase):
    def login(self, password="test1234", **extra):
        return self.client.post(
            reverse("login"),
            {"username": self.student.username, "password": password, **extra},
        )

    def test_로그인하면_홈으로_간다(self):
        response = self.login()

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.pk)

    def test_비밀번호가_틀리면_로그인되지_않는다(self):
        response = self.login(password="wrong-password")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("올바르지 않습니다", self.message_texts(response)[0])

    def test_로그인_뒤_원래_보려던_화면으로_돌아간다(self):
        target = reverse("message_box")

        response = self.login(next=target)

        self.assertRedirects(response, target)

    def test_다른_사이트로_보내는_next_는_무시한다(self):
        for target in ("https://evil.example.com/", "//evil.example.com/"):
            with self.subTest(target=target):
                response = self.login(next=target)

                self.assertRedirects(response, reverse("home"))

    def test_탈퇴한_회원은_로그인할_수_없다(self):
        self.student.is_active = False
        self.student.save()

        self.login()

        self.assertNotIn("_auth_user_id", self.client.session)


class LogoutTests(CommunityTestCase):
    def test_POST_로_로그아웃한다(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_주소를_여는_것만으로는_로그아웃되지_않는다(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)


class CheckUsernameTests(CommunityTestCase):
    def test_쓰는_아이디와_빈_아이디를_구분한다(self):
        taken = self.client.get(reverse("check_username"), {"username": "student1"})
        free = self.client.get(reverse("check_username"), {"username": "brand_new"})

        self.assertEqual(taken.json(), {"is_taken": True})
        self.assertEqual(free.json(), {"is_taken": False})


class LoginRequiredTests(CommunityTestCase):
    def test_로그인이_필요한_화면은_비로그인을_로그인으로_보낸다(self):
        for name in ("message_box", "mypage", "notification_list", "recruit_create", "qna_ask"):
            with self.subTest(name=name):
                url = reverse(name)

                response = self.client.get(url)

                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_누구나_볼_수_있는_화면은_비로그인으로_열린다(self):
        for name in ("home", "qna_list", "recruit_list", "login", "signup", "find_account"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
