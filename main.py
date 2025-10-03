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
        # ✅ 비즈니스 로직 레이어를 거쳐서 호출
        user = await chatbot_manager.get_user_info(user_id)
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
    """웹훅 요청 처리 - Action 기반 분기"""
    user_id = user_request["user"]["id"]
    user_message = user_request["utterance"]
    action_name = action.get("name", "fallback")

    print(f"🎯 Action: {action_name}")
    print(f"💬 User message: {user_message}")

    # ========================================
    # 1. 테스트용 사용자 (개발/디버깅용)
    # ========================================
    if "test_user" in user_id:
        print("🧪 [Test User] LangGraph 워크플로우 처리")
        response = await chatbot_manager.handle_conversation(user_id, user_message)
        return response

    # ========================================
    # 2. Action 기반 명확한 분기 (버튼 클릭)
    # ========================================
    if action_name == "온보딩":
        print("🔘 [Button] 온보딩 버튼 클릭")
        response = await chatbot_manager.handle_conversation(
            user_id,
            user_message,
            action_hint="onboarding"
        )
        return response

    elif action_name in ["일일기록", "오늘의 일일기록 시작"]:
        print("🔘 [Button] 일일기록 버튼 클릭")
        response = await chatbot_manager.handle_conversation(
            user_id,
            user_message,
            action_hint="daily_record"
        )
        return response

    elif action_name == "서비스피드백":
        print("🔘 [Button] 서비스피드백 버튼 클릭")
        response = await chatbot_manager.handle_conversation(
            user_id,
            user_message,
            action_hint="service_feedback"
        )
        return response

    # ========================================
    # 3. 자연어 처리 (fallback)
    # ========================================
    # router_node가 DB 기반으로 자동 판단
    print("🤖 [자연어] LangGraph 워크플로우로 자동 라우팅")
    response = await chatbot_manager.handle_conversation(user_id, user_message)
    return response

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