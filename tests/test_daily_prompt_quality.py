"""
Daily Prompt 경량화 버전 품질 테스트
골든 데이터셋 + LLM-as-a-Judge 평가 방식
"""
import asyncio
import os
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage
from src.utils.models import get_chat_llm

# GCP 인증 설정
project_root = Path(__file__).parent
credentials_path = project_root / "thetimecollabo-38646deba34a.json"
if credentials_path.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
    print(f"✅ GCP 인증 파일 설정: {credentials_path}")
else:
    print(f"⚠️ GCP 인증 파일을 찾을 수 없습니다: {credentials_path}")

# ============================================================================
# 골든 데이터셋: 실제 사용자 시나리오
# ============================================================================

CONVERSATION_TEST_CASES = [
    {
        "name": "간단한 작업 보고",
        "user_metadata": {"name": "김민수", "job_title": "백엔드 개발자"},
        "user_message": "오늘 API 개발했어",
        "context": {"history": []},
        "expected_behavior": {
            "asks_follow_up": True,
            "asks_about": ["구체적 기능", "목적", "방법"],
            "tone": "warm_professional",
            "length": "2-3_sentences"
        }
    },
    {
        "name": "상세한 작업 설명",
        "user_metadata": {"name": "이서연", "job_title": "프론트엔드 개발자"},
        "user_message": "사용자 인증 페이지를 리액트로 구현했어요. JWT 토큰 방식을 사용했고, 로그인 상태를 전역으로 관리하는 컨텍스트도 만들었어요",
        "context": {"history": []},
        "expected_behavior": {
            "asks_follow_up": True,
            "asks_about": ["결과", "어려움", "다음 단계"],
            "acknowledges_detail": True,
            "tone": "warm_professional"
        }
    },
    {
        "name": "사용자 부정 응답",
        "user_metadata": {"name": "박준호", "job_title": "데이터 분석가"},
        "user_message": "안했어",
        "context": {
            "history": [
                {"role": "assistant", "content": "데이터 시각화 작업도 하셨나요?"}
            ]
        },
        "expected_behavior": {
            "acknowledges_denial": True,
            "asks_clarification": True,
            "no_wrong_assumptions": True,
            "tone": "understanding"
        }
    },
    {
        "name": "인사/잡담",
        "user_metadata": {"name": "최유진", "job_title": "기획자"},
        "user_message": "안녕하세요!",
        "context": {"history": []},
        "expected_behavior": {
            "responds_warmly": True,
            "redirects_to_work": True,
            "mentions": "오늘 업무"
        }
    },
    {
        "name": "온보딩 재시작 요청",
        "user_metadata": {"name": "정민지", "job_title": "디자이너"},
        "user_message": "온보딩 다시",
        "context": {"history": []},
        "expected_behavior": {
            "prevents_restart": True,
            "mentions": "이미 완료",
            "redirects_to_work": True
        }
    }
]

SUMMARY_TEST_CASES = [
    {
        "name": "간단한 요약",
        "user_metadata": {"job_title": "개발자"},
        "conversation": "오늘 API 3개 개발했어요. 사용자 인증, 데이터 조회, 파일 업로드 API예요.",
        "expected_quality": {
            "includes_numbers": True,
            "under_900_chars": True,
            "has_encouragement": True,
            "has_suggestions": 2,
            "no_markdown": True
        }
    },
    {
        "name": "부정 내용 포함",
        "user_metadata": {"job_title": "기획자"},
        "conversation": "오늘 요구사항 정의서 작성했어요. 와이어프레임도 그리려고 했는데 그건 안했어요. 시간이 부족했거든요.",
        "expected_quality": {
            "excludes_denied_content": True,  # 와이어프레임 제외
            "includes_only_completed": True,  # 요구사항 정의서만
            "under_900_chars": True,
            "has_suggestions": 2
        }
    },
    {
        "name": "수치 포함 상세 작업",
        "user_metadata": {"job_title": "데이터 분석가"},
        "conversation": "500건의 사용자 데이터를 분석해서 3가지 유형으로 분류했어요. 각 유형별로 특징을 정리하고 시각화 차트도 만들었어요.",
        "expected_quality": {
            "includes_numbers": True,  # 500건, 3가지
            "specific_achievements": True,
            "under_900_chars": True,
            "actionable_suggestions": True
        }
    }
]

# ============================================================================
# LLM-as-a-Judge 평가기
# ============================================================================

CONVERSATION_EVALUATION_PROMPT = """
You are an expert evaluator of AI chatbot responses.

# Task
Evaluate the chatbot's response to a user message based on the criteria below.

# User Context
- Message: "{user_message}"
- Expected Behavior: {expected_behavior}

# Chatbot Response
{bot_response}

# Evaluation Criteria (rate 1-5 for each)
1. **Follow-up Quality**: Does it ask relevant, thoughtful follow-up questions?
2. **Tone Appropriateness**: Is the tone warm, professional, and appropriate?
3. **Length**: Is it concise (2-3 sentences)?
4. **Context Awareness**: Does it properly handle denials, greetings, or special requests?
5. **Korean Quality**: Is the Korean natural and grammatically correct?

# Output Format (JSON)
{{
  "follow_up_quality": <1-5>,
  "tone": <1-5>,
  "length": <1-5>,
  "context_awareness": <1-5>,
  "korean_quality": <1-5>,
  "overall_score": <average>,
  "reasoning": "Brief explanation of scores"
}}
"""

SUMMARY_EVALUATION_PROMPT = """
You are an expert evaluator of career summaries.

# Task
Evaluate the quality of a career memo based on the criteria below.

# Original Conversation
{conversation}

# Generated Summary
{summary}

# Expected Quality
{expected_quality}

# Evaluation Criteria (rate 1-5 for each)
1. **Factual Accuracy**: Does it only include what the user confirmed? Excludes denied content?
2. **Conciseness**: Is it under 900 Korean characters?
3. **Specificity**: Does it include specific numbers, methods, and outcomes?
4. **Format Compliance**: Emojis (📝, 💡) are ALLOWED. Check: no bold (**text**), no headers (#), no bullets (*/-). Correct structure?
5. **Actionability**: Are the next-day suggestions concrete and useful?
6. **Korean Quality**: Natural, professional Korean with ~함 style?

# Output Format (JSON)
{{
  "factual_accuracy": <1-5>,
  "conciseness": <1-5>,
  "specificity": <1-5>,
  "format_compliance": <1-5>,
  "actionability": <1-5>,
  "korean_quality": <1-5>,
  "overall_score": <average>,
  "character_count": <actual count>,
  "reasoning": "Brief explanation of scores"
}}
"""

# ============================================================================
# Pairwise Comparison 평가 (개선 방법 #1)
# ============================================================================

PAIRWISE_CONVERSATION_PROMPT = """
You are an expert evaluator comparing two AI chatbot responses.

# Task
Compare Response A and Response B, then choose which is better.

# User Context
- Message: "{user_message}"
- Expected Behavior: {expected_behavior}

# Response A
{response_a}

# Response B
{response_b}

# Comparison Criteria
1. **Follow-up Quality**: Which asks more thoughtful, relevant questions?
2. **Tone**: Which has a more appropriate warm/professional tone?
3. **Length**: Which is more concise (2-3 sentences)?
4. **Context Awareness**: Which better handles the specific situation (denial/greeting/etc)?
5. **Korean Quality**: Which has more natural, grammatical Korean?

# Output Format (JSON)
{{
  "winner": "A" | "B" | "Tie",
  "confidence": "high" | "medium" | "low",
  "better_at": {{
    "follow_up_quality": "A" | "B" | "Tie",
    "tone": "A" | "B" | "Tie",
    "length": "A" | "B" | "Tie",
    "context_awareness": "A" | "B" | "Tie",
    "korean_quality": "A" | "B" | "Tie"
  }},
  "reasoning": "Brief explanation of why the winner is better"
}}
"""

PAIRWISE_SUMMARY_PROMPT = """
You are an expert evaluator comparing two career summaries.

# Task
Compare Summary A and Summary B, then choose which is better.

# Original Conversation
{conversation}

# Summary A
{summary_a}

# Summary B
{summary_b}

# Expected Quality
{expected_quality}

# Comparison Criteria
1. **Factual Accuracy**: Which better includes only confirmed content and excludes denials?
2. **Conciseness**: Which is more concise while staying under 900 chars?
3. **Specificity**: Which includes more specific numbers, methods, outcomes?
4. **Format Compliance**: Emojis (📝, 💡) are ALLOWED. Which better avoids forbidden Markdown (bold/headers/bullets) and follows structure?
5. **Actionability**: Which provides more concrete, useful next-day suggestions?
6. **Korean Quality**: Which has more natural, professional Korean?

# Output Format (JSON)
{{
  "winner": "A" | "B" | "Tie",
  "confidence": "high" | "medium" | "low",
  "better_at": {{
    "factual_accuracy": "A" | "B" | "Tie",
    "conciseness": "A" | "B" | "Tie",
    "specificity": "A" | "B" | "Tie",
    "format_compliance": "A" | "B" | "Tie",
    "actionability": "A" | "B" | "Tie",
    "korean_quality": "A" | "B" | "Tie"
  }},
  "reasoning": "Brief explanation of why the winner is better",
  "char_count_a": <count>,
  "char_count_b": <count>
}}
"""

# ============================================================================
# Chain-of-Thought 평가 (개선 방법 #3)
# ============================================================================

COT_CONVERSATION_PROMPT = """
You are an expert evaluator of AI chatbot responses. Use step-by-step reasoning.

# Task
Evaluate the chatbot's response using Chain-of-Thought reasoning.

# User Context
- Message: "{user_message}"
- Expected Behavior: {expected_behavior}

# Chatbot Response
{bot_response}

# Evaluation Process (Think step by step)

## Step 1: Analyze the user's situation
- What is the user trying to do?
- What does the expected behavior suggest?
- What would be an ideal response?

## Step 2: Evaluate each criterion (1-5 scale)
1. **Follow-up Quality**: Does it ask relevant, thoughtful questions?
   - Think: What questions would help the user reflect on their work?

2. **Tone Appropriateness**: Is it warm, professional, appropriate?
   - Think: Does this match the expected tone for a career mentor?

3. **Length**: Is it concise (2-3 sentences)?
   - Think: Count the sentences. Is it too verbose or too short?

4. **Context Awareness**: Does it handle denials/greetings/special requests properly?
   - Think: Does this response show understanding of the specific situation?

5. **Korean Quality**: Is the Korean natural and grammatically correct?
   - Think: Are there any awkward phrases or grammar errors?

## Step 3: Final judgment
- Calculate overall score
- Identify strengths and weaknesses
- Provide actionable feedback

# Output Format (JSON)
{{
  "step1_analysis": "Your analysis of the user's situation",
  "step2_reasoning": {{
    "follow_up_quality": {{"score": <1-5>, "reasoning": "..."}},
    "tone": {{"score": <1-5>, "reasoning": "..."}},
    "length": {{"score": <1-5>, "reasoning": "..."}},
    "context_awareness": {{"score": <1-5>, "reasoning": "..."}},
    "korean_quality": {{"score": <1-5>, "reasoning": "..."}}
  }},
  "step3_final": {{
    "overall_score": <average>,
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"],
    "actionable_feedback": "Specific suggestions for improvement"
  }}
}}
"""

COT_SUMMARY_PROMPT = """
You are an expert evaluator of career summaries. Use step-by-step reasoning.

# Task
Evaluate the career memo using Chain-of-Thought reasoning.

# Original Conversation
{conversation}

# Generated Summary
{summary}

# Expected Quality
{expected_quality}

# Evaluation Process (Think step by step)

## Step 1: Analyze the conversation
- What tasks did the user actually complete?
- What did they deny or say they didn't do?
- What specific details (numbers, methods) were mentioned?

## Step 2: Evaluate each criterion (1-5 scale)
1. **Factual Accuracy**: Only confirmed content, excludes denials?
   - Think: Cross-check each claim in summary against conversation

2. **Conciseness**: Under 900 Korean characters?
   - Think: Count characters. Is it concise yet complete?

3. **Specificity**: Includes specific numbers, methods, outcomes?
   - Think: Are details from conversation preserved?

4. **Format Compliance**: Emojis (📝, 💡) are ALLOWED. Check: no bold (**text**), no headers (#), no bullets (*/-). Correct structure?
   - Think: Are there any forbidden Markdown elements? (Emojis are OK)

5. **Actionability**: Concrete, useful next-day suggestions?
   - Think: Are suggestions specific enough to act on?

6. **Korean Quality**: Natural, professional, ~함 style?
   - Think: Is the Korean grammatical and appropriate?

## Step 3: Final judgment
- Calculate overall score
- Identify what's done well and what needs improvement
- Provide specific feedback

# Output Format (JSON)
{{
  "step1_analysis": {{
    "completed_tasks": ["task1", "task2"],
    "denied_tasks": ["task1"],
    "key_details": ["detail1", "detail2"]
  }},
  "step2_reasoning": {{
    "factual_accuracy": {{"score": <1-5>, "reasoning": "..."}},
    "conciseness": {{"score": <1-5>, "reasoning": "...", "char_count": <count>}},
    "specificity": {{"score": <1-5>, "reasoning": "..."}},
    "format_compliance": {{"score": <1-5>, "reasoning": "..."}},
    "actionability": {{"score": <1-5>, "reasoning": "..."}},
    "korean_quality": {{"score": <1-5>, "reasoning": "..."}}
  }},
  "step3_final": {{
    "overall_score": <average>,
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"],
    "actionable_feedback": "Specific suggestions for improvement"
  }}
}}
"""

# ============================================================================
# 테스트 실행 함수들
# ============================================================================

async def test_conversation_prompt(system_prompt: str, test_case: dict, prompt_name: str):
    """대화 프롬프트 테스트"""
    llm = get_chat_llm()

    # 프롬프트 렌더링
    rendered_prompt = system_prompt.format(
        name=test_case["user_metadata"]["name"],
        job_title=test_case["user_metadata"]["job_title"],
        total_years="3년",  # 테스트용 더미 데이터
        job_years="1년",
        career_goal="시니어 개발자",
        project_name="테스트 프로젝트",
        recent_work="챗봇 개발"
    )

    # LLM 응답 생성
    messages = [SystemMessage(content=rendered_prompt)]
    if test_case["context"].get("history"):
        for msg in test_case["context"]["history"]:
            messages.append(HumanMessage(content=msg["content"]))
    messages.append(HumanMessage(content=test_case["user_message"]))

    response = await llm.ainvoke(messages)
    bot_response = response.content

    # LLM Judge 평가
    eval_prompt = CONVERSATION_EVALUATION_PROMPT.format(
        user_message=test_case["user_message"],
        expected_behavior=test_case["expected_behavior"],
        bot_response=bot_response
    )

    eval_response = await llm.ainvoke([HumanMessage(content=eval_prompt)])

    # JSON 파싱 시도
    import json
    try:
        eval_json = json.loads(eval_response.content.replace("```json", "").replace("```", "").strip())
    except:
        eval_json = {"raw": eval_response.content}

    return {
        "test_name": test_case["name"],
        "prompt_version": prompt_name,
        "bot_response": bot_response,
        "evaluation": eval_json,
        "response_length": len(bot_response)
    }


async def test_summary_prompt(system_prompt: str, test_case: dict, prompt_name: str):
    """요약 프롬프트 테스트"""
    llm = get_chat_llm()

    # 요약 생성
    user_prompt = f"""
# USER_INFO
{test_case["user_metadata"]}

# CONVERSATION
{test_case["conversation"]}
"""

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ])

    summary = response.content
    char_count = len(summary)

    # LLM Judge 평가
    eval_prompt = SUMMARY_EVALUATION_PROMPT.format(
        conversation=test_case["conversation"],
        summary=summary,
        expected_quality=test_case["expected_quality"]
    )

    eval_response = await llm.ainvoke([HumanMessage(content=eval_prompt)])

    # JSON 파싱 시도
    import json
    try:
        eval_json = json.loads(eval_response.content.replace("```json", "").replace("```", "").strip())
    except:
        eval_json = {"raw": eval_response.content}

    return {
        "test_name": test_case["name"],
        "prompt_version": prompt_name,
        "summary": summary,
        "character_count": char_count,
        "evaluation": eval_json
    }


async def pairwise_comparison_test(prompt_a: str, prompt_b: str, test_case: dict, prompt_name_a: str, prompt_name_b: str):
    """Pairwise Comparison: 두 프롬프트의 응답을 직접 비교"""
    llm = get_chat_llm()

    # 프롬프트 A 응답 생성
    rendered_a = prompt_a.format(
        name=test_case["user_metadata"]["name"],
        job_title=test_case["user_metadata"]["job_title"],
        total_years="3년", job_years="1년",
        career_goal="시니어 개발자",
        project_name="테스트 프로젝트",
        recent_work="챗봇 개발"
    )
    messages_a = [SystemMessage(content=rendered_a), HumanMessage(content=test_case["user_message"])]
    response_a = await llm.ainvoke(messages_a)

    # 프롬프트 B 응답 생성
    rendered_b = prompt_b.format(
        name=test_case["user_metadata"]["name"],
        job_title=test_case["user_metadata"]["job_title"],
        total_years="3년", job_years="1년",
        career_goal="시니어 개발자",
        project_name="테스트 프로젝트",
        recent_work="챗봇 개발"
    )
    messages_b = [SystemMessage(content=rendered_b), HumanMessage(content=test_case["user_message"])]
    response_b = await llm.ainvoke(messages_b)

    # Pairwise 평가
    eval_prompt = PAIRWISE_CONVERSATION_PROMPT.format(
        user_message=test_case["user_message"],
        expected_behavior=test_case["expected_behavior"],
        response_a=response_a.content,
        response_b=response_b.content
    )
    eval_response = await llm.ainvoke([HumanMessage(content=eval_prompt)])

    import json
    try:
        eval_json = json.loads(eval_response.content.replace("```json", "").replace("```", "").strip())
    except:
        eval_json = {"raw": eval_response.content}

    return {
        "test_name": test_case["name"],
        "prompt_a_name": prompt_name_a,
        "prompt_b_name": prompt_name_b,
        "response_a": response_a.content,
        "response_b": response_b.content,
        "comparison": eval_json
    }


async def cot_evaluation_test(system_prompt: str, test_case: dict, is_summary: bool = False):
    """Chain-of-Thought Evaluation: 단계별 추론을 포함한 평가"""
    llm = get_chat_llm()

    if is_summary:
        # 요약 생성
        user_prompt = f"""
# USER_INFO
{test_case["user_metadata"]}

# CONVERSATION
{test_case["conversation"]}
"""
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        # CoT 평가
        eval_prompt = COT_SUMMARY_PROMPT.format(
            conversation=test_case["conversation"],
            summary=response.content,
            expected_quality=test_case["expected_quality"]
        )
    else:
        # 대화 응답 생성
        rendered = system_prompt.format(
            name=test_case["user_metadata"]["name"],
            job_title=test_case["user_metadata"]["job_title"],
            total_years="3년", job_years="1년",
            career_goal="시니어 개발자",
            project_name="테스트 프로젝트",
            recent_work="챗봇 개발"
        )
        messages = [SystemMessage(content=rendered), HumanMessage(content=test_case["user_message"])]
        response = await llm.ainvoke(messages)

        # CoT 평가
        eval_prompt = COT_CONVERSATION_PROMPT.format(
            user_message=test_case["user_message"],
            expected_behavior=test_case["expected_behavior"],
            bot_response=response.content
        )

    eval_response = await llm.ainvoke([HumanMessage(content=eval_prompt)])

    import json
    try:
        eval_json = json.loads(eval_response.content.replace("```json", "").replace("```", "").strip())
    except:
        eval_json = {"raw": eval_response.content}

    return {
        "test_name": test_case["name"],
        "bot_response": response.content,
        "cot_evaluation": eval_json
    }


async def main():
    """전체 테스트 실행"""

    # 프롬프트 import
    from src.prompt.daily_record_prompt import DAILY_CONVERSATION_SYSTEM_PROMPT as CONV_PROMPT
    from src.prompt.daily_summary_prompt import DAILY_SUMMARY_SYSTEM_PROMPT as SUM_PROMPT

    print("\n" + "="*70)
    print("📋 Daily Conversation Prompt 품질 테스트")
    print("="*70)

    conv_results = []
    for test_case in CONVERSATION_TEST_CASES:
        print(f"\n테스트: {test_case['name']}")
        result = await test_conversation_prompt(CONV_PROMPT, test_case, "경량화 버전")
        conv_results.append(result)

        print(f"  📨 사용자: {test_case['user_message']}")
        print(f"  🤖 봇 응답: {result['bot_response']}")
        print(f"  📏 응답 길이: {result['response_length']}자")

        if isinstance(result['evaluation'], dict):
            if 'overall_score' in result['evaluation']:
                print(f"  ⭐ 종합 점수: {result['evaluation']['overall_score']}/5")
                print(f"     - Follow-up 질문: {result['evaluation'].get('follow_up_quality', 'N/A')}/5")
                print(f"     - 톤: {result['evaluation'].get('tone', 'N/A')}/5")
                print(f"     - 길이: {result['evaluation'].get('length', 'N/A')}/5")
                print(f"     - 맥락 인식: {result['evaluation'].get('context_awareness', 'N/A')}/5")
                print(f"     - 한국어 품질: {result['evaluation'].get('korean_quality', 'N/A')}/5")
                if 'reasoning' in result['evaluation']:
                    print(f"  💭 평가 이유: {result['evaluation']['reasoning']}")
        else:
            print(f"  ⚠️ 평가 (파싱 실패): {str(result['evaluation'])[:200]}...")

    print("\n" + "="*70)
    print("📝 Daily Summary Prompt 품질 테스트")
    print("="*70)

    sum_results = []
    for test_case in SUMMARY_TEST_CASES:
        print(f"\n테스트: {test_case['name']}")
        result = await test_summary_prompt(SUM_PROMPT, test_case, "경량화 버전")
        sum_results.append(result)

        print(f"  💬 대화: {test_case['conversation']}")
        print(f"  📝 요약:")
        print("  " + "\n  ".join(result['summary'].split('\n')))
        print(f"  📏 글자 수: {result['character_count']}/900")

        if isinstance(result['evaluation'], dict):
            if 'overall_score' in result['evaluation']:
                print(f"  ⭐ 종합 점수: {result['evaluation']['overall_score']}/5")
                print(f"     - 사실 정확성: {result['evaluation'].get('factual_accuracy', 'N/A')}/5")
                print(f"     - 간결성: {result['evaluation'].get('conciseness', 'N/A')}/5")
                print(f"     - 구체성: {result['evaluation'].get('specificity', 'N/A')}/5")
                print(f"     - 형식 준수: {result['evaluation'].get('format_compliance', 'N/A')}/5")
                print(f"     - 실행가능성: {result['evaluation'].get('actionability', 'N/A')}/5")
                print(f"     - 한국어 품질: {result['evaluation'].get('korean_quality', 'N/A')}/5")
                if 'reasoning' in result['evaluation']:
                    print(f"  💭 평가 이유: {result['evaluation']['reasoning']}")
        else:
            print(f"  ⚠️ 평가 (파싱 실패): {str(result['evaluation'])[:200]}...")

    # 전체 결과 요약
    print("\n" + "="*70)
    print("📊 종합 평가 결과")
    print("="*70)

    # 대화 프롬프트 통계
    print(f"\n[대화 프롬프트]")
    print(f"  테스트 케이스: {len(conv_results)}개")
    print(f"  평균 응답 길이: {sum(r['response_length'] for r in conv_results) / len(conv_results):.0f}자")

    conv_scores = [r['evaluation'].get('overall_score', 0) for r in conv_results if isinstance(r['evaluation'], dict) and 'overall_score' in r['evaluation']]
    if conv_scores:
        print(f"  평균 품질 점수: {sum(conv_scores) / len(conv_scores):.2f}/5")
        print(f"  최고 점수: {max(conv_scores)}/5")
        print(f"  최저 점수: {min(conv_scores)}/5")

    # 요약 프롬프트 통계
    print(f"\n[요약 프롬프트]")
    print(f"  테스트 케이스: {len(sum_results)}개")
    print(f"  평균 글자 수: {sum(r['character_count'] for r in sum_results) / len(sum_results):.0f}/900")

    over_limit = [r for r in sum_results if r['character_count'] > 900]
    if over_limit:
        print(f"  ⚠️ 900자 초과: {len(over_limit)}건")
        for r in over_limit:
            print(f"     - {r['test_name']}: {r['character_count']}자")
    else:
        print(f"  ✅ 모든 요약이 900자 이내")

    sum_scores = [r['evaluation'].get('overall_score', 0) for r in sum_results if isinstance(r['evaluation'], dict) and 'overall_score' in r['evaluation']]
    if sum_scores:
        print(f"  평균 품질 점수: {sum(sum_scores) / len(sum_scores):.2f}/5")
        print(f"  최고 점수: {max(sum_scores)}/5")
        print(f"  최저 점수: {min(sum_scores)}/5")

    # 개선 포인트 분석
    print(f"\n[개선이 필요한 영역]")
    for result in conv_results:
        if isinstance(result['evaluation'], dict) and 'overall_score' in result['evaluation']:
            if result['evaluation']['overall_score'] < 4.0:
                print(f"  ⚠️ 대화: {result['test_name']} (점수: {result['evaluation']['overall_score']}/5)")

    for result in sum_results:
        if isinstance(result['evaluation'], dict) and 'overall_score' in result['evaluation']:
            if result['evaluation']['overall_score'] < 4.0:
                print(f"  ⚠️ 요약: {result['test_name']} (점수: {result['evaluation']['overall_score']}/5)")

    print("\n" + "="*70)
    print("✅ 품질 테스트 완료!")
    print("="*70)
    print("\n💡 다음 단계:")
    print("  1. 평가 결과를 검토하여 개선이 필요한 부분 파악")
    print("  2. 평균 점수 4.0 미만인 케이스 분석 및 프롬프트 미세 조정")
    print("  3. 실제 환경에 배포 전 A/B 테스트 고려")
    print("  4. 응답 시간 측정하여 경량화 효과 확인")

    # ========================================================================
    # 추가 평가 방법 시연 (Pairwise Comparison & Chain-of-Thought)
    # ========================================================================
    print("\n" + "="*70)
    print("🆚 Pairwise Comparison 테스트 (경량화 전/후 직접 비교)")
    print("="*70)
    print("\n💡 사용법: 두 프롬프트 버전을 직접 비교하려면 아래 주석을 해제하세요")
    print("""
# 예시: 경량화 전 프롬프트와 현재 프롬프트 비교
# ORIGINAL_PROMPT = '''기존 프롬프트 내용...'''
#
# for test_case in CONVERSATION_TEST_CASES[:2]:  # 샘플 2개만
#     result = await pairwise_comparison_test(
#         prompt_a=ORIGINAL_PROMPT,
#         prompt_b=CONV_PROMPT,
#         test_case=test_case,
#         prompt_name_a="경량화 전",
#         prompt_name_b="경량화 후"
#     )
#     print(f"\\n테스트: {result['test_name']}")
#     print(f"  승자: {result['comparison'].get('winner', 'N/A')}")
#     print(f"  신뢰도: {result['comparison'].get('confidence', 'N/A')}")
#     print(f"  이유: {result['comparison'].get('reasoning', 'N/A')}")
""")

    print("\n" + "="*70)
    print("🧠 Chain-of-Thought Evaluation 테스트 (단계별 추론 평가)")
    print("="*70)
    print("\n💡 사용법: 더 상세한 평가가 필요하면 아래 주석을 해제하세요")
    print("""
# 예시: CoT 평가로 더 깊은 인사이트 얻기
# for test_case in CONVERSATION_TEST_CASES[:1]:  # 샘플 1개만
#     result = await cot_evaluation_test(CONV_PROMPT, test_case, is_summary=False)
#     cot = result['cot_evaluation']
#
#     print(f"\\n테스트: {result['test_name']}")
#     if 'step1_analysis' in cot:
#         print(f"  [Step 1] 상황 분석: {cot['step1_analysis']}")
#     if 'step2_reasoning' in cot:
#         print(f"  [Step 2] 세부 평가:")
#         for criterion, data in cot['step2_reasoning'].items():
#             print(f"    - {criterion}: {data.get('score', 'N/A')}/5")
#             print(f"      이유: {data.get('reasoning', 'N/A')}")
#     if 'step3_final' in cot:
#         final = cot['step3_final']
#         print(f"  [Step 3] 최종 평가:")
#         print(f"    - 종합 점수: {final.get('overall_score', 'N/A')}/5")
#         print(f"    - 강점: {', '.join(final.get('strengths', []))}")
#         print(f"    - 약점: {', '.join(final.get('weaknesses', []))}")
#         print(f"    - 개선 제안: {final.get('actionable_feedback', 'N/A')}")
""")


if __name__ == "__main__":
    asyncio.run(main())
