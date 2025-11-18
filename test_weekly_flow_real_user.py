"""실제 사용자 ID로 주간 요약 플로우 테스트

사용법:
    python test_weekly_flow_real_user.py YOUR_KAKAO_USER_ID

주의사항:
    - 실제 DB에 저장되므로 주의해서 사용하세요
    - 평일 2일 이상 기록이 있어야 주간 요약이 생성됩니다
"""
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 파이썬 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.database.database import Database
from src.service.weekly.feedback_processor import (
    handle_weekly_v1_request,
    handle_weekly_qna_response
)
from src.utils.models import get_chat_llm
from src.chatbot.state import UserMetadata


async def test_real_user_weekly_flow(user_id: str):
    """실제 사용자로 주간 요약 플로우 테스트"""

    # DB 로깅 억제
    import logging
    logging.getLogger('src.database').setLevel(logging.INFO)
    logging.getLogger('src.service').setLevel(logging.INFO)

    print("\n" + "="*70)
    print(f"🧪 주간 요약 플로우 테스트 - 사용자: {user_id}")
    print("="*70 + "\n")

    # DB 및 LLM 초기화
    db = Database()
    llm = get_chat_llm()

    # 1. 사용자 정보 조회
    print("📦 사용자 정보 조회 중...\n")
    user_data = await db.get_user(user_id)

    if not user_data:
        print(f"❌ 사용자를 찾을 수 없습니다: {user_id}")
        print("💡 카카오워크에서 먼저 온보딩을 완료해주세요.")
        return

    metadata = UserMetadata(
        name=user_data.get("name", "사용자"),
        job_title=user_data.get("job_title", "직장인"),
        career_goal=user_data.get("career_goal", "성장하기")
    )

    print(f"👤 사용자 정보:")
    print(f"   이름: {metadata.name}")
    print(f"   직무: {metadata.job_title}")
    print(f"   목표: {metadata.career_goal}\n")

    # 2. 주간 요약 준비 상태 확인
    from src.database import check_weekly_summary_ready

    is_ready, weekday_count = await check_weekly_summary_ready(db, user_id)
    print(f"📊 주간 요약 준비 상태:")
    print(f"   평일 기록 일수: {weekday_count}일")
    print(f"   주간 요약 가능: {'✅ 예' if is_ready else '❌ 아니오'}\n")

    if not is_ready:
        print("💡 주간 요약을 받으려면:")
        print("   1. 평일(월~금) 중 2일 이상 기록이 필요합니다")
        print("   2. 주말(토/일)에 실행해야 합니다\n")

        # 강제로 진행할지 물어보기
        print("그래도 테스트를 진행하시겠습니까? (y/n): ", end="")
        choice = input().strip().lower()
        if choice != 'y':
            print("테스트를 취소합니다.")
            return
        print()

    # 3. v1.0 생성
    print("━"*70)
    print("📋 Step 1: 주간 요약 v1.0 생성")
    print("━"*70 + "\n")

    v1_result = await handle_weekly_v1_request(db, user_id, metadata, llm)

    print("✅ v1.0 요약 생성 완료\n")
    print("📝 전체 응답:")
    print(v1_result.ai_response)
    print()

    # 4. QnA 티키타카
    print("━"*70)
    print("💬 Step 2: 역질문 티키타카 (최대 5턴)")
    print("━"*70)
    print("💡 답변을 입력하세요. 'skip'을 입력하면 자동으로 5턴까지 진행합니다.\n")

    turn_count = 0
    while turn_count < 5:
        turn_count += 1
        print(f"\n{'─'*70}")
        print(f"💬 Turn {turn_count}/5")
        print(f"{'─'*70}\n")

        # 사용자 입력 받기
        print("👤 유저 응답: ", end="")
        user_answer = input().strip()

        if not user_answer:
            print("⚠️  빈 응답입니다. 다시 입력해주세요.")
            turn_count -= 1
            continue

        # skip이면 자동 답변
        if user_answer.lower() == 'skip':
            auto_answers = [
                "주로 프로젝트 개발과 코드 리뷰를 했어요",
                "3개의 새로운 기능을 구현했고, 버그도 5개 수정했습니다",
                "팀원들과 협업하며 좋은 아이디어를 많이 얻었어요",
                "사용자 만족도가 올라가서 뿌듯했습니다",
                "이번 주는 정말 보람찬 한 주였어요!"
            ]
            user_answer = auto_answers[turn_count - 1]
            print(f"   (자동) {user_answer}")

        # QnA 처리
        qna_result = await handle_weekly_qna_response(db, user_id, user_answer, llm)

        if qna_result.summary_type == 'weekly_v2':
            print(f"\n{'━'*70}")
            print("✅ v2.0 생성 완료!")
            print(f"{'━'*70}\n")
            print("📝 전체 응답:")
            print(qna_result.ai_response)
            print()
            break
        else:
            print(f"\n🤖 AI 응답:")
            print(f"   {qna_result.ai_response}\n")

    # 5. 소감 입력
    print("━"*70)
    print("💭 Step 3: 주간 소감 입력")
    print("━"*70)
    print("\n👤 이번 주에 대한 소감을 입력하세요: ", end="")
    user_thought = input().strip()

    if not user_thought:
        user_thought = "이번 주도 열심히 달렸습니다! 다음 주도 화이팅!"
        print(f"   (기본) {user_thought}")

    # 소감 저장
    ai_response = "소중한 한마디 감사합니다! 다음 주에도 열심히 기록하며 성장해봐요! 😊"
    await db.save_conversation_turn(
        user_id,
        user_thought,
        ai_response,
        is_summary=False,
        is_review=True
    )

    print(f"\n🤖 AI 응답:")
    print(f"   {ai_response}\n")
    print("✅ 소감 저장 완료 (is_review=True)\n")

    # 6. 저장된 데이터 확인
    print("="*70)
    print("📊 저장된 데이터 확인")
    print("="*70 + "\n")

    # 주간 요약 조회
    weekly_summaries = db.supabase.table("ai_answer_messages") \
        .select("*") \
        .eq("kakao_user_id", user_id) \
        .eq("is_summary", True) \
        .in_("summary_type", ["weekly_v1", "weekly_v2"]) \
        .order("created_at", desc=True) \
        .limit(5) \
        .execute()

    print(f"📋 최근 주간 요약: {len(weekly_summaries.data)}개")
    for i, summary in enumerate(weekly_summaries.data, 1):
        print(f"   {i}. {summary['summary_type']} ({summary['created_at'][:10]})")

    # 소감 조회
    user_reviews = db.supabase.table("user_answer_messages") \
        .select("*") \
        .eq("kakao_user_id", user_id) \
        .eq("is_review", True) \
        .order("created_at", desc=True) \
        .limit(3) \
        .execute()

    print(f"\n💭 최근 소감: {len(user_reviews.data)}개")
    for i, review in enumerate(user_reviews.data, 1):
        print(f"   {i}. {review['content'][:50]}... ({review['created_at'][:10]})")

    print(f"\n{'='*70}")
    print("✅ 테스트 완료!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python test_weekly_flow_real_user.py YOUR_KAKAO_USER_ID")
        print("\n예시: python test_weekly_flow_real_user.py 12345678")
        sys.exit(1)

    user_id = sys.argv[1]

    try:
        asyncio.run(test_real_user_weekly_flow(user_id))
    except KeyboardInterrupt:
        print("\n\n테스트 중단됨")
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
