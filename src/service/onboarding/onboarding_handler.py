"""온보딩 첫 진입 처리 핸들러"""
from ...chatbot.state import UserMetadata, OnboardingIntent, ExtractionResponse
from ...prompt.onboarding_questions import (
    FIELD_ORDER,
    format_welcome_message,
    get_field_template,
    get_progress_indicator,
    get_next_field,
    format_completion_message
)
from ...database import save_onboarding_metadata
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


async def handle_first_onboarding(db, user_id: str, current_metadata: UserMetadata) -> dict:
    """첫 온보딩 환영 메시지 및 첫 질문 처리

    Args:
        db: DB 인스턴스
        user_id: 사용자 ID
        current_metadata: 현재 메타데이터 (비어있을 것으로 예상)

    Returns:
        dict: {
            "is_first": bool,
            "ai_response": str (첫 온보딩인 경우에만)
        }
    """
    # conversation_states로 첫 온보딩인지 체크
    conv_state = await db.get_conversation_state(user_id)
    has_onboarding_messages = False
    if conv_state and conv_state.get("temp_data"):
        has_onboarding_messages = "onboarding_messages" in conv_state["temp_data"]

    is_first_onboarding = not has_onboarding_messages and all(
        getattr(current_metadata, field) is None for field in FIELD_ORDER
    )

    if not is_first_onboarding:
        logger.info(f"[FirstOnboarding] 첫 온보딩 아님 (user_id={user_id})")
        return {"is_first": False}

    # 첫 온보딩 처리
    logger.info(f"[FirstOnboarding] 첫 온보딩 시작 (user_id={user_id})")

    welcome_msg = format_welcome_message()
    # 첫 질문 가져오기
    first_template = get_field_template("name")
    first_question = first_template.get_question(1)
    progress = get_progress_indicator(current_metadata.dict())
    ai_response = f"{welcome_msg}\n\n{progress}\n\n{first_question}"

    # 메타데이터 초기화 (field_attempts, field_status 저장)
    await save_onboarding_metadata(db, user_id, current_metadata)

    # 대화 히스토리 저장
    conv_state_updated = await db.get_conversation_state(user_id)
    existing_temp_data = conv_state_updated.get("temp_data", {}) if conv_state_updated else {}
    existing_temp_data["onboarding_messages"] = [{"role": "assistant", "content": ai_response}]

    await db.upsert_conversation_state(
        user_id,
        current_step="onboarding",
        temp_data=existing_temp_data
    )

    logger.info(f"[FirstOnboarding] 환영 메시지 생성 완료 (user_id={user_id})")

    return {
        "is_first": True,
        "ai_response": ai_response
    }


async def process_extraction_result(
    db,
    user_id: str,
    message: str,
    extraction_result: ExtractionResponse,
    current_metadata: UserMetadata,
    target_field: str
) -> dict:
    """추출 결과에 따른 처리 및 다음 질문 생성

    Args:
        db: DB 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지
        extraction_result: LLM 추출 결과
        current_metadata: 현재 메타데이터
        target_field: 현재 수집 중인 필드

    Returns:
        dict: {
            "ai_response": str,
            "is_completed": bool,  # 온보딩 완료 여부
            "should_save": bool    # 메타데이터 저장 필요 여부
        }
    """
    from ...database import complete_onboarding

    updated_metadata = current_metadata.copy()
    current_attempt = updated_metadata.field_attempts.get(target_field, 0)
    field_template = get_field_template(target_field)
    user_name = updated_metadata.name  # 질문에 사용할 이름

    # field_attempts의 의미: 이 필드에서 몇 번 시도했는가
    # 0 → 첫 시도 → 1차 질문 (get_question(1))
    # 1 → 두 번째 시도 → 2차 질문 (get_question(2))
    # 2 → 세 번째 시도 → 3차 질문 (get_question(3))

    if extraction_result.intent == OnboardingIntent.CLARIFICATION:
        # 명확화 요청 - 시도 횟수 증가하고 더 자세한 질문 제공
        updated_metadata.field_attempts[target_field] = current_attempt + 1
        new_attempt = updated_metadata.field_attempts[target_field]
        # 최대 3차 질문까지
        progress = get_progress_indicator(updated_metadata.dict())
        question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
        ai_response = f"{progress}\n\n{question}"

        await save_onboarding_metadata(db, user_id, updated_metadata)
        return {
            "ai_response": ai_response,
            "is_completed": False,
            "should_save": False  # 이미 저장했음
        }

    elif extraction_result.intent == OnboardingIntent.INVALID:
        # 무관한 응답 - 시도 횟수 증가 후 재질문 또는 스킵
        updated_metadata.field_attempts[target_field] = current_attempt + 1
        new_attempt = updated_metadata.field_attempts[target_field]

        # 3회 이상 시도 시 스킵 처리
        if new_attempt >= 3:
            updated_metadata.field_status[target_field] = "insufficient"
            setattr(updated_metadata, target_field, f"[SKIPPED] 응답 거부")
            logger.warning(f"[OnboardingHandler] [{target_field}] 3회 무관한 응답 - 스킵 처리")

            # 다음 필드로 이동
            next_field = get_next_field(updated_metadata.dict())

            if next_field:
                next_template = get_field_template(next_field)
                ai_response = next_template.get_question(1, name=updated_metadata.name)
            else:
                # 온보딩 완료
                await save_onboarding_metadata(db, user_id, updated_metadata)
                await complete_onboarding(db, user_id)
                ai_response = format_completion_message(updated_metadata.name)
                return {
                    "ai_response": ai_response,
                    "is_completed": True,
                    "should_save": False  # 이미 저장했음
                }

            await save_onboarding_metadata(db, user_id, updated_metadata)
            return {
                "ai_response": ai_response,
                "is_completed": False,
                "should_save": False  # 이미 저장했음
            }
        else:
            # 재질문
            logger.warning(f"[OnboardingHandler] [{target_field}] 무관한 응답 ({new_attempt}/3회) - 재질문")
            progress = get_progress_indicator(updated_metadata.dict())
            question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
            ai_response = f"{progress}\n\n{question}"
            await save_onboarding_metadata(db, user_id, updated_metadata)
            return {
                "ai_response": ai_response,
                "is_completed": False,
                "should_save": False  # 이미 저장했음
            }

    elif extraction_result.intent == OnboardingIntent.ANSWER:
        # 답변 제공됨
        extracted_value = extraction_result.extracted_value
        confidence = extraction_result.confidence

        # 신뢰도 체크: 0.5 미만이면 명확화 필요
        if confidence < 0.5:
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]
            logger.warning(f"[OnboardingHandler] [{target_field}] 신뢰도 낮음 (conf={confidence:.2f}) - 명확화 요청")
            progress = get_progress_indicator(updated_metadata.dict())
            question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
            ai_response = f"{progress}\n\n{question}"
            # 메타데이터 저장 후 종료
            await save_onboarding_metadata(db, user_id, updated_metadata)
            return {
                "ai_response": ai_response,
                "is_completed": False,
                "should_save": False  # 이미 저장했음
            }

        # 신입 특수 처리
        if target_field == "total_years" and extracted_value and "신입" in extracted_value:
            updated_metadata.total_years = "신입"
            updated_metadata.job_years = "신입"
            updated_metadata.field_status["total_years"] = "filled"
            updated_metadata.field_status["job_years"] = "filled"
            updated_metadata.field_attempts["total_years"] = current_attempt + 1
            updated_metadata.field_attempts["job_years"] = 0  # job_years는 건너뛰었으므로 0
            logger.info(f"[OnboardingHandler] 신입 감지 - total_years, job_years 모두 '신입'으로 설정")

            # career_goal로 이동
            next_field = "career_goal"
        else:
            # 검증
            if field_template.validate(extracted_value):
                # privacy_consent 특수 처리: "동의" → True, "비동의" → 재질문
                if target_field == "privacy_consent":
                    if extracted_value.strip() == "동의":
                        setattr(updated_metadata, target_field, True)
                        updated_metadata.field_status[target_field] = "filled"
                        updated_metadata.field_attempts[target_field] = current_attempt + 1
                        logger.info(f"[OnboardingHandler] [{target_field}] 값 저장: True")
                        next_field = get_next_field(updated_metadata.dict())
                    else:
                        # 비동의 시 저장하지 않고 재질문
                        updated_metadata.field_attempts[target_field] = current_attempt + 1
                        new_attempt = updated_metadata.field_attempts[target_field]
                        logger.info(f"[OnboardingHandler] [{target_field}] 비동의 - 재질문 ({new_attempt}/3)")

                        progress = get_progress_indicator(updated_metadata.dict())
                        question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
                        ai_response = f"⚠️ 개인정보 수집 동의 없이는 3분커리어 서비스를 이용하실 수 없습니다.\n\n{progress}\n\n{question}"

                        await save_onboarding_metadata(db, user_id, updated_metadata)
                        return {
                            "ai_response": ai_response,
                            "is_completed": False,
                            "should_save": False
                        }
                else:
                    setattr(updated_metadata, target_field, extracted_value)
                    updated_metadata.field_status[target_field] = "filled"
                    updated_metadata.field_attempts[target_field] = current_attempt + 1
                    logger.info(f"[OnboardingHandler] [{target_field}] 값 저장: {extracted_value}")

                    # 다음 필드
                    next_field = get_next_field(updated_metadata.dict())
            else:
                # 검증 실패
                updated_metadata.field_attempts[target_field] = current_attempt + 1
                logger.warning(f"[OnboardingHandler] [{target_field}] 검증 실패: {extracted_value}")
                next_field = target_field  # 같은 필드 재시도

        # 시도 횟수 체크 (3회 초과 시 스킵)
        if updated_metadata.field_attempts.get(target_field, 0) >= 3:
            # privacy_consent 특수 처리: 3회 비동의 시 False 저장 + 서비스 차단
            if target_field == "privacy_consent":
                setattr(updated_metadata, target_field, False)
                updated_metadata.field_status[target_field] = "rejected"
                await save_onboarding_metadata(db, user_id, updated_metadata)
                ai_response = "개인정보 수집에 동의하지 않으셨습니다.\n\n⚠️ 개인정보 수집 동의 없이는 3분커리어 서비스를 이용하실 수 없습니다.\n\n서비스 이용을 원하시면 관리자에게 문의해주세요."
                logger.info(f"[OnboardingHandler] [{target_field}] 3회 비동의 - 서비스 차단")
                return {
                    "ai_response": ai_response,
                    "is_completed": False,
                    "should_save": False
                }
            else:
                updated_metadata.field_status[target_field] = "insufficient"
                setattr(updated_metadata, target_field, f"[INSUFFICIENT] {extracted_value or message[:50]}")
            next_field = get_next_field(updated_metadata.dict())

        # 다음 질문 생성
        if next_field == target_field:
            # 같은 필드 재시도 (검증 실패 케이스)
            next_attempt_count = updated_metadata.field_attempts.get(next_field, 0)
            # attempts가 1이면 2차 질문, 2이면 3차 질문
            next_question = field_template.get_question(min(next_attempt_count + 1, 3), name=user_name)
            progress = get_progress_indicator(updated_metadata.dict())
            ai_response = f"{progress}\n\n{next_question}"
        elif next_field:
            # 다른 필드로 이동 (성공 케이스)
            next_template = get_field_template(next_field)
            # 새 필드는 아직 시도 안 했으므로 1차 질문
            # name이 방금 저장되었을 수 있으니 updated_metadata에서 다시 가져옴
            next_question = next_template.get_question(1, name=updated_metadata.name)

            # 진행률 표시 + 다음 질문
            progress = get_progress_indicator(updated_metadata.dict())

            # 신입 특수 처리: job_years 생략 안내
            if target_field == "total_years" and updated_metadata.total_years == "신입":
                skip_message = "💡 신입이시군요! 현재 직무 경력을 물어보는 질문은 생략되었습니다."
                ai_response = f"{skip_message}\n\n{progress}\n\n{next_question}"
            else:
                ai_response = f"{progress}\n\n{next_question}"
        else:
            # 완료 - 마지막 필드까지 저장 후 온보딩 완료 처리
            logger.info(f"[OnboardingHandler] 온보딩 완료 - save_onboarding_metadata 호출 전")
            logger.info(f"[OnboardingHandler] updated_metadata.important_thing = {updated_metadata.important_thing}")
            await save_onboarding_metadata(db, user_id, updated_metadata)
            logger.info(f"[OnboardingHandler] save_onboarding_metadata 완료")
            await complete_onboarding(db, user_id)
            ai_response = format_completion_message(updated_metadata.name)
            logger.info(f"[OnboardingHandler] 온보딩 완료, onboarding_messages 삭제됨")
            return {
                "ai_response": ai_response,
                "is_completed": True,
                "should_save": False  # 이미 저장했음
            }

        await save_onboarding_metadata(db, user_id, updated_metadata)
        return {
            "ai_response": ai_response,
            "is_completed": False,
            "should_save": False  # 이미 저장했음
        }

    else:  # INVALID
        # 무관한 내용 - 현재 필드 재질문
        updated_metadata.field_attempts[target_field] = current_attempt + 1
        new_attempt = updated_metadata.field_attempts[target_field]
        # new_attempt가 1이면 2차 질문, 2이면 3차 질문
        progress = get_progress_indicator(updated_metadata.dict())
        question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
        ai_response = f"{progress}\n\n{question}"

        await save_onboarding_metadata(db, user_id, updated_metadata)
        return {
            "ai_response": ai_response,
            "is_completed": False,
            "should_save": False  # 이미 저장했음
        }


# =============================================================================
# 온보딩 헬퍼 함수들 (utils.py에서 이동)
# =============================================================================

async def save_onboarding_conversation(
    db,
    user_id: str,
    user_message: str,
    ai_message: str,
    max_history: int = 6
) -> None:
    """온보딩 대화 히스토리 저장 (최근 N개만 유지)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_message: 사용자 메시지
        ai_message: AI 응답 메시지
        max_history: 최대 유지 턴 수 (기본 6개 = 3턴)

    Usage:
        onboarding_agent_node에서 대화 진행 중 히스토리 저장
    """
    conv_state = await db.get_conversation_state(user_id)
    recent_messages = []

    if conv_state and conv_state.get("temp_data"):
        recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-max_history:]

    recent_messages.append({"role": "user", "content": user_message})
    recent_messages.append({"role": "assistant", "content": ai_message})
    recent_messages = recent_messages[-max_history:]  # 최근 N개만 유지

    await db.upsert_conversation_state(
        user_id,
        current_step="onboarding",
        temp_data={"onboarding_messages": recent_messages}
    )


async def update_onboarding_state(
    db,
    user_id: str,
    metadata: UserMetadata,
    ai_response: str,
    user_message: Optional[str] = None
) -> None:
    """온보딩 메타데이터 + 대화 히스토리 업데이트를 한 번에 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        ai_response: AI 응답 메시지
        user_message: 사용자 메시지 (있으면 히스토리에 추가)

    Usage:
        onboarding_agent_node에서 메타데이터 저장 + 히스토리 저장을 한 번에
    """
    # 메타데이터 저장
    await save_onboarding_metadata(db, user_id, metadata)

    # 대화 히스토리 저장 (user_message가 있을 때만)
    if user_message:
        await save_onboarding_conversation(db, user_id, user_message, ai_response)
