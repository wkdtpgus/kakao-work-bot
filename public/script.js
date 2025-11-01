// 전역 변수
let currentUserId = '2871c5895ca869ade588bd23a20e7842c52acb03053fbc6e77f757a681a0732475';//`test_user_${Date.now()}`;//
let conversationHistory = [];
let isTyping = false;

// DOM 요소
const chatMessages = document.getElementById("chatMessages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const sidebar = document.getElementById("sidebar");
const userInfo = document.getElementById("userInfo");
const conversationHistoryDiv = document.getElementById("conversationHistory");
const aiActivity = document.getElementById("aiActivity");
const apiLogs = document.getElementById("apiLogs");

// 초기화
document.addEventListener("DOMContentLoaded", function () {
  updateWelcomeTime();
  checkServerStatus();

  // Enter 키로 메시지 전송
  messageInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // 입력 필드 포커스
  messageInput.focus();
});

// 서버 상태 확인
async function checkServerStatus() {
  try {
    const response = await fetch("/api/status");
    if (response.ok) {
      updateStatus("connected", "연결됨");
    } else {
      updateStatus("disconnected", "연결 실패");
    }
  } catch (error) {
    updateStatus("disconnected", "서버 오프라인");
  }
}

// 상태 업데이트
function updateStatus(status, text) {
  statusDot.className = `status-dot ${status}`;
  statusText.textContent = text;
}

// 환영 메시지 시간 업데이트
function updateWelcomeTime() {
  const welcomeTime = document.getElementById("welcomeTime");
  if (welcomeTime) {
    welcomeTime.textContent = new Date().toLocaleTimeString("ko-KR");
  }
}

// 메시지 전송
async function sendMessage() {
  const message = messageInput.value.trim();
  if (!message || isTyping) return;

  // 사용자 메시지 표시
  addMessage(message, "user");
  messageInput.value = "";

  // 입력 비활성화
  setInputState(false);

  // 타이핑 인디케이터 표시
  showTypingIndicator();

  try {
    console.log("🚀 메시지 전송 시작:", message);

    // API 호출
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        userId: currentUserId,
        message: message,
      }),
    });

    console.log("📡 응답 상태:", response.status, response.statusText);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log("📥 서버 응답 (전체):", data);
    console.log("📥 응답 구조 체크:", {
      hasTemplate: !!data.template,
      hasOutputs: data.template?.outputs,
      firstOutput: data.template?.outputs?.[0],
      simpleText: data.template?.outputs?.[0]?.simpleText,
      text: data.template?.outputs?.[0]?.simpleText?.text
    });

    // 타이핑 인디케이터 제거
    console.log("⏳ 타이핑 인디케이터 제거 중...");
    hideTypingIndicator();

    // 봇 응답 표시
    if (data.template && data.template.outputs && data.template.outputs[0]?.simpleText?.text) {
      const botMessage = data.template.outputs[0].simpleText.text;
      console.log("✅ 봇 메시지 추출 성공:", botMessage.substring(0, 100));

      console.log("💬 메시지 추가 중...");
      addMessage(botMessage, "bot");
      console.log("✅ 메시지 추가 완료");

      // 대화 히스토리 업데이트
      conversationHistory.push({ role: "user", content: message });
      conversationHistory.push({ role: "assistant", content: botMessage });
      updateConversationHistory();

      // API 로그 업데이트
      updateApiLogs(data);
    } else {
      console.error("❌ 응답 형식 오류:", data);
      addMessage("죄송합니다. 응답을 처리하는 중 오류가 발생했습니다.", "bot");
    }
  } catch (error) {
    console.error("❌ 오류 발생:", error);
    console.error("❌ 오류 스택:", error.stack);
    hideTypingIndicator();
    addMessage(
      "서버와의 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
      "bot"
    );
  } finally {
    console.log("🏁 메시지 처리 완료");
    setInputState(true);
  }
}

// 빠른 메시지 전송
function sendQuickMessage(message) {
  messageInput.value = message;
  sendMessage();
}

// 메시지 추가
function addMessage(text, sender) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${sender}-message`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.innerHTML =
    sender === "bot"
      ? '<i class="fas fa-robot"></i>'
      : '<i class="fas fa-user"></i>';

  const content = document.createElement("div");
  content.className = "message-content";

  const messageText = document.createElement("div");
  messageText.className = "message-text";
  messageText.innerHTML = text.replace(/\n/g, "<br>");

  const messageTime = document.createElement("div");
  messageTime.className = "message-time";
  messageTime.textContent = new Date().toLocaleTimeString("ko-KR");

  content.appendChild(messageText);
  content.appendChild(messageTime);

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);

  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 타이핑 인디케이터 표시
function showTypingIndicator() {
  if (isTyping) return;

  isTyping = true;
  const typingDiv = document.createElement("div");
  typingDiv.className = "message bot-message typing-indicator";
  typingDiv.id = "typingIndicator";

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.innerHTML = '<i class="fas fa-robot"></i>';

  const content = document.createElement("div");
  content.className = "message-content";

  const typingDots = document.createElement("div");
  typingDots.className = "typing-indicator";
  typingDots.innerHTML =
    '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

  content.appendChild(typingDots);
  typingDiv.appendChild(avatar);
  typingDiv.appendChild(content);

  chatMessages.appendChild(typingDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 타이핑 인디케이터 제거
function hideTypingIndicator() {
  const typingIndicator = document.getElementById("typingIndicator");
  if (typingIndicator) {
    typingIndicator.remove();
  }
  isTyping = false;
}

// 입력 상태 설정
function setInputState(enabled) {
  messageInput.disabled = !enabled;
  sendButton.disabled = !enabled;

  if (enabled) {
    messageInput.focus();
  }
}

// 사이드바 토글
function toggleSidebar() {
  sidebar.classList.toggle("open");
}

// 대화 히스토리 업데이트
function updateConversationHistory() {
  if (conversationHistory.length === 0) {
    conversationHistoryDiv.innerHTML = "<p>대화가 시작되지 않았습니다.</p>";
    return;
  }

  let historyHtml = '<div class="conversation-list">';
  conversationHistory.forEach((msg, index) => {
    const role = msg.role === "user" ? "사용자" : "봇";
    const time = new Date().toLocaleTimeString("ko-KR");
    historyHtml += `
            <div class="conversation-item">
                <strong>${role}:</strong> ${msg.content.substring(0, 100)}${msg.content.length > 100 ? "..." : ""}
                <small>(${time})</small>
            </div>
        `;
  });
  historyHtml += "</div>";

  conversationHistoryDiv.innerHTML = historyHtml;
}

// API 로그 업데이트
function updateApiLogs(data) {
  const timestamp = new Date().toLocaleTimeString("ko-KR");
  const logEntry = {
    timestamp: timestamp,
    request: data,
    response: data,
  };

  let logsHtml = '<div class="api-logs">';
  logsHtml += `
        <div class="log-entry">
            <strong>[${timestamp}]</strong>
            <pre>${JSON.stringify(data, null, 2)}</pre>
        </div>
    `;
  logsHtml += "</div>";

  apiLogs.innerHTML = logsHtml;
}

// AI 활동 업데이트
function updateAiActivity(activity) {
  const timestamp = new Date().toLocaleTimeString("ko-KR");
  let activityHtml = '<div class="ai-activity">';
  activityHtml += `
        <div class="activity-item">
            <strong>[${timestamp}]</strong> ${activity}
        </div>
    `;
  activityHtml += "</div>";

  aiActivity.innerHTML = activityHtml;
}

// 사용자 정보 업데이트 (온보딩 완료 시)
function updateUserInfo(userData) {
  if (!userData) {
    userInfo.innerHTML = "<p>아직 온보딩이 완료되지 않았습니다.</p>";
    return;
  }

  let userHtml = '<div class="user-details">';
  userHtml += `<p><strong>이름:</strong> ${userData.name || "N/A"}</p>`;
  userHtml += `<p><strong>직무:</strong> ${userData.job_title || "N/A"}</p>`;
  userHtml += `<p><strong>총 연차:</strong> ${userData.total_years || "N/A"}</p>`;
  userHtml += `<p><strong>직무 연차:</strong> ${userData.job_years || "N/A"}</p>`;
  userHtml += `<p><strong>커리어 목표:</strong> ${userData.career_goal || "N/A"}</p>`;
  userHtml += `<p><strong>프로젝트:</strong> ${userData.project_name || "N/A"}</p>`;
  userHtml += `<p><strong>최근 업무:</strong> ${userData.recent_work || "N/A"}</p>`;
  userHtml += `<p><strong>직무 의미:</strong> ${userData.job_meaning || "N/A"}</p>`;
  userHtml += `<p><strong>중요한 것:</strong> ${userData.important_thing || "N/A"}</p>`;
  userHtml += "</div>";

  userInfo.innerHTML = userHtml;
}

// 주기적으로 서버 상태 확인
setInterval(checkServerStatus, 30000); // 30초마다

// 페이지 로드 시 사용자 정보 가져오기
async function loadUserInfo() {
  try {
    const response = await fetch(`/api/user/${currentUserId}`);
    if (response.ok) {
      const userData = await response.json();
      updateUserInfo(userData);
    }
  } catch (error) {
    console.error("사용자 정보 로드 실패:", error);
  }
}

// 초기 사용자 정보 로드
loadUserInfo();
