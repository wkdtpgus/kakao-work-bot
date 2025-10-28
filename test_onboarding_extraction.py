"""
온보딩 개선 테스트 (의도 추출 방식)
"""

import asyncio
from src.chatbot.state import ExtractionResponse, OnboardingIntent
from src.prompt.onboarding import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT_TEMPLATE, FIELD_DESCRIPTIONS
from src.prompt.onboarding_questions import get_field_template, FIELD_ORDER
from langchain_core.messages import SystemMessage, HumanMessage


async def test_extraction_cases():
    """다양한 사용자 입력에 대한 추출 테스트"""

    # LLM 초기화 (실제 환경에서는 실제 LLM 사용)
    from src.utils.models import get_onboarding_llm
    llm = get_onboarding_llm()
    extraction_llm = llm.with_structured_output(ExtractionResponse)

    test_cases = [
        # (target_field, user_message, expected_intent)
        ("name", "지은이라고 불러주세요", OnboardingIntent.ANSWER),
        ("name", "gg", OnboardingIntent.ANSWER),  # confidence 낮아야 함
        ("job_title", "백엔드 개발자예요", OnboardingIntent.ANSWER),
        ("job_title", "개발자", OnboardingIntent.ANSWER),  # confidence 중간
        ("total_years", "5년 정도 했어요", OnboardingIntent.ANSWER),
        ("total_years", "신입입니다", OnboardingIntent.ANSWER),  # 특수 케이스
        ("career_goal", "건너뛰기", OnboardingIntent.SKIP),
        ("project_name", "무슨 뜻이에요?", OnboardingIntent.CLARIFICATION),
        ("recent_work", "오늘 날씨 좋네요", OnboardingIntent.INVALID),
    ]

    print("=" * 60)
    print("온보딩 정보 추출 테스트")
    print("=" * 60)

    for target_field, user_message, expected_intent in test_cases:
        field_description = FIELD_DESCRIPTIONS.get(target_field, "")
        extraction_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
            target_field=target_field,
            field_description=field_description,
            user_message=user_message
        )

        result = await extraction_llm.ainvoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=extraction_prompt)
        ])

        print(f"\n[{target_field}] \"{user_message}\"")
        print(f"  예상 의도: {expected_intent.value}")
        print(f"  실제 의도: {result.intent.value} {'✅' if result.intent == expected_intent else '❌'}")
        print(f"  추출 값: {result.extracted_value}")
        print(f"  신뢰도: {result.confidence:.2f}")
        print(f"  명확화 필요: {result.clarification_needed}")


def test_question_templates():
    """질문 템플릿 테스트"""
    print("\n" + "=" * 60)
    print("질문 템플릿 테스트")
    print("=" * 60)

    for field_name in FIELD_ORDER[:3]:  # 처음 3개만 테스트
        template = get_field_template(field_name)
        print(f"\n[{field_name}]")
        print(f"  1차 시도: {template.get_question(1)[:50]}...")
        print(f"  2차 시도: {template.get_question(2)[:50]}...")
        print(f"  3차 시도: {template.get_question(3)[:50]}...")


def test_validation():
    """검증 로직 테스트"""
    print("\n" + "=" * 60)
    print("검증 로직 테스트")
    print("=" * 60)

    test_cases = [
        ("name", "지은", False),  # 3자 미만
        ("name", "김지은", True),
        ("name", "123", False),  # 숫자만
        ("job_title", "백엔드 개발자", True),
        ("job_title", "개", False),  # 2자 미만
        ("total_years", "5년", True),
        ("total_years", "신입", True),
        ("total_years", "abc", False),  # 숫자 없음
    ]

    for field_name, value, expected in test_cases:
        template = get_field_template(field_name)
        result = template.validate(value)
        status = "✅" if result == expected else "❌"
        print(f"{status} [{field_name}] '{value}' -> {result} (예상: {expected})")


if __name__ == "__main__":
    print("\n🧪 온보딩 개선 테스트 시작\n")

    # 1. 질문 템플릿 테스트
    test_question_templates()

    # 2. 검증 로직 테스트
    test_validation()

    # 3. LLM 추출 테스트 (비동기)
    print("\n⏳ LLM 추출 테스트 시작 (시간이 소요될 수 있습니다)...\n")
    asyncio.run(test_extraction_cases())

    print("\n✅ 모든 테스트 완료!")
