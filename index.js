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
      
      if (state.current_step === 'name_input' || 
          state.current_step === 'job_input' || 
          state.current_step === 'project_input') {
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
      switch (actionId) {
        case '웰컴':
          response = await handleWelcome(userId);
          break;
        case '온보딩':
          response = await handleOnboarding(userId, userMessage);
          break;
        case '일일기록':
          response = await handleDailyRecord(userId);
          break;
        case '업무기록':
          response = await handleWorkRecord(userId, userMessage);
          break;
        default:
          response = {
            version: "2.0",
            template: {
              outputs: [{
                simpleText: {
                  text: `알 수 없는 명령입니다.\n받은 액션: ${actionId}\n메시지: ${userMessage}`
                }
              }]
            }
          };
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
          label: "업무기록",
          action: "message",
          messageText: "업무 기록"
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
    // 이름 입력 단계
    await supabase.from('conversation_states').upsert({
      kakao_user_id: userId,
      current_step: 'name_input',
      temp_data: {},
      updated_at: new Date()
    });

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "사용하실 닉네임을 입력해주세요."
          }
        }]
      }
    };
  }

  if (state.current_step === 'name_input') {
    console.log('Processing name_input step');
    console.log('User input name:', message);
    
    const { data: updateResult, error: updateError } = await supabase
      .from('conversation_states')
      .upsert({
        kakao_user_id: userId,
        current_step: 'job_input',
        temp_data: { name: message },
        updated_at: new Date()
      });
    
    if (updateError) {
      console.error('Error updating conversation state:', updateError);
      return {
        version: "2.0",
        template: {
          outputs: [{
            simpleText: {
              text: "데이터베이스 오류가 발생했습니다. 다시 시도해주세요."
            }
          }]
        }
      };
    }
    
    console.log('Update result:', updateResult);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `안녕하세요 ${message}님! 직무를 입력해주세요.`
          }
        }]
      }
    };
  }

  if (state.current_step === 'job_input') {
    const tempData = { ...state.temp_data, job_title: message };
    await supabase.from('conversation_states').upsert({
      kakao_user_id: userId,
      current_step: 'project_input',
      temp_data: tempData,
      updated_at: new Date()
    });

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "현재 진행 중인 주요 프로젝트를 입력해주세요."
          }
        }]
      }
    };
  }

  if (state.current_step === 'project_input') {
    // 온보딩 완료
    const tempData = { ...state.temp_data, project_name: message };
    
    // 사용자 정보 저장
    await supabase.from('users').upsert({
      kakao_user_id: userId,
      name: tempData.name,
      job_title: tempData.job_title,
      project_name: tempData.project_name,
      onboarding_completed: true
    });

    // 상태 초기화
    await supabase.from('conversation_states').delete()
      .eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `온보딩이 완료되었습니다! 🎉\n이제 일일 업무를 기록해보세요.`
          }
        }],
        quickReplies: [{
          label: "업무기록",
          action: "message",
          messageText: "업무 기록"
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

// 일일 기록 처리
async function handleDailyRecord(userId) {
  // 사용자 정보 확인
  const { data: user } = await supabase
    .from('users')
    .select('*')
    .eq('kakao_user_id', userId)
    .single();

  if (!user) {
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "사용자 정보를 찾을 수 없습니다. 온보딩을 먼저 진행해주세요."
          }
        }],
        quickReplies: [{
          label: "온보딩시작",
          action: "message",
          messageText: "온보딩 시작"
        }]
      }
    };
  }

  // 오늘 이미 기록했는지 확인
  const today = new Date().toISOString().split('T')[0];
  const { data: todayRecord } = await supabase
    .from('daily_records')
    .select('*')
    .eq('user_id', user.id)
    .eq('record_date', today)
    .single();

  if (todayRecord) {
    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "오늘은 이미 기록을 완료하셨습니다! ✅"
          }
        }],
        quickReplies: [{
          label: "메인으로",
          action: "message",
          messageText: "메인"
        }]
      }
    };
  }

  // 업무 기록 시작
  await supabase.from('conversation_states').upsert({
    kakao_user_id: userId,
    current_step: 'work_content',
    temp_data: {},
    updated_at: new Date()
  });

  return {
    version: "2.0",
    template: {
      outputs: [{
        simpleText: {
          text: "오늘 어떤 업무를 하셨나요? 간단히 작성해주세요."
        }
      }]
    }
  };
}

// 업무 내용 기록 처리
async function handleWorkRecord(userId, message) {
  const { data: state } = await supabase
    .from('conversation_states')
    .select('*')
    .eq('kakao_user_id', userId)
    .single();

  // 상태가 없거나 잘못된 경우 - daily_record로 리다이렉트
  if (!state || !state.current_step) {
    console.log('No state found, redirecting to daily record');
    return await handleDailyRecord(userId);
  }

  if (state.current_step === 'work_content') {
    // 기분 입력 단계로
    await supabase.from('conversation_states').upsert({
      kakao_user_id: userId,
      current_step: 'mood_input',
      temp_data: { work_content: message },
      updated_at: new Date()
    });

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "오늘 기분은 어떠셨나요?"
          }
        }],
        quickReplies: [
          { label: "😊좋음", action: "message", messageText: "좋음" },
          { label: "😐보통", action: "message", messageText: "보통" },
          { label: "😔안좋음", action: "message", messageText: "안좋음" }
        ]
      }
    };
  }

  if (state.current_step === 'mood_input') {
    // 성과 입력 단계로
    const tempData = { ...state.temp_data, mood: message };
    await supabase.from('conversation_states').upsert({
      kakao_user_id: userId,
      current_step: 'achievements',
      temp_data: tempData,
      updated_at: new Date()
    });

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: "오늘의 성과나 배운 점이 있다면 알려주세요."
          }
        }]
      }
    };
  }

  if (state.current_step === 'achievements') {
    // 기록 완료
    const tempData = { ...state.temp_data, achievements: message };
    
    // 사용자 정보 가져오기
    const { data: user } = await supabase
      .from('users')
      .select('*')
      .eq('kakao_user_id', userId)
      .single();

    if (!user) {
      return {
        version: "2.0",
        template: {
          outputs: [{
            simpleText: {
              text: "사용자 정보를 찾을 수 없습니다. 온보딩을 다시 진행해주세요."
            }
          }]
        }
      };
    }

    // 일일 기록 저장
    await supabase.from('daily_records').insert({
      user_id: user.id,
      work_content: tempData.work_content,
      mood: tempData.mood,
      achievements: tempData.achievements
    });

    // 출석 카운트 증가
    await supabase.from('users')
      .update({ attendance_count: user.attendance_count + 1 })
      .eq('id', user.id);

    // 상태 초기화
    await supabase.from('conversation_states').delete()
      .eq('kakao_user_id', userId);

    return {
      version: "2.0",
      template: {
        outputs: [{
          simpleText: {
            text: `기록이 완료되었습니다! 🎉\n${user.attendance_count + 1}일째 기록 중이시네요!\n내일도 화이팅! 💪`
          }
        }],
        quickReplies: [{
          label: "완료",
          action: "message",
          messageText: "메인"
        }]
      }
    };
  }

  // 알 수 없는 상태인 경우
  console.log(`Unknown work record state for user ${userId}:`, state);
  return {
    version: "2.0",
    template: {
      outputs: [{
        simpleText: {
          text: "상태를 알 수 없습니다. 다시 시작해주세요."
        }
      }],
      quickReplies: [{
        label: "업무기록",
        action: "message",
        messageText: "업무 기록"
      }]
    }
  };
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});