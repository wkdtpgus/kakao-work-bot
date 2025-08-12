const express = require('express');
const cors = require('cors');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

// 루트 경로 추가 (테스트용)
app.get('/', (req, res) => {
  res.json({
    message: "카카오 업무기록 챗봇 서버가 정상 작동 중입니다.",
    endpoints: {
      webhook: "/webhook"
    },
    status: "running"
  });
});

// 웹훅 엔드포인트 - 대화 연속성 수정
app.post('/webhook', async (req, res) => {
  try {
    const { userRequest, action } = req.body;
    const userId = userRequest.user.id;
    const userMessage = userRequest.utterance;

    console.log('Action:', action);
    console.log('User message:', userMessage);
    
    const actionId = action.name;
    
    let response;

    // 🔥 핵심: 진행 중인 대화 상태를 먼저 확인
    const { data: state } = await supabase
      .from('conversation_states')
      .select('*')
      .eq('kakao_user_id', userId)
      .single();

        // 진행 중인 대화가 있으면 우선 처리
    if (state && state.current_step) {
      console.log('Found active conversation:', state.current_step);
      
      if (state.current_step === 'onboarding_start' || 
          state.current_step === 'name_input' || 
          state.current_step === 'job_input' || 
          state.current_step === 'total_years' ||
          state.current_step === 'job_years' ||
          state.current_step === 'career_goal' ||
          state.current_step === 'project_name' ||
          state.current_step === 'recent_work' ||
          state.current_step === 'job_meaning' ||
          state.current_step === 'important_thing') {
        // 온보딩 진행 중
        response = await handleOnboarding(userId, userMessage);
      } else if (state.current_step === 'work_content' || 
                 state.current_step === 'mood_input' || 
                 state.current_step === 'achievements') {
        // 업무 기록 진행 중
        response = await handleWorkRecord(userId, userMessage);
      } else {
        // 알 수 없는 상태 - 초기화 후 웰컴으로
        console.log('Unknown state, clearing:', state.current_step);
        await supabase.from('conversation_states').delete()
          .eq('kakao_user_id', userId);
        response = await handleWelcome(userId);
      }
    } else {
      // 진행 중인 대화가 없을 때만 액션에 따라 처리
      // action.name은 무시하고 userMessage로 판단
      if (userMessage === "온보딩 시작" || userMessage === "온보딩") {
        response = await handleOnboarding(userId, userMessage);
      } else if (userMessage === "업무 기록" || userMessage === "일일기록") {
        response = await handleDailyRecord(userId);
      } else if (userMessage === "웰컴" || userMessage === "메인") {
        response = await handleWelcome(userId);
      } else {
        // 기본적으로 웰컴으로
        response = await handleWelcome(userId);
      }
    }
    
    res.json(response);
  } catch (error) {
    console.error('Webhook error:', error);
    res.status(500).json({ 
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
          }
        }]
      }
    });
  }
});

// 환영 메시지 처리
async function handleWelcome(userId) {
  const { data: user } = await supabase
    .from('users')
    .select('*')
    .eq('kakao_user_id', userId)
    .single();

  if (!user) {
    // 신규 사용자
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "안녕하세요! 일일 업무 기록봇입니다.\n먼저 간단한 정보를 입력해주세요."
          }
        }],
        quickReplies: [{
          label: "시작하기",
          action: "message",
          messageText: "온보딩 시작"
        }]
      }
    };
  } else if (!user.onboarding_completed) {
    // 온보딩 미완료
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "온보딩을 완료해주세요."
          }
        }],
        quickReplies: [{
          label: "온보딩계속",
          action: "message",
          messageText: "온보딩 계속"
        }]
      }
    };
  } else {
    // 기존 사용자
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `안녕하세요 ${user.name}님!\n${user.attendance_count}일째 기록 중이시네요! 💪`
          }
        }],
        quickReplies: [
          {
            label: "업무기록",
            action: "message", 
            messageText: "업무 기록"
          },
          {
            label: "쉬기",
            action: "message",
            messageText: "쉬기"
          }
        ]
      }
    };
  }
}

// 온보딩 처리
async function handleOnboarding(userId, message) {
  // 사용자 정보 먼저 확인
  const { data: user } = await supabase
    .from('users')
    .select('*')
    .eq('kakao_user_id', userId)
    .single();

  // 이미 온보딩이 완료된 경우
  if (user && user.onboarding_completed) {
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `${user.name}님은 이미 온보딩이 완료되었습니다!`
          }
        }],
        quickReplies: [{
          label: "완료",
          action: "message",
          messageText: "완료"
        }]
      }
    };
  }

  // 현재 온보딩 단계 확인
  const { data: state } = await supabase
    .from('conversation_states')
    .select('*')
    .eq('kakao_user_id', userId)
    .single();

  if (!state || !state.current_step) {
    // 온보딩 시작 단계
    await supabase.from('conversation_states').upsert({
      kakao_user_id: userId,
      current_step: 'onboarding_start',
      temp_data: {},
      updated_at: new Date()
    });

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "안녕하세요! <3분커리어>입니다. 😊\n\n당신의 커리어 성장을 위해, 몇 가지 질문으로 시작할게요. 편하게 답변해주세요!"
          }
        }],
        quickReplies: [{
          label: "네 알겠습니다!",
          action: "message",
          messageText: "네 알겠습니다!"
        }]
      }
    };
  }

  if (state.current_step === 'onboarding_start') {
    // 이름 입력 단계
    await supabase.from('conversation_states').update({
      current_step: 'name_input',
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "당신을 어떻게 부르면 될까요? 이름이나 별명을 알려주세요!"
          }
        }]
      }
    };
  }

  if (state.current_step === 'name_input') {
    // 직무 입력 단계로
    await supabase.from('conversation_states').update({
      current_step: 'job_input',
      temp_data: { name: message },
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `좋습니다! 먼저 당신에 대해 알려주세요.\n\n현재 직무는 무엇인가요? (예: 서비스 기획자, 개발자)`
          }
        }]
      }
    };
  }

  if (state.current_step === 'job_input') {
    // 총 연차 입력 단계로
    const tempData = { ...state.temp_data, job_title: message };
    await supabase.from('conversation_states').update({
      current_step: 'total_years',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `총 연차는 어떻게 되세요? (예: 5년차, 10년차)`
          }
        }]
      }
    };
  }

  if (state.current_step === 'total_years') {
    // 직무 연차 입력 단계로
    const tempData = { ...state.temp_data, total_years: message };
    await supabase.from('conversation_states').update({
      current_step: 'job_years',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `현재 직무 연차는 어떻게 되세요? (예: 3년차, 7년차)`
          }
        }]
      }
    };
  }

  if (state.current_step === 'job_years') {
    // 커리어 목표 입력 단계로
    const tempData = { ...state.temp_data, job_years: message };
    await supabase.from('conversation_states').update({
      current_step: 'career_goal',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `앞으로의 커리어 목표는 무엇인가요? (예: 1년 내 PM으로 성장, 특정 기술 전문 자격증 취득)`
          }
        }]
      }
    };
  }

  if (state.current_step === 'career_goal') {
    // 프로젝트명 입력 단계로
    const tempData = { ...state.temp_data, career_goal: message };
    await supabase.from('conversation_states').update({
      current_step: 'project_name',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `좋은 목표네요! 지금 어떤 프로젝트를 진행 중이신가요?\n\n현재 진행 중인 프로젝트명과 목표를 알려주세요. 여러 개라면 모두 입력해주세요!\n\n입력 예시는 다음과 같아요:\n✅ 프로젝트명: A 서비스 리뉴얼\n🎯 목표: 재방문율 10% 증가`
          }
        }]
      }
    };
  }

  if (state.current_step === 'project_name') {
    // 최근 업무 입력 단계로
    const tempData = { ...state.temp_data, project_name: message };
    await supabase.from('conversation_states').update({
      current_step: 'recent_work',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `알겠습니다. 이 외에 최근에 주로 하는 업무가 있다면 말씀해주세요. (예: 주간 회의 준비, 새 비즈니스 모델 조사)`
          }
        }]
      }
    };
  }

  if (state.current_step === 'recent_work') {
    // 직무 의미 입력 단계로
    const tempData = { ...state.temp_data, recent_work: message };
    await supabase.from('conversation_states').update({
      current_step: 'job_meaning',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `답변 감사합니다! 당신의 직무와 업무를 더 이해하기 위해 질문 드릴게요.\n\n당신에게 ${tempData.job_title}란 어떤 의미인가요?`
          }
        }]
      }
    };
  }

  if (state.current_step === 'job_meaning') {
    // 중요하게 생각하는 것 입력 단계로
    const tempData = { ...state.temp_data, job_meaning: message };
    await supabase.from('conversation_states').update({
      current_step: 'important_thing',
      temp_data: tempData,
      updated_at: new Date()
    }).eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `${tempData.recent_work}를 할 때 가장 중요하게 생각하는 것은 무엇인가요?`
          }
        }]
      }
    };
  }

  if (state.current_step === 'important_thing') {
    // 온보딩 완료
    const tempData = { ...state.temp_data, important_thing: message };
    
    // 사용자 정보 저장
    const { data: userResult, error: userError } = await supabase.from('users').upsert({
      kakao_user_id: userId,
      name: tempData.name,
      job_title: tempData.job_title,
      total_years: tempData.total_years,
      job_years: tempData.job_years,
      career_goal: tempData.career_goal,
      project_name: tempData.project_name,
      recent_work: tempData.recent_work,
      job_meaning: tempData.job_meaning,
      important_thing: tempData.important_thing,
      onboarding_completed: true
    });
    
    if (userError) {
      console.error('Error creating user:', userError);
      return {
        version: "2.0",
        template: {
          outputs: [{
            simpleText: {
              text: "사용자 정보 저장 중 오류가 발생했습니다. 다시 시도해주세요."
            }
          }]
        }
      };
    }

    // 상태 초기화
    await supabase.from('conversation_states').delete()
      .eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `답변 고맙습니다! 당신의 정보로 <3분커리어>가 최적화되었어요.\n\n내일부터 본격적으로 <3분커리어>를 이용하실 수 있습니다.\n\n매일 아침 맞춤 정보나 질문을 드릴게요!\n\n궁금한 점은 언제든지 질문해주세요. 그럼 내일 만나요! 😊`
          }
        }],
        quickReplies: [{
          label: "완료",
          action: "message",
          messageText: "완료"
        }]
      }
    };
  }

  // 알 수 없는 상태인 경우
  console.log(`Unknown onboarding state for user ${userId}:`, state);
  
  // 상태 초기화 후 다시 시작
  await supabase.from('conversation_states').delete()
    .eq('kakao_user_id', userId);

  return {
    version: "2.0",
    template: {
      outputs: [{
        simpleText: {
          text: "온보딩 상태에 문제가 있어 초기화했습니다. 다시 시작해주세요."
        }
      }],
      quickReplies: [{
        label: "다시시작",
        action: "message",
        messageText: "온보딩 시작"
      }]
    }
  };
}



const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});