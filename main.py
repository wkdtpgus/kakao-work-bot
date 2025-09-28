from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from dotenv import load_dotenv

from src.chatbot.graph_manager import ChatBotManager
from src.database import Database

# 환경 변수 로드
load_dotenv()

app = FastAPI(title="3분 커리어 챗봇")

# 정적 파일 서빙 (public 폴더)
app.mount("/static", StaticFiles(directory="public"), name="static")

# public 파일들을 루트에서 직접 서빙
@app.get("/style.css")
async def get_css():
    return FileResponse('public/style.css', media_type='text/css')

@app.get("/script.js")
async def get_js():
    return FileResponse('public/script.js', media_type='application/javascript')

# 데이터베이스 및 ChatBot 초기화
db = Database()
chatbot_manager = ChatBotManager(db)

# 앱 시작 시 초기화
@app.on_event("startup")
async def startup_event():
    await chatbot_manager.initialize()

class ChatRequest(BaseModel):
    userId: str
    message: str

class UserResponse(BaseModel):
    user: dict
    utterance: str

class ActionResponse(BaseModel):
    name: str

@app.get("/")
async def serve_index():
    """메인 페이지 서빙"""
    return FileResponse('public/index.html')

@app.get("/api/status")
async def get_status():
    """서버 상태 확인"""
    return {
        "status": "running",
        "timestamp": "2024-01-01T00:00:00Z",
        "message": "3분 커리어 챗봇 서버가 정상 작동 중입니다."
    }

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """로컬 테스트용 채팅 API"""
    try:
        # 기존 웹훅 로직 재사용
        user_request = {
            "user": {"id": request.userId},
            "utterance": request.message
        }

        action = {"name": "test_action"}

        # 웹훅 핸들러 호출
        response = await handle_webhook_request(user_request, action)
        return response

    except Exception as e:
        print(f"로컬 채팅 API 오류: {e}")
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
                    }
                }]
            }
        }

@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    """사용자 정보 조회"""
    try:
        user = await db.get_user(user_id)
        return user
    except Exception as e:
        print(f"사용자 정보 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="사용자 정보를 가져올 수 없습니다.")

@app.post("/webhook")
async def webhook(request: dict):
    """카카오톡 웹훅 엔드포인트"""
    try:
        user_request = request.get("userRequest")
        action = request.get("action")

        response = await handle_webhook_request(user_request, action)
        return response

    except Exception as e:
        print(f"Webhook error: {e}")
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
                    }
                }]
            }
        }

async def handle_webhook_request(user_request: dict, action: dict):
    """웹훅 요청 처리"""
    user_id = user_request["user"]["id"]
    user_message = user_request["utterance"]

    print(f"Action: {action['name']}")
    print(f"User message: {user_message}")

    # 현재 대화 상태 확인
    state = await db.get_conversation_state(user_id)
    print(f"🔍 현재 대화 상태: {state.get('current_step') if state else '없음'}")

    # 테스트용 사용자는 바로 AI 대화 모드로 진입
    if "test_user" in user_id:
        print("🧪 테스트용 사용자 감지 - AI 대화 모드로 직접 진입")

        # 기존 상태 삭제하고 새로 시작
        if state:
            await db.delete_conversation_state(user_id)

        # ai_conversation 단계로 직접 시작
        await db.upsert_conversation_state(user_id, "ai_conversation", {
            "conversation_history": [],
            "current_topic": "3분커리어"
        })

        response = await chatbot_manager.handle_conversation(user_id, user_message)
        return response

    # "3분 커리어" 키워드 처리
    if user_message == "오늘의 3분 커리어 시작!" or "3분 커리어" in user_message:
        print("🚀 3분 커리어 키워드 감지 - 우선 처리")

        if state:
            await db.delete_conversation_state(user_id)

        await db.upsert_conversation_state(user_id, "ai_intro", {})
        response = await chatbot_manager.handle_conversation(user_id, user_message)
        return response

    # 진행 중인 대화 상태에 따른 처리
    if state and state.get("current_step"):
        if state["current_step"] in ["onboarding_start", "name_input", "job_input",
                                   "total_years", "job_years", "career_goal",
                                   "project_name", "recent_work", "job_meaning", "important_thing"]:
            return await handle_onboarding(user_id, user_message)
        elif state["current_step"] == "ai_intro":
            return await chatbot_manager.handle_conversation(user_id, user_message)
        elif state["current_step"] == "ai_conversation":
            return await chatbot_manager.handle_conversation(user_id, user_message)
        else:
            # 알 수 없는 상태 - 초기화
            await db.delete_conversation_state(user_id)
            return await handle_welcome(user_id)
    else:
        # 새로운 대화 시작
        if user_message in ["온보딩 시작", "온보딩"]:
            return await handle_onboarding(user_id, user_message)
        elif user_message in ["오늘의 3분 커리어 시작!"] or "3분 커리어" in user_message:
            await db.upsert_conversation_state(user_id, "ai_intro", {})
            return await chatbot_manager.handle_conversation(user_id, user_message)
        else:
            return await handle_welcome(user_id)

async def handle_welcome(user_id: str):
    """환영 메시지 처리"""
    user = await db.get_user(user_id)

    if not user:
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "안녕하세요! 3분커리어 온보딩봇입니다.\n먼저 간단한 정보를 입력해주세요."
                    }
                }],
                "quickReplies": [{
                    "label": "시작하기",
                    "action": "message",
                    "messageText": "온보딩 시작"
                }]
            }
        }
    elif not user.get("onboarding_completed"):
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "온보딩을 완료해주세요."
                    }
                }],
                "quickReplies": [{
                    "label": "온보딩계속",
                    "action": "message",
                    "messageText": "온보딩 계속"
                }]
            }
        }
    else:
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": f"안녕하세요 {user['name']}님!\n온보딩이 완료되었습니다! 🎉"
                    }
                }],
                "quickReplies": [{
                    "label": "완료",
                    "action": "message",
                    "messageText": "완료"
                }]
            }
        }

async def handle_onboarding(user_id: str, message: str):
    """온보딩 처리 (기존 로직 유지)"""
    # TODO: 기존 Node.js의 온보딩 로직을 Python으로 포팅
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": "온보딩 기능은 아직 구현 중입니다."
                }
            }]
        }
    }

async def handle_ai_intro_transition(user_id: str, message: str, state: dict):
    """AI 소개에서 대화로 전환"""
    # TODO: 기존 Node.js의 AI intro 로직을 Python으로 포팅
    return await chatbot.handle_conversation(user_id, message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)