"""작성 권한 판정 — board_permission 표에 있는 조합만 허용되는지"""

from django.contrib.auth.models import AnonymousUser

from ..models import Board, BoardPermission
from ..permissions import can_write, is_owner, write_denied_reason
from .base import ANSWER, QUESTION, CommunityTestCase


class CanWriteTests(CommunityTestCase):
    def test_표에_있는_조합만_허용한다(self):
        self.assertTrue(can_write(self.staff, self.notice))
        self.assertFalse(can_write(self.student, self.notice))
        self.assertFalse(can_write(self.teacher, self.notice))
        self.assertFalse(can_write(self.mentor, self.notice))

    def test_비로그인은_어디에도_쓸_수_없다(self):
        for board in Board.objects.all():
            self.assertFalse(can_write(AnonymousUser(), board))

    def test_qna_는_질문과_답변_권한을_따로_본다(self):
        # 수강생은 질문만, 강사는 답변만, 멘토는 둘 다
        self.assertTrue(can_write(self.student, self.qna, QUESTION))
        self.assertFalse(can_write(self.student, self.qna, ANSWER))

        self.assertFalse(can_write(self.teacher, self.qna, QUESTION))
        self.assertTrue(can_write(self.teacher, self.qna, ANSWER))

        self.assertTrue(can_write(self.mentor, self.qna, QUESTION))
        self.assertTrue(can_write(self.mentor, self.qna, ANSWER))

    def test_qna_에_일반_권한으로는_아무도_쓸_수_없다(self):
        for member in (self.student, self.teacher, self.mentor, self.staff):
            self.assertFalse(can_write(member, self.qna))

    def test_멘토의_취업비밀은_멘토만_쓴다(self):
        self.assertTrue(can_write(self.mentor, self.secret))
        for member in (self.student, self.teacher, self.staff):
            self.assertFalse(can_write(member, self.secret))

    def test_행을_추가하면_코드_수정_없이_권한이_열린다(self):
        self.assertFalse(can_write(self.student, self.job))

        BoardPermission.objects.create(board=self.job, user_type=self.student_type)

        self.assertTrue(can_write(self.student, self.job))

    def test_새_게시판은_권한을_넣기_전까지_전부_금지다(self):
        new_board = Board.objects.create(board_name="스터디")

        for member in (self.student, self.teacher, self.mentor, self.staff):
            self.assertFalse(can_write(member, new_board))


class WriteDeniedReasonTests(CommunityTestCase):
    def test_쓸_수_있는_회원유형을_안내한다(self):
        reason = write_denied_reason(self.notice)

        self.assertIn("공지사항", reason)
        self.assertIn("직원", reason)
        self.assertNotIn("수강생", reason)

    def test_아무도_쓸_수_없는_게시판은_따로_안내한다(self):
        new_board = Board.objects.create(board_name="스터디")

        self.assertEqual(write_denied_reason(new_board), "스터디은(는) 글을 쓸 수 없습니다.")


class IsOwnerTests(CommunityTestCase):
    def test_작성자_본인만_참이다(self):
        post = self.make_post(self.free, self.student)

        self.assertTrue(is_owner(self.student, post))
        self.assertFalse(is_owner(self.student2, post))
        self.assertFalse(is_owner(AnonymousUser(), post))
