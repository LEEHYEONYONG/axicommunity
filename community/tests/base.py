"""
테스트 공통 준비물.

게시판·회원유형·작성 권한은 sql/seed.sql 과 같은 조합으로 만듭니다.
권한 표가 바뀌면 여기와 seed.sql 을 함께 고치세요.
"""

import shutil
import tempfile

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings

from ..models import Board, BoardPermission, Member, Post, UserType

GENERAL = BoardPermission.PermissionType.GENERAL
QUESTION = BoardPermission.PermissionType.QUESTION
ANSWER = BoardPermission.PermissionType.ANSWER

# 테스트가 올린 첨부파일이 실제 media/ 에 섞이지 않게 임시 폴더로 돌립니다
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="axi_test_media_")


# 비밀번호 해시는 일부러 느리게 만들어져 있어서, 회원을 만들 때마다 테스트가 늘어집니다
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, PASSWORD_HASHERS=FAST_HASHERS)
class CommunityTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student_type = UserType.objects.create(type_name="수강생")
        cls.teacher_type = UserType.objects.create(type_name="강사")
        cls.mentor_type = UserType.objects.create(type_name="멘토")
        cls.staff_type = UserType.objects.create(type_name="직원")

        cls.notice = Board.objects.create(board_name="공지사항")
        cls.free = Board.objects.create(board_name="자유게시판")
        cls.qna = Board.objects.create(board_name="Q&A", allow_comment=False)
        cls.job = Board.objects.create(board_name="취업정보")
        cls.secret = Board.objects.create(board_name="멘토의 취업비밀", is_anonymous=True)

        permissions = [
            (cls.notice, cls.staff_type, GENERAL),
            (cls.free, cls.student_type, GENERAL),
            (cls.free, cls.teacher_type, GENERAL),
            (cls.free, cls.mentor_type, GENERAL),
            (cls.free, cls.staff_type, GENERAL),
            (cls.qna, cls.student_type, QUESTION),
            (cls.qna, cls.mentor_type, QUESTION),
            (cls.qna, cls.mentor_type, ANSWER),
            (cls.qna, cls.teacher_type, ANSWER),
            (cls.job, cls.teacher_type, GENERAL),
            (cls.job, cls.mentor_type, GENERAL),
            (cls.job, cls.staff_type, GENERAL),
            (cls.secret, cls.mentor_type, GENERAL),
        ]
        BoardPermission.objects.bulk_create(
            BoardPermission(board=b, user_type=t, permission_type=p)
            for b, t, p in permissions
        )

        cls.student = cls.make_member("student1", "한수강", cls.student_type)
        cls.student2 = cls.make_member("student2", "두수강", cls.student_type)
        cls.teacher = cls.make_member("teacher1", "김강사", cls.teacher_type)
        cls.mentor = cls.make_member("mentor1", "최멘토", cls.mentor_type)
        cls.mentor2 = cls.make_member("mentor2", "박멘토", cls.mentor_type)
        cls.staff = cls.make_member("staff1", "운영직원", cls.staff_type)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    @staticmethod
    def make_member(username, name, user_type, **extra):
        return Member.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test1234",
            member_name=name,
            phone="01012345678",
            address="서울특별시",
            user_type=user_type,
            **extra,
        )

    @staticmethod
    def make_post(board, writer, title="제목", content="내용", **extra):
        return Post.objects.create(
            board=board, writer=writer, title=title, content=content, **extra
        )

    def message_texts(self, response):
        """뷰가 messages 로 남긴 안내 문구 목록"""
        return [str(m) for m in get_messages(response.wsgi_request)]
