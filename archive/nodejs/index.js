const express = require("express");
const cors = require("cors");
const path = require("path");
const { createClient } = require("@supabase/supabase-js");
require("dotenv").config();

const app = express();
app.use(cors());
app.use(express.json());

// 정적 파일 서빙 (public 폴더)
app.use(express.static(path.join(__dirname, "public")));

// Supabase 클라이언트 설정 (환경 변수가 없으면 모킹)
let supabase;
if (process.env.SUPABASE_URL && process.env.SUPABASE_ANON_KEY) {
  supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_ANON_KEY
  );
} else {
  console.log(
    "⚠️ Supabase 환경 변수가 설정되지 않았습니다. 모킹 모드로 실행됩니다."
  );
  // 모킹된 Supabase 클라이언트
  supabase = {
    from: (table) => ({
      select: () => ({
        eq: () => ({ single: () => ({ data: null, error: null }) }),
      }),
      insert: () => ({
        select: () => ({ single: () => ({ data: null, error: null }) }),
      }),
      update: () => ({ eq: () => ({ data: null, error: null }) }),
      upsert: () => ({ data: null, error: null }),
      delete: () => ({ eq: () => ({ data: null, error: null }) }),
    }),
  };
}

// Supabase 연결 테스트
async function testSupabaseConnection() {
  try {
    const { data, error } = await supabase
      .from("users")
      .select("count")
      .limit(1);

    if (error) {
      console.error("❌ Supabase 연결 실패:", error);
      return false;
    }

    console.log("✅ Supabase 연결 성공!");
    return true;
  } catch (err) {
    console.error("❌ Supabase 연결 테스트 중 오류:", err);
    return false;
  }
}

// 키워드 추출 함수들
function extractJobTitle(text) {
  // "입니다", "이에요" 등 제거하고 핵심 직무만 추출
  return text.replace(/입니다?|이에요|입니다\.?|이에요\.?/g, "").trim();
}

// AI Agent 대화 시스템 - 토큰 절약 버전
// prompt.text에서 프롬프트 읽기
const fs = require("fs");

// AI Agent 시스템 프롬프트 읽기
let AI_AGENT_SYSTEM_PROMPT = "";
let AI_AGENT_USER_PROMPT_TEMPLATE = "";

try {
  const promptContent = fs.readFileSync(
    path.join(__dirname, "prompt.text"),
    "utf8"
  );

  // AI_AGENT_SYSTEM_PROMPT 추출
  const systemMatch = promptContent.match(
    /AI_AGENT_SYSTEM_PROMPT = """([\s\S]*?)"""/
  );
  if (systemMatch) {
    AI_AGENT_SYSTEM_PROMPT = systemMatch[1].trim();
    console.log("✅ AI Agent 시스템 프롬프트 로드 성공");
  }

  // AI_AGENT_USER_PROMPT_TEMPLATE 추출
  const userMatch = promptContent.match(
    /AI_AGENT_USER_PROMPT_TEMPLATE = """([\s\S]*?)"""/
  );
  if (userMatch) {
    AI_AGENT_USER_PROMPT_TEMPLATE = userMatch[1].trim();
    console.log("✅ AI Agent 유저 프롬프트 템플릿 로드 성공");
  }

  if (!AI_AGENT_SYSTEM_PROMPT) {
    throw new Error("시스템 프롬프트를 찾을 수 없습니다");
  }
} catch (error) {
  console.error("❌ 프롬프트 파일 읽기 실패:", error.message);
  // 폴백 프롬프트 사용
  AI_AGENT_SYSTEM_PROMPT = `3분커리어 AI Agent. 친근하게 대화하며 업무 경험을 정리하고 강화. 한국어 사용. 공감 표현과 구체적 질문으로 더 나은 표현 도출. 응답은 공감→질문→정리 순서.`;
  AI_AGENT_USER_PROMPT_TEMPLATE = `# Conversation History\n{conversation_history}\n\n# User's Latest Message\n{user_message}\n\n# Instructions\nBased on the conversation history and user's latest message, provide a helpful response following the AI_AGENT_SYSTEM_PROMPT guidelines.`;
  console.log("⚠️ 폴백 프롬프트 사용");
}

// 토큰 절약을 위한 캐싱 시스템
const responseCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5분 캐시

/*
🎯 토큰 절약 전략:
1. 프롬프트 간소화: 상세한 설명 대신 핵심만
2. 대화 히스토리 제한: 최근 6개 메시지만 유지
3. 메시지 길이 제한: 사용자 입력 300자, 히스토리 200자
4. 응답 길이 제한: max_tokens 500으로 설정
5. 모델 선택: gpt-3.5-turbo (gpt-4보다 1/10 비용)
6. 캐싱 시스템: 동일한 질문에 대한 중복 API 호출 방지
7. 정기적 캐시 정리: 메모리 누수 방지
*/

async function callChatGPT(message, conversationHistory = []) {
  try {
    // API 키가 없으면 모킹된 응답 반환
    if (!process.env.OPENAI_API_KEY) {
      console.log("🤖 모킹된 AI 응답 생성 중...");

      // 간단한 모킹된 응답들
      const mockResponses = [
        "정말 흥미로운 이야기네요! 그 업무에서 어떤 부분이 가장 도전적이었나요?",
        "좋은 경험이군요! 그 결과로 어떤 성과를 얻으셨나요?",
        "흥미로운 프로젝트네요! 그 과정에서 배운 점이 있다면 무엇인가요?",
        "훌륭한 업무 경험이에요! 이런 경험을 이력서에 어떻게 표현하면 좋을까요?",
        "정말 의미 있는 작업이었네요! 그 업무의 핵심 가치는 무엇이라고 생각하시나요?",
        "좋은 질문이에요! 그 부분에 대해 좀 더 구체적으로 설명해주실 수 있나요?",
        "흥미로운 관점이네요! 그런 경험을 통해 어떤 인사이트를 얻으셨나요?",
        "훌륭한 성과군요! 그 성과를 달성하기 위해 어떤 노력을 하셨나요?",
      ];

      // 메시지 내용에 따른 맞춤형 응답
      let response =
        mockResponses[Math.floor(Math.random() * mockResponses.length)];

      if (message.includes("프로젝트") || message.includes("개발")) {
        response =
          "개발 프로젝트 경험이군요! 어떤 기술 스택을 사용하셨고, 그 과정에서 어떤 도전과제가 있었나요?";
      } else if (message.includes("회의") || message.includes("미팅")) {
        response =
          "회의나 미팅 관련 업무네요! 그 과정에서 어떤 역할을 하셨고, 어떤 결과를 얻으셨나요?";
      } else if (message.includes("분석") || message.includes("데이터")) {
        response =
          "데이터 분석 업무군요! 어떤 도구를 사용하셨고, 그 결과로 어떤 인사이트를 얻으셨나요?";
      } else if (message.includes("고객") || message.includes("서비스")) {
        response =
          "고객 서비스 관련 업무네요! 그 과정에서 어떤 문제를 해결하셨고, 고객에게 어떤 가치를 제공하셨나요?";
      }

      // 캐시에 저장
      const cacheKey = `${message.substring(0, 100)}_${conversationHistory.length}`;
      responseCache.set(cacheKey, {
        response: response,
        timestamp: Date.now(),
      });

      return response;
    }

    // 실제 API 호출
    const cacheKey = `${message.substring(0, 100)}_${conversationHistory.length}`;
    const cached = responseCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      console.log("캐시된 응답 사용 - 토큰 절약!");
      return cached.response;
    }

    // 빠른 응답을 위한 타임아웃 설정
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000); // 4초 타임아웃

    // 토큰 절약: 대화 히스토리 길이 제한 (최근 6개 메시지만 유지)
    const limitedHistory = conversationHistory.slice(-6);

    // 토큰 절약: 메시지 길이 제한 (각 메시지 최대 200자)
    const truncatedHistory = limitedHistory.map((msg) => ({
      role: msg.role,
      content:
        msg.content.length > 200
          ? msg.content.substring(0, 200) + "..."
          : msg.content,
    }));

    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-3.5-turbo", // gpt-4보다 토큰당 비용이 낮음
        messages: [
          { role: "system", content: AI_AGENT_SYSTEM_PROMPT },
          {
            role: "user",
            content: AI_AGENT_USER_PROMPT_TEMPLATE.replace(
              "{conversation_history}",
              JSON.stringify(truncatedHistory, null, 2)
            ).replace(
              "{user_message}",
              message.length > 300 ? message.substring(0, 300) + "..." : message
            ),
          },
        ],
        max_tokens: 300, // 더 빠른 응답을 위해 토큰 수 줄임
        temperature: 0.7,
      }),
      signal: controller.signal,
    });

    // 타임아웃 정리
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status}`);
    }

    // 타임아웃 에러 처리
    if (response.status === 0 && response.type === "aborted") {
      throw new Error("OpenAI API timeout - 4초 초과");
    }

    const data = await response.json();
    const aiResponse = data.choices[0].message.content;

    // 응답 캐싱
    responseCache.set(cacheKey, {
      response: aiResponse,
      timestamp: Date.now(),
    });

    // 캐시 크기 제한 (메모리 절약)
    if (responseCache.size > 100) {
      const firstKey = responseCache.keys().next().value;
      responseCache.delete(firstKey);
    }

    return aiResponse;
  } catch (error) {
    console.error("ChatGPT API 호출 오류:", error);

    if (error.name === "AbortError" || error.message.includes("timeout")) {
      return "죄송합니다. 응답이 너무 늦어졌습니다. 다시 시도해주세요.";
    }

    return "죄송합니다. AI 응답을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  }
}

// AI Agent 대화 처리 - 타임아웃 방지 버전
async function handleAIConversation(userId, message) {
  try {
    console.log("🤖 AI Agent 대화 시작:", userId);
    console.log("📨 받은 메시지:", message);
    console.log("🔄 함수 실행 시작...");

    // 즉시 응답을 위한 자연스러운 대화형 메시지 (AI와 대화 중임을 숨김)
    let immediateResponse;

    // 현재 AI 대화 상태 가져오기
    let { data: aiState } = await supabase
      .from("conversation_states")
      .select("*")
      .eq("kakao_user_id", userId)
      .eq("current_step", "ai_conversation")
      .single();

    // 첫 번째 메시지인지 확인 (대화 히스토리가 비어있거나 첫 번째 메시지인 경우)
    if (
      !aiState ||
      !aiState.temp_data?.conversation_history ||
      aiState.temp_data.conversation_history.length === 0
    ) {
      console.log("🆕 새로운 AI 대화 시작 - 극단적인 프롬프트로 직접 응답");

      // 사용자 이름 가져오기
      const { data: user } = await supabase
        .from("users")
        .select("name")
        .eq("kakao_user_id", userId)
        .single();

      const userName = user?.name || "사용자";
      console.log("👤 사용자 이름:", userName);

      // ai_conversation 단계로 설정
      const { error: updateError } = await supabase
        .from("conversation_states")
        .update({
          current_step: "ai_conversation",
          temp_data: {
            conversation_history: [],
            current_topic: "3분커리어",
            user_name: userName,
          },
          updated_at: new Date(),
        })
        .eq("kakao_user_id", userId)
        .eq("current_step", "ai_conversation");

      if (updateError) {
        console.error("❌ ai_conversation 단계 설정 실패:", updateError);
      } else {
        console.log("✅ ai_conversation 단계로 설정 완료");
      }

      // 극단적인 프롬프트로 직접 AI 응답 생성
      console.log("🤖 극단적인 프롬프트로 AI 응답 생성 중...");
      const aiResponse = await callChatGPT(message, []);
      console.log("🎯 극단적인 프롬프트 결과:", aiResponse);

      immediateResponse = {
        version: "2.0",
        template: {
          outputs: [
            {
              simpleText: {
                text: aiResponse,
              },
            },
          ],
        },
      };
    } else {
      // 대화 중: 자연스러운 생각하는 중 메시지
      const naturalResponses = [
        "음... 🤔 그건 정말 흥미로운 주제네요! 잠깐 생각해볼게요.",
        "아, 그런 질문이군요! 좀 더 구체적으로 생각해보겠습니다.",
        "흠... 🤔 그 부분에 대해 좀 더 깊이 생각해보고 있어요.",
        "오, 좋은 지적이에요! 잠시 정리해보겠습니다.",
        "그건 정말 중요한 포인트네요. 차근차근 정리해볼게요.",
        "음... 🤔 그 부분에 대해 좀 더 자세히 살펴보겠습니다.",
        "아, 그런 관점도 있군요! 잠깐 생각해보겠습니다.",
        "흥미로운 질문이에요! 좀 더 구체적으로 정리해보겠습니다.",
      ];

      const randomResponse =
        naturalResponses[Math.floor(Math.random() * naturalResponses.length)];

      immediateResponse = {
        version: "2.0",
        template: {
          outputs: [
            {
              simpleText: {
                text: randomResponse,
              },
            },
          ],
        },
      };
    }

    // 비동기로 AI 응답 처리 (백그라운드에서 실행)
    processAIAgentResponse(userId, message).catch((error) => {
      console.error("❌ AI 응답 처리 중 오류:", error);
    });

    // 즉시 응답 반환 (5초 타임아웃 방지)
    return immediateResponse;
  } catch (error) {
    console.error("AI 대화 처리 오류:", error);
    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "AI 대화 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
            },
          },
        ],
      },
    };
  }
}

// 비동기 AI 응답 처리 함수
async function processAIAgentResponse(userId, message) {
  try {
    console.log("🔄 비동기 AI 응답 처리 시작...");

    // 임시로 conversation_states 테이블 사용
    let { data: aiState } = await supabase
      .from("conversation_states")
      .select("*")
      .eq("kakao_user_id", userId)
      .eq("current_step", "ai_conversation")
      .single();

    if (!aiState) {
      console.log("🆕 새로운 AI 대화 상태 생성 중...");
      // 새로운 AI 대화 시작
      const { data: newState, error: insertError } = await supabase
        .from("conversation_states")
        .insert({
          kakao_user_id: userId,
          current_step: "ai_conversation",
          temp_data: {
            conversation_history: [
              {
                role: "assistant",
                content:
                  "안녕하세요! 오늘도 3분 커리어와 함께하시는군요. 어떤 이야기를 나누고 싶으신가요? 😊",
              },
            ],
            current_topic: "3분커리어",
          },
          updated_at: new Date(),
        })
        .select()
        .single();

      if (insertError) {
        console.error("❌ AI 대화 상태 생성 오류:", insertError);
        return;
      }
      aiState = newState;
      console.log("✅ AI 대화 상태 생성 성공");
    }

    // 대화 히스토리 구성
    const conversationHistory = aiState.temp_data?.conversation_history || [];
    console.log("📝 현재 대화 히스토리 길이:", conversationHistory.length);

    // ChatGPT API 호출
    console.log("🤖 ChatGPT API 호출 중...");
    const aiResponse = await callChatGPT(message, conversationHistory);
    console.log("✅ ChatGPT 응답 받음");

    // 대화 히스토리 업데이트
    const updatedHistory = [
      ...conversationHistory,
      { role: "user", content: message },
      { role: "assistant", content: aiResponse },
    ];

    // 데이터베이스 업데이트
    console.log("💾 대화 히스토리 저장 중...");
    const { error: updateError } = await supabase
      .from("conversation_states")
      .update({
        temp_data: {
          ...aiState.temp_data,
          conversation_history: updatedHistory,
        },
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId)
      .eq("current_step", "ai_conversation");

    if (updateError) {
      console.error("❌ 대화 히스토리 저장 실패:", updateError);
    } else {
      console.log("✅ 대화 히스토리 저장 성공");
    }

    console.log("🎯 AI 응답 완료:", aiResponse);
  } catch (error) {
    console.error("❌ AI 응답 처리 중 오류:", error);
  }
}

function extractYears(text) {
  // "년차" 제거하고 숫자만 추출
  const match = text.match(/(\d+)년차?/);
  return match ? match[1] + "년차" : text;
}

function extractCareerGoal(text) {
  // "입니다", "이에요" 등 제거
  return text.replace(/입니다?|이에요|입니다\.?|이에요\.?/g, "").trim();
}

function extractProjectName(text) {
  // "프로젝트명 : ", "목표 : " 등 제거하고 핵심 내용만 추출
  return text.replace(/프로젝트명\s*:\s*|목표\s*:\s*/g, "").trim();
}

function extractRecentWork(text) {
  // "를 주로합니다", "를 합니다" 등 제거하고 핵심 업무만 추출
  return text
    .replace(/를\s*주로\s*합니다?|를\s*합니다?|합니다?\.?/g, "")
    .trim();
}

function extractJobMeaning(text) {
  // "라고 생각해요", "입니다" 등 제거하고 핵심 의미만 추출
  return text
    .replace(/라고\s*생각해요?|입니다?|이에요?|입니다\.?|이에요\.?/g, "")
    .trim();
}

// 루트 경로 - 웹 페이지 서빙
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

// 서버 상태 확인 API
app.get("/api/status", (req, res) => {
  res.json({
    status: "running",
    timestamp: new Date().toISOString(),
    message: "3분 커리어 챗봇 서버가 정상 작동 중입니다.",
  });
});

// 로컬 테스트용 채팅 API
app.post("/api/chat", async (req, res) => {
  try {
    const { userId, message } = req.body;

    if (!userId || !message) {
      return res.status(400).json({
        error: "userId와 message는 필수입니다.",
      });
    }

    console.log("🤖 로컬 테스트 채팅 요청:", { userId, message });

    // 기존 웹훅 로직 재사용
    const mockUserRequest = {
      user: { id: userId },
      utterance: message,
    };

    const mockAction = { name: "test_action" };

    // 웹훅 핸들러 호출
    const response = await handleWebhookRequest(mockUserRequest, mockAction);

    res.json(response);
  } catch (error) {
    console.error("로컬 채팅 API 오류:", error);
    res.status(500).json({
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            },
          },
        ],
      },
    });
  }
});

// 사용자 정보 조회 API
app.get("/api/user/:userId", async (req, res) => {
  try {
    const { userId } = req.params;

    const { data: user, error } = await supabase
      .from("users")
      .select("*")
      .eq("kakao_user_id", userId)
      .single();

    if (error && error.code !== "PGRST116") {
      // PGRST116은 데이터 없음 오류
      throw error;
    }

    res.json(user || null);
  } catch (error) {
    console.error("사용자 정보 조회 오류:", error);
    res.status(500).json({ error: "사용자 정보를 가져올 수 없습니다." });
  }
});

// 웹훅 요청 처리 함수 분리
async function handleWebhookRequest(userRequest, action) {
  const userId = userRequest.user.id;
  const userMessage = userRequest.utterance;
  const actionId = action.name;

  console.log("Action:", actionId);
  console.log("User message:", userMessage);

  let response;

  // 🔥 핵심: 진행 중인 대화 상태를 먼저 확인
  const { data: state } = await supabase
    .from("conversation_states")
    .select("*")
    .eq("kakao_user_id", userId)
    .single();

  console.log("🔍 현재 대화 상태:", state ? state.current_step : "없음");
  console.log("📝 상태 상세:", state);

  // 테스트용 사용자는 바로 AI 대화 모드로 진입
  if (userId.includes("test_user")) {
    console.log("🧪 테스트용 사용자 감지 - AI 대화 모드로 직접 진입");

    // 기존 상태가 있으면 삭제하고 새로 시작
    if (state) {
      await supabase
        .from("conversation_states")
        .delete()
        .eq("kakao_user_id", userId);
      console.log("🗑️ 기존 상태 삭제 완료");
    }

    // ai_conversation 단계로 직접 시작
    await supabase.from("conversation_states").upsert({
      kakao_user_id: userId,
      current_step: "ai_conversation",
      temp_data: {
        conversation_history: [],
        current_topic: "3분커리어",
      },
      updated_at: new Date(),
    });

    response = await handleAIConversation(userId, userMessage);
    return response;
  }

  // "3분 커리어" 키워드가 포함된 경우 우선 처리 (어떤 상황에서든)
  if (
    userMessage === "오늘의 3분 커리어 시작!" ||
    userMessage.includes("3분 커리어")
  ) {
    console.log("🚀 3분 커리어 키워드 감지 - 우선 처리");

    // 기존 상태가 있으면 삭제하고 새로 시작
    if (state) {
      await supabase
        .from("conversation_states")
        .delete()
        .eq("kakao_user_id", userId);
      console.log("🗑️ 기존 상태 삭제 완료");
    }

    // ai_intro 단계로 새로 시작
    await supabase.from("conversation_states").upsert({
      kakao_user_id: userId,
      current_step: "ai_intro",
      temp_data: {},
      updated_at: new Date(),
    });

    response = await handleAIConversation(userId, userMessage);
    return response;
  }

  // 진행 중인 대화가 있으면 우선 처리
  if (state && state.current_step) {
    console.log("Found active conversation:", state.current_step);
    console.log("🎯 상태별 처리 분기 시작...");

    if (
      state.current_step === "onboarding_start" ||
      state.current_step === "name_input" ||
      state.current_step === "job_input" ||
      state.current_step === "total_years" ||
      state.current_step === "job_years" ||
      state.current_step === "career_goal" ||
      state.current_step === "project_name" ||
      state.current_step === "recent_work" ||
      state.current_step === "job_meaning" ||
      state.current_step === "important_thing"
    ) {
      console.log("📚 온보딩 진행 중 - handleOnboarding 호출");
      // 온보딩 진행 중
      response = await handleOnboarding(userId, userMessage);
    } else if (state.current_step === "ai_intro") {
      console.log("📋 AI Agent 소개 단계 - 사용자 응답 대기");
      console.log("📨 사용자 응답:", userMessage);

      // ai_intro 단계에서 사용자가 응답하면 ai_conversation으로 전환
      // 사용자 이름 가져오기
      const { data: user } = await supabase
        .from("users")
        .select("name")
        .eq("kakao_user_id", userId)
        .single();

      const userName = user?.name || "사용자";
      console.log("👤 사용자 이름:", userName);

      // ai_conversation 단계로 전환
      const { error: updateError } = await supabase
        .from("conversation_states")
        .update({
          current_step: "ai_conversation",
          temp_data: {
            ...state.temp_data,
            conversation_history: [
              {
                role: "assistant",
                content: `안녕하세요, 반가워요 ${userName}님! 😊\n오늘도 "3분 커리어"와 함께하러 오셨군요.\n바로 시작해볼까요?\n\n오늘 어떤 업무를 하셨는지 공유해주실 수 있나요?\n말씀해주시면 이력을 위한 메모로 정리하고, 더 임팩트 있는 표현을 위해 질문도 함께 드릴게요!`,
              },
              { role: "user", content: userMessage },
            ],
          },
          updated_at: new Date(),
        })
        .eq("kakao_user_id", userId)
        .eq("current_step", "ai_intro");

      if (updateError) {
        console.error("❌ ai_conversation 단계 전환 실패:", updateError);
      } else {
        console.log("✅ ai_conversation 단계로 성공적으로 전환됨");
      }

      // 상태 전환 후 즉시 AI Agent와 대화 시작 (별도 상태 조회 없이)
      console.log("🤖 AI Agent 대화 시작 - 직접 처리");

      // ChatGPT API 직접 호출
      try {
        // 새로운 프롬프트를 활용한 대화 시작
        const introMessage = `안녕하세요, 반가워요 ${userName}님! 😊\n\n오늘도 "3분 커리어"와 함께하러 오셨군요. 바로 시작해볼까요?\n\n오늘 어떤 업무를 하셨는지 공유해주실 수 있나요? 말씀해주시면 이력을 위한 메모로 정리하고, 더 임팩트 있는 표현을 위해 질문도 함께 드릴게요!`;

        const conversationHistory = [
          { role: "assistant", content: introMessage },
          { role: "user", content: userMessage },
        ];

        console.log("🤖 ChatGPT API 호출 중...");
        const aiResponse = await callChatGPT(userMessage, conversationHistory);
        console.log("✅ ChatGPT 응답 받음:", aiResponse);

        // 대화 히스토리 업데이트
        const updatedHistory = [
          ...conversationHistory,
          { role: "assistant", content: aiResponse },
        ];

        // 데이터베이스 업데이트
        await supabase
          .from("conversation_states")
          .update({
            temp_data: {
              ...state.temp_data,
              conversation_history: updatedHistory,
            },
            updated_at: new Date(),
          })
          .eq("kakao_user_id", userId)
          .eq("current_step", "ai_conversation");

        response = {
          version: "2.0",
          template: {
            outputs: [
              {
                simpleText: {
                  text: aiResponse,
                },
              },
            ],
          },
        };
      } catch (error) {
        console.error("❌ AI 응답 생성 실패:", error);
        response = {
          version: "2.0",
          template: {
            outputs: [
              {
                simpleText: {
                  text: "AI 응답을 생성하는 중 오류가 발생했습니다. 다시 시도해주세요.",
                },
              },
            ],
          },
        };
      }
    } else if (state.current_step === "ai_conversation") {
      console.log("🤖 AI Agent 대화 진행 중 - handleAIConversation 호출");
      // AI Agent 대화 진행 중
      response = await handleAIConversation(userId, userMessage);
    } else {
      // 알 수 없는 상태 - 초기화 후 웰컴으로
      console.log("Unknown state, clearing:", state.current_step);
      await supabase
        .from("conversation_states")
        .delete()
        .eq("kakao_user_id", userId);
      response = await handleWelcome(userId);
    }
  } else {
    // 진행 중인 대화가 없을 때만 액션에 따라 처리
    // action.name은 무시하고 userMessage로 판단
    if (userMessage === "온보딩 시작" || userMessage === "온보딩") {
      response = await handleOnboarding(userId, userMessage);
    } else if (
      userMessage === "오늘의 3분 커리어 시작!" ||
      userMessage.includes("3분 커리어")
    ) {
      // AI Agent 대화 시작 - ai_intro 단계로 설정
      await supabase.from("conversation_states").upsert({
        kakao_user_id: userId,
        current_step: "ai_intro",
        temp_data: {},
        updated_at: new Date(),
      });
      response = await handleAIConversation(userId, userMessage);
    } else if (userMessage === "웰컴" || userMessage === "메인") {
      response = await handleWelcome(userId);
    } else {
      // 기본적으로 웰컴으로
      response = await handleWelcome(userId);
    }
  }

  return response;
}

// 웹훅 엔드포인트 - 대화 연속성 수정
app.post("/webhook", async (req, res) => {
  try {
    console.log("📨 웹훅 요청 수신");

    const { userRequest, action } = req.body;

    // 웹훅 요청 처리 함수 호출
    const response = await handleWebhookRequest(userRequest, action);

    res.json(response);
  } catch (error) {
    console.error("Webhook error:", error);
    res.status(500).json({
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            },
          },
        ],
      },
    });
  }
});

// 환영 메시지 처리
async function handleWelcome(userId) {
  const { data: user } = await supabase
    .from("users")
    .select("*")
    .eq("kakao_user_id", userId)
    .single();

  if (!user) {
    // 신규 사용자
    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "안녕하세요! 3분커리어 온보딩봇입니다.\n먼저 간단한 정보를 입력해주세요.",
            },
          },
        ],
        quickReplies: [
          {
            label: "시작하기",
            action: "message",
            messageText: "온보딩 시작",
          },
        ],
      },
    };
  } else if (!user.onboarding_completed) {
    // 온보딩 미완료
    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "온보딩을 완료해주세요.",
            },
          },
        ],
        quickReplies: [
          {
            label: "온보딩계속",
            action: "message",
            messageText: "온보딩 계속",
          },
        ],
      },
    };
  } else {
    // 기존 사용자
    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `안녕하세요 ${user.name}님!\n온보딩이 완료되었습니다! 🎉`,
            },
          },
        ],
        quickReplies: [
          {
            label: "완료",
            action: "message",
            messageText: "완료",
          },
        ],
      },
    };
  }
}

// 온보딩 처리
async function handleOnboarding(userId, message) {
  // 사용자 정보 먼저 확인
  const { data: user } = await supabase
    .from("users")
    .select("*")
    .eq("kakao_user_id", userId)
    .single();

  // 온보딩 완료된 사용자는 AI 대화 모드로 직접 진입
  if (user && user.onboarding_completed) {
    // AI 대화 모드로 직접 진입
    return await handleAIConversation(userId, "오늘의 3분 커리어 시작!");
  }

  // 현재 온보딩 단계 확인
  const { data: state } = await supabase
    .from("conversation_states")
    .select("*")
    .eq("kakao_user_id", userId)
    .single();

  if (!state || !state.current_step) {
    console.log("🚀 새로운 온보딩 시작 - 상태 생성 중...");
    // 온보딩 시작 단계
    const { data: insertResult, error: insertError } = await supabase
      .from("conversation_states")
      .upsert({
        kakao_user_id: userId,
        current_step: "onboarding_start",
        temp_data: {},
        updated_at: new Date(),
      });

    if (insertError) {
      console.error("❌ 상태 생성 실패:", insertError);
    } else {
      console.log("✅ 상태 생성 성공:", insertResult);
    }

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: "안녕하세요! <3분커리어>입니다. 😊\n\n당신의 커리어 성장을 위해, 몇 가지 질문으로 시작할게요. 편하게 답변해주세요!",
            },
          },
        ],
        quickReplies: [
          {
            label: "네 알겠습니다!",
            action: "message",
            messageText: "네 알겠습니다!",
          },
        ],
      },
    };
  }

  if (state.current_step === "onboarding_start") {
    console.log("🎯 onboarding_start 단계 처리 중...");
    console.log("사용자 메시지:", message);

    // "네 알겠습니다!" 메시지인 경우에만 다음 단계로 진행
    if (message === "네 알겠습니다!" || message.includes("알겠습니다")) {
      console.log('✅ "네 알겠습니다!" 감지, name_input으로 진행');

      // 이름 입력 단계
      await supabase
        .from("conversation_states")
        .update({
          current_step: "name_input",
          updated_at: new Date(),
        })
        .eq("kakao_user_id", userId);

      return {
        version: "2.0",
        template: {
          outputs: [
            {
              simpleText: {
                text: "당신을 어떻게 부르면 될까요? 이름이나 별명을 알려주세요!",
              },
            },
          ],
        },
      };
    } else {
      console.log('❌ "네 알겠습니다!"가 아님, 현재 단계 유지');
      // 다른 메시지인 경우 현재 단계 유지
      return {
        version: "2.0",
        template: {
          outputs: [
            {
              simpleText: {
                text: "온보딩을 시작하려면 '네 알겠습니다!'라고 답변해주세요.",
              },
            },
          ],
        },
      };
    }
  }

  if (state.current_step === "name_input") {
    // 직무 입력 단계로
    await supabase
      .from("conversation_states")
      .update({
        current_step: "job_input",
        temp_data: { name: message },
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `좋습니다! 먼저 당신에 대해 알려주세요.\n\n현재 직무는 무엇인가요? (예: 서비스 기획자, 개발자)`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "job_input") {
    // 총 연차 입력 단계로
    const tempData = { ...state.temp_data, job_title: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "total_years",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `총 연차는 어떻게 되세요? (예: 5년차, 10년차)`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "total_years") {
    // 직무 연차 입력 단계로
    const tempData = { ...state.temp_data, total_years: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "job_years",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `현재 직무 연차는 어떻게 되세요? (예: 3년차, 7년차)`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "job_years") {
    // 커리어 목표 입력 단계로
    const tempData = { ...state.temp_data, job_years: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "career_goal",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `앞으로의 커리어 목표는 무엇인가요? (예: 1년 내 PM으로 성장, 특정 기술 전문 자격증 취득)`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "career_goal") {
    // 프로젝트명 입력 단계로
    const tempData = { ...state.temp_data, career_goal: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "project_name",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `좋은 목표네요! 지금 어떤 프로젝트를 진행 중이신가요?\n\n현재 진행 중인 프로젝트명과 목표를 알려주세요. 여러 개라면 모두 입력해주세요!\n\n입력 예시는 다음과 같아요:\n✅ 프로젝트명: A 서비스 리뉴얼\n🎯 목표: 재방문율 10% 증가`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "project_name") {
    // 최근 업무 입력 단계로
    const tempData = { ...state.temp_data, project_name: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "recent_work",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `알겠습니다. 이 외에 최근에 주로 하는 업무가 있다면 말씀해주세요. (예: 주간 회의 준비, 새 비즈니스 모델 조사)`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "recent_work") {
    // 직무 의미 입력 단계로
    const tempData = { ...state.temp_data, recent_work: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "job_meaning",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `답변 감사합니다! 당신의 직무와 업무를 더 이해하기 위해 질문 드릴게요.\n\n당신에게 ${tempData.job_title}란 어떤 의미인가요?`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "job_meaning") {
    // 중요하게 생각하는 것 입력 단계로
    const tempData = { ...state.temp_data, job_meaning: message };
    await supabase
      .from("conversation_states")
      .update({
        current_step: "important_thing",
        temp_data: tempData,
        updated_at: new Date(),
      })
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `${tempData.recent_work}를 할 때 가장 중요하게 생각하는 것은 무엇인가요?`,
            },
          },
        ],
      },
    };
  }

  if (state.current_step === "important_thing") {
    // 온보딩 완료
    const tempData = { ...state.temp_data, important_thing: message };

    // 사용자 정보 저장 - 키워드 추출 적용
    const { data: userResult, error: userError } = await supabase
      .from("users")
      .upsert({
        kakao_user_id: userId,
        name: tempData.name,
        job_title: extractJobTitle(tempData.job_title),
        total_years: extractYears(tempData.total_years),
        job_years: extractYears(tempData.job_years),
        career_goal: extractCareerGoal(tempData.career_goal),
        project_name: extractProjectName(tempData.project_name),
        recent_work: extractRecentWork(tempData.recent_work),
        job_meaning: extractJobMeaning(tempData.job_meaning),
        important_thing: tempData.important_thing, // 이미 짧은 키워드
        onboarding_completed: true,
      });

    if (userError) {
      console.error("Error creating user:", userError);
      return {
        version: "2.0",
        template: {
          outputs: [
            {
              simpleText: {
                text: "사용자 정보 저장 중 오류가 발생했습니다. 다시 시도해주세요.",
              },
            },
          ],
        },
      };
    }

    // 상태 초기화
    await supabase
      .from("conversation_states")
      .delete()
      .eq("kakao_user_id", userId);

    return {
      version: "2.0",
      template: {
        outputs: [
          {
            simpleText: {
              text: `답변 고맙습니다! 당신의 정보로 <3분커리어>가 최적화되었어요.\n\n내일부터 본격적으로 <3분커리어>를 이용하실 수 있습니다.\n\n매일 아침 맞춤 정보나 질문을 드릴게요!\n\n궁금한 점은 언제든지 질문해주세요. 그럼 내일 만나요! 😊`,
            },
          },
        ],
        quickReplies: [
          {
            label: "완료",
            action: "message",
            messageText: "완료",
          },
        ],
      },
    };
  }

  // 알 수 없는 상태인 경우
  console.log(`Unknown onboarding state for user ${userId}:`, state);

  // 상태 초기화 후 다시 시작
  await supabase
    .from("conversation_states")
    .delete()
    .eq("kakao_user_id", userId);

  return {
    version: "2.0",
    template: {
      outputs: [
        {
          simpleText: {
            text: "온보딩 상태에 문제가 있어 초기화했습니다. 다시 시작해주세요.",
          },
        },
      ],
      quickReplies: [
        {
          label: "다시시작",
          action: "message",
          messageText: "온보딩 시작",
        },
      ],
    },
  };
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`🚀 서버가 포트 ${PORT}에서 실행 중입니다.`);

  // 서버 시작 후 DB 연결 테스트
  const dbConnected = await testSupabaseConnection();

  if (dbConnected) {
    console.log("🎉 모든 시스템이 정상적으로 작동 중입니다!");
  } else {
    console.log("⚠️ DB 연결에 문제가 있습니다.");
  }
});
