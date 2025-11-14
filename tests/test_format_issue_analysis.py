"""
Format Compliance 문제 상세 분석 (CoT 평가)
"""
import asyncio
import os
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage
from src.utils.models import get_chat_llm
from test_daily_prompt_quality import COT_SUMMARY_PROMPT, SUMMARY_TEST_CASES

# GCP 인증 설정
project_root = Path(__file__).parent
credentials_path = project_root / "thetimecollabo-38646deba34a.json"
if credentials_path.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)

async def analyze_format_issue():
    """Format Compliance 문제가 발생한 케이스를 CoT로 상세 분석"""
    from src.prompt.daily_summary_prompt import DAILY_SUMMARY_SYSTEM_PROMPT as SUM_PROMPT

    # 문제가 발생한 케이스 (부정 내용 포함 - 점수 3.8)
    test_case = SUMMARY_TEST_CASES[1]

    llm = get_chat_llm()

    # 요약 생성
    user_prompt = f"""
# USER_INFO
{test_case["user_metadata"]}

# CONVERSATION
{test_case["conversation"]}
"""

    response = await llm.ainvoke([
        SystemMessage(content=SUM_PROMPT),
        HumanMessage(content=user_prompt)
    ])

    summary = response.content

    print("="*70)
    print("📝 생성된 요약:")
    print("="*70)
    print(summary)
    print(f"\n글자 수: {len(summary)}")

    # CoT 평가
    eval_prompt = COT_SUMMARY_PROMPT.format(
        conversation=test_case["conversation"],
        summary=summary,
        expected_quality=test_case["expected_quality"]
    )

    eval_response = await llm.ainvoke([HumanMessage(content=eval_prompt)])

    import json
    try:
        cot = json.loads(eval_response.content.replace("```json", "").replace("```", "").strip())
    except:
        print("\n⚠️ JSON 파싱 실패")
        print(eval_response.content)
        return

    print("\n" + "="*70)
    print("🧠 Chain-of-Thought 분석 결과")
    print("="*70)

    if 'step1_analysis' in cot:
        print("\n[Step 1] 대화 분석:")
        analysis = cot['step1_analysis']
        print(f"  완료한 작업: {analysis.get('completed_tasks', 'N/A')}")
        print(f"  부정한 작업: {analysis.get('denied_tasks', 'N/A')}")
        print(f"  핵심 디테일: {analysis.get('key_details', 'N/A')}")

    if 'step2_reasoning' in cot:
        print("\n[Step 2] 세부 평가:")
        for criterion, data in cot['step2_reasoning'].items():
            print(f"\n  {criterion}: {data.get('score', 'N/A')}/5")
            print(f"  → {data.get('reasoning', 'N/A')}")

    if 'step3_final' in cot:
        final = cot['step3_final']
        print("\n[Step 3] 최종 판단:")
        print(f"  종합 점수: {final.get('overall_score', 'N/A')}/5")
        print(f"  강점: {', '.join(final.get('strengths', []))}")
        print(f"  약점: {', '.join(final.get('weaknesses', []))}")
        print(f"\n  💡 개선 제안:")
        print(f"  {final.get('actionable_feedback', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(analyze_format_issue())
