"""Database 리팩토링 테스트 스크립트"""
import asyncio
from src.database import (
    Database,
    get_user_with_context,
    get_onboarding_history,
    save_onboarding_metadata,
    UserSchema,
)


async def test_database():
    """Database 기본 기능 테스트"""
    print("=" * 50)
    print("🧪 Database 리팩토링 테스트 시작")
    print("=" * 50)

    # 1. Database 인스턴스 생성
    print("\n1️⃣ Database 인스턴스 생성...")
    db = Database()
    print("✅ Database 생성 성공")

    # 2. get_user_with_context 테스트
    print("\n2️⃣ get_user_with_context 테스트...")
    test_user_id = "test_user_repo_pattern"

    try:
        user, context = await get_user_with_context(db, test_user_id)
        print(f"✅ get_user_with_context 성공")
        print(f"   - user: {user}")
        print(f"   - context.onboarding_stage: {context.onboarding_stage}")
        print(f"   - context.metadata: {context.metadata}")
    except Exception as e:
        print(f"❌ get_user_with_context 실패: {e}")
        import traceback
        traceback.print_exc()

    # 3. get_onboarding_history 테스트
    print("\n3️⃣ get_onboarding_history 테스트...")
    try:
        total_count, recent_messages = await get_onboarding_history(db, test_user_id)
        print(f"✅ get_onboarding_history 성공")
        print(f"   - total_count: {total_count}")
        print(f"   - recent_messages: {len(recent_messages)}개")
    except Exception as e:
        print(f"❌ get_onboarding_history 실패: {e}")
        import traceback
        traceback.print_exc()

    # 4. Schema 테스트
    print("\n4️⃣ UserSchema 테스트...")
    try:
        # Mock 데이터로 UserSchema 생성
        mock_user_data = {
            "kakao_user_id": "test_123",
            "name": "테스트",
            "job_title": "개발자",
            "attendance_count": 3,
            "daily_record_count": 2,
        }
        user_schema = UserSchema(**mock_user_data)
        print(f"✅ UserSchema 생성 성공")
        print(f"   - name: {user_schema.name}")
        print(f"   - job_title: {user_schema.job_title}")
        print(f"   - attendance_count: {user_schema.attendance_count}")
    except Exception as e:
        print(f"❌ UserSchema 실패: {e}")
        import traceback
        traceback.print_exc()

    # 5. save_onboarding_metadata 테스트
    print("\n5️⃣ save_onboarding_metadata 테스트...")
    try:
        from src.chatbot.state import UserMetadata

        # 테스트용 메타데이터 생성
        test_metadata = UserMetadata(
            name="홍길동",
            job_title="백엔드 개발자",
            total_years="3년",
            job_years="2년",
            career_goal="시니어 개발자",
            field_attempts={"name": 1, "job_title": 1},
            field_status={"name": "filled", "job_title": "filled"}
        )

        await save_onboarding_metadata(db, test_user_id, test_metadata)
        print(f"✅ save_onboarding_metadata 성공")
        print(f"   - name: {test_metadata.name}")
        print(f"   - job_title: {test_metadata.job_title}")
        print(f"   - field_attempts: {test_metadata.field_attempts}")
        print(f"   - field_status: {test_metadata.field_status}")

        # 저장된 데이터 확인
        user2, context2 = await get_user_with_context(db, test_user_id)
        print(f"   - 저장 후 조회: name={context2.metadata.name}, job_title={context2.metadata.job_title}")
    except Exception as e:
        print(f"❌ save_onboarding_metadata 실패: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("✅ 모든 테스트 완료!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_database())
