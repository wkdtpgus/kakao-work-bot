from .state import OnboardingState, OnboardingResponse
from .utils import is_onboarding_complete, get_daily_reflections_count


# =============================================================================
# 기본 노드들
# =============================================================================

async def load_user_state(state: OnboardingState, db, memory_manager) -> OnboardingState:
    """사용자 상태 로드 노드"""
    try:
        user_id = state["user_id"]

        # 먼저 메모리 매니저의 캐시에서 확인
        cached_user = getattr(memory_manager, '_user_cache', {}).get(user_id)

        # 캐시가 있으면 사용, 없으면 DB에서 로드
        if cached_user:
            user = cached_user
            print(f"🔄 캐시된 사용자 정보 사용: {user_id}")
        else:
            user = await db.get_user(user_id)
            print(f"📥 DB에서 사용자 정보 로드: {user_id}")

        # 온보딩 상태 구성
        current_state = {
            "name": user.get("name") if user else None,
            "job": user.get("job") if user else None,
            "total_experience_year": user.get("total_experience_year") if user else None,
            "job_experience_year": user.get("job_experience_year") if user else None,
            "career_goal": user.get("career_goal") if user else None,
            "projects": user.get("projects") if user else None,
            "recent_tasks": user.get("recent_tasks") if user else None,
            "job_meaning": user.get("job_meaning") if user else None,
            "work_philosophy": user.get("work_philosophy") if user else None
        }

        # 대화 히스토리 로드
        conversation_history = await memory_manager.get_conversation_history(user_id, db)

        state["current_state"] = current_state
        state["conversation_history"] = conversation_history

        print(f"✅ 사용자 상태 로드: {user_id} - name: {current_state.get('name')}")
        return state

    except Exception as e:
        print(f"❌ 사용자 상태 로드 실패: {e}")
        state["current_state"] = {}
        state["conversation_history"] = []
        return state


async def check_next_step(state: OnboardingState, db) -> OnboardingState:
    """다음 단계 결정 노드"""
    try:
        user_id = state["user_id"]
        current_state = state["current_state"]

        # 온보딩 완료 여부 체크
        if not is_onboarding_complete(current_state):
            state["next_step"] = "continue_onboarding"
        else:
            # 일일 회고 횟수 체크
            daily_reflections_count = await get_daily_reflections_count(user_id, db)

            if daily_reflections_count > 0 and daily_reflections_count % 7 == 0:
                # 7일마다 주간 랩업
                state["next_step"] = "weekly_wrapup"
            else:
                # 일일 회고
                state["next_step"] = "daily_reflection"

        print(f"✅ 다음 단계 결정: {state['next_step']}")
        return state

    except Exception as e:
        print(f"❌ 다음 단계 결정 실패: {e}")
        state["next_step"] = "continue_onboarding"  # 기본값
        return state


async def save_conversation(state: OnboardingState, memory_manager, db) -> OnboardingState:
    """대화 저장 노드"""
    try:
        user_id = state["user_id"]
        message = state["message"]
        ai_response = state["ai_response"]

        # 메모리에 저장
        await memory_manager.add_messages(user_id, message, ai_response, db)
        print(f"✅ 대화 저장 완료")

        return state

    except Exception as e:
        print(f"❌ 대화 저장 실패: {e}")
        return state


# =============================================================================
# 온보딩 노드들
# =============================================================================

async def generate_ai_response(state: OnboardingState, llm, prompt_loader) -> OnboardingState:
    """AI 응답 생성 노드"""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        message = state["message"]
        current_state = state["current_state"]

        # LLM이 없으면 에러 발생
        if not llm:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다. 환경변수 OPENAI_API_KEY를 설정해주세요.")

        # 프롬프트 구성
        system_prompt = prompt_loader.get_system_prompt()
        user_prompt = prompt_loader.format_user_prompt(message, current_state)

        # 메시지 구성
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        # LLM 호출 (structured output)
        response = await llm.ainvoke(messages)

        # 디버깅을 위한 로그
        print(f"🔍 LLM 응답 타입: {type(response)}")
        print(f"🔍 LLM 응답 내용: {response}")

        # OnboardingResponse 객체에서 response 부분만 추출
        if isinstance(response, OnboardingResponse):
            state["ai_response"] = response.response
            # 모든 필드를 확인해서 None이 아닌 값들을 추출
            updated_vars = {}
            field_names = ['name', 'job', 'total_experience_year', 'job_experience_year',
                          'career_goal', 'projects', 'recent_tasks', 'job_meaning', 'work_philosophy']

            for field in field_names:
                value = getattr(response, field, None)
                if value is not None:
                    updated_vars[field] = value

            state["updated_variables"] = updated_vars

            # 현재 상태도 즉시 업데이트 (같은 세션 내에서 반영되도록)
            current_state = state.get("current_state", {})
            for key, value in updated_vars.items():
                if value is not None:
                    current_state[key] = value
            state["current_state"] = current_state

            print(f"✅ Structured output 성공: {response.response}")
            print(f"🔄 추출된 변수: {updated_vars}")
            print(f"🔄 업데이트된 상태: {current_state}")
        else:
            state["ai_response"] = str(response)
            state["updated_variables"] = {}
            print(f"⚠️ Structured output 실패, 원본 사용")

        return state

    except Exception as error:
        print(f"❌ AI 응답 생성 오류: {error}")
        state["ai_response"] = f"AI 응답 생성 중 오류가 발생했습니다: {str(error)}"
        state["updated_variables"] = {}
        return state


async def update_user_info(state: OnboardingState, db, memory_manager=None) -> OnboardingState:
    """사용자 정보 업데이트 노드"""
    try:
        user_id = state["user_id"]
        updated_variables = state["updated_variables"]

        if updated_variables:
            # 기존 사용자 정보 가져오기
            user = await db.get_user(user_id)
            if not user:
                user = {"id": user_id}

            # 업데이트된 변수들 적용
            for key, value in updated_variables.items():
                if value is not None:  # None이 아닌 값만 업데이트
                    # 값 정리 (불필요한 문자 제거)
                    if isinstance(value, str):
                        # 특수 문자 제거
                        cleaned_value = value.strip()
                        # JSON 관련 문자들 제거
                        for char in ['}}]}', ']}', '}}', '"]', '"']:
                            cleaned_value = cleaned_value.replace(char, '')
                        user[key] = cleaned_value.strip()
                    else:
                        user[key] = value

            # 메모리 매니저 캐시 업데이트
            if memory_manager:
                if not hasattr(memory_manager, '_user_cache'):
                    memory_manager._user_cache = {}
                memory_manager._user_cache[user_id] = user
                print(f"🔄 사용자 캐시 업데이트: {user_id}")

            # 데이터베이스에 저장 시도 (실패해도 캐시는 유지)
            try:
                await db.create_or_update_user(user_id, user)
                print(f"✅ 사용자 정보 DB 업데이트: {updated_variables}")
            except Exception as db_error:
                print(f"⚠️ DB 업데이트 실패하지만 캐시는 업데이트됨: {db_error}")

        return state

    except Exception as e:
        print(f"❌ 사용자 정보 업데이트 실패: {e}")
        return state


# =============================================================================
# 일일 회고 노드들 (임시)
# =============================================================================

async def start_daily_reflection(state: OnboardingState) -> OnboardingState:
    """일일 업무 회고 시작 노드"""
    try:
        # TODO: 일일 회고 프롬프트 적용
        state["ai_response"] = "오늘 하루 어떤 업무를 하셨나요? 구체적으로 알려주세요!"
        state["updated_variables"] = {}

        print(f"✅ 일일 회고 시작")
        return state

    except Exception as e:
        print(f"❌ 일일 회고 시작 실패: {e}")
        state["ai_response"] = "일일 회고를 시작하는 중 오류가 발생했습니다."
        return state


async def collect_daily_tasks(state: OnboardingState) -> OnboardingState:
    """오늘 한 업무 수집 노드"""
    try:
        # TODO: 업무 수집 프롬프트 적용
        message = state["message"]

        # 임시로 단순히 메시지를 저장
        state["updated_variables"] = {
            "today_tasks": message,
            "reflection_date": "2024-01-01"  # TODO: 실제 날짜로 변경
        }

        state["ai_response"] = "좋네요! 그 업무에서 어떤 점이 가장 도전적이었나요?"

        print(f"✅ 일일 업무 수집 완료")
        return state

    except Exception as e:
        print(f"❌ 일일 업무 수집 실패: {e}")
        state["ai_response"] = "업무 수집 중 오류가 발생했습니다."
        return state


# =============================================================================
# 주간 랩업 노드들 (임시)
# =============================================================================

async def start_weekly_wrapup(state: OnboardingState) -> OnboardingState:
    """주간 랩업 시작 노드"""
    try:
        # TODO: 주간 랩업 프롬프트 적용
        state["ai_response"] = "이번 주 7일간의 업무를 돌아보며 전체적인 성장과 인사이트를 정리해보겠습니다!"
        state["updated_variables"] = {}

        print(f"✅ 주간 랩업 시작")
        return state

    except Exception as e:
        print(f"❌ 주간 랩업 시작 실패: {e}")
        state["ai_response"] = "주간 랩업 시작 중 오류가 발생했습니다."
        return state


async def generate_weekly_insights(state: OnboardingState) -> OnboardingState:
    """주간 인사이트 생성 노드"""
    try:
        user_id = state["user_id"]

        # TODO: 지난 7일간의 회고 데이터를 분석하여 인사이트 생성
        # 임시 인사이트
        insights = {
            "growth_areas": ["문제 해결 능력", "커뮤니케이션"],
            "key_achievements": ["프로젝트 완성", "새로운 기술 학습"],
            "next_week_goals": ["더 효율적인 작업 방식 적용"]
        }

        state["updated_variables"] = insights
        state["ai_response"] = "이번 주의 핵심 인사이트를 정리해드렸습니다. 다음 주 목표도 함께 설정해보세요!"

        print(f"✅ 주간 인사이트 생성 완료")
        return state

    except Exception as e:
        print(f"❌ 주간 인사이트 생성 실패: {e}")
        state["ai_response"] = "인사이트 생성 중 오류가 발생했습니다."
        return state


async def save_weekly_summary(state: OnboardingState) -> OnboardingState:
    """주간 요약 저장 노드"""
    try:
        user_id = state["user_id"]

        # TODO: 주간 요약을 DB에 저장
        weekly_summary = {
            "user_id": user_id,
            "week_start": "2024-01-01",
            "week_end": "2024-01-07",
            "insights": state["updated_variables"]
        }

        # 임시로 로그만 출력
        print(f"📊 주간 요약 저장: {weekly_summary}")

        state["ai_response"] = "주간 랩업이 완료되었습니다! 다음 주부터 새로운 일일 회고를 시작하겠습니다."

        return state

    except Exception as e:
        print(f"❌ 주간 요약 저장 실패: {e}")
        state["ai_response"] = "주간 요약 저장 중 오류가 발생했습니다."
        return state


