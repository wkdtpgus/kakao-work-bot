"""
온보딩 질문 템플릿 및 검증 로직
LLM은 정보 추출만, 질문/검증은 시스템이 관리
"""

from typing import Callable, Dict, List, Optional


class FieldTemplate:
    """필드별 질문 템플릿 및 검증 규칙"""

    def __init__(
        self,
        field_name: str,
        first_attempt: str,
        second_attempt: str,
        third_attempt: str,
        validation: Optional[Callable[[str], bool]] = None,
        options: Optional[List[str]] = None
    ):
        self.field_name = field_name
        self.first_attempt = first_attempt
        self.second_attempt = second_attempt
        self.third_attempt = third_attempt
        self.validation = validation or (lambda x: len(x.strip()) > 0)
        self.options = options

    def get_question(self, attempt_count: int, name: Optional[str] = None) -> str:
        """시도 횟수에 따른 질문 반환

        Args:
            attempt_count: 시도 횟수 (1, 2, 3)
            name: 사용자 이름 (템플릿 내 {name} 치환용)
        """
        if attempt_count == 1:
            question = self.first_attempt
        elif attempt_count == 2:
            question = self.second_attempt
        else:  # 3회 이상
            question = self.third_attempt

        # 템플릿 내 {name} 치환 (name이 있을 때만)
        if name and "{name}" in question:
            return question.format(name=name)
        else:
            return question

    def validate(self, value: str) -> bool:
        """값 검증"""
        return self.validation(value)


# 검증 함수들
def validate_name(value: str) -> bool:
    """이름 검증: 1자 이상, 숫자만은 불가"""
    v = value.strip()
    return len(v) >= 1 and not v.isdigit()


def validate_years(value: str) -> bool:
    """연차 검증: 신입 또는 숫자 포함"""
    v = value.strip()
    return v == "신입" or any(char.isdigit() for char in v)


def validate_text(value: str) -> bool:
    """텍스트 검증: 비어있지 않으면 OK"""
    return len(value.strip()) >= 1


# 9개 필드 템플릿 정의
FIELD_TEMPLATES: Dict[str, FieldTemplate] = {
    "name": FieldTemplate(
        field_name="name",
        first_attempt="먼저, 이름을 알려주시겠어요? 실명이 아니어도 괜찮아요.\n예: '지은', '민수', 'Alex'",
        second_attempt="이름을 정확히 알려주시면 좋겠어요.\n실명이 아니어도 괜찮아요. 어떻게 불러드리면 될까요?",
        third_attempt="편하게 부를 수 있는 이름을 알려주세요.\n예: '지은', '민수', 'Alex'\n\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_name
    ),

    "job_title": FieldTemplate(
        field_name="job_title",
        first_attempt="좋아요 {name}님, 현재 어떤 일을 하고 계신가요? 직무나 직책을 알려주세요.\n예: '백엔드 개발자', 'UX 디자이너', '프로덕트 매니저', '퍼포먼스 마케터'",
        second_attempt="직무를 더 구체적으로 알려주시면 좋겠어요.\n예: '백엔드 개발자', 'UX 디자이너', '프로덕트 매니저', '퍼포먼스 마케터'",
        third_attempt="{name}님, 아래 예시처럼 직접 입력해주세요:\n예: '백엔드 개발자', 'UX 디자이너', '프로덕트 매니저', '퍼포먼스 마케터'\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=lambda x: len(x.strip()) >= 2 and not x.strip().isdigit()
    ),

    "total_years": FieldTemplate(
        field_name="total_years",
        first_attempt="{name}님, 현재 직무경력을 포함한 전체 경력 연차를 알려주세요.\n예: '5년', '1년 6개월', '신입'",
        second_attempt="{name}님, 전체 경력 연차를 알려주세요.\n예: '5년', '1년 6개월', '신입'",
        third_attempt="{name}님, 아래 예시처럼 입력해주세요:\n예: '5년', '1년 6개월', '신입'\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_years
    ),

    "job_years": FieldTemplate(
        field_name="job_years",
        first_attempt="그러면 {name}님의 현재 직무 경력은 얼마나 되시나요? 직무 전환 케이스를 고려한 질문이에요.\n예: '2년', '6개월', '신입'",
        second_attempt="{name}님, 현재 직무 경력을 다시 알려주세요.\n예: '2년', '6개월', '신입'",
        third_attempt="{name}님, 현재 직무 경력을 다음 예시처럼 입력해주세요:\n예: '2년', '6개월', '신입'\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_years
    ),

    "career_goal": FieldTemplate(
        field_name="career_goal",
        first_attempt="{name}님은 앞으로 어떤 커리어를 만들어가고 싶으세요? 미래의 목표나 방향성을 자유롭게 말씀해주세요.\n예: '시니어 개발자로 성장하고 싶어요', '나만의 서비스를 만들고 싶어요'",
        second_attempt="{name}님, 커리어 목표를 조금 더 구체적으로 알려주시면 좋겠어요.\n예: '시니어 개발자로 성장하고 싶어요', '나만의 서비스를 만들고 싶어요'",
        third_attempt="{name}님, 커리어 목표에 대해 간단히라도 말씀해주세요.\n예시:\n• 전문성을 키우고 싶어요\n• 팀을 리드하고 싶어요\n• 다양한 경험을 쌓고 싶어요\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_text
    ),

    "project_name": FieldTemplate(
        field_name="project_name",
        first_attempt="이제 {name}님의 업무가 궁금해요. 요즘 어떤 프로젝트나 업무를 하고 계신가요?\n예: '커머스 앱 리뉴얼', '신규 마케팅 캠페인', '사내 도구 개선'",
        second_attempt="{name}님, 현재 진행 중인 프로젝트 이름이나 내용을 알려주세요.\n간단히 설명해주셔도 괜찮아요.",
        third_attempt="{name}님, 현재 업무나 프로젝트에 대해 한 줄로 설명해주세요.\n예: '커머스 앱 리뉴얼', '신규 마케팅 캠페인', '사내 도구 개선'\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=lambda x: len(x.strip()) >= 3
    ),

    "recent_work": FieldTemplate(
        field_name="recent_work",
        first_attempt="{name}님의 관심사도 알려주세요. 최근에 했던 일 중 기억에 남는 게 있나요? 어떤 일이었는지 자세히 말씀해주세요.\n예:\n• 새로운 시도를 한 경험\n• 어려운 문제를 해결한 경험\n• 팀과 협업해서 목표를 달성한 경험",
        second_attempt="{name}님, 최근 업무 중 인상 깊었던 경험을 구체적으로 알려주세요.\n성공한 일이든 어려웠던 일이든 괜찮아요.",
        third_attempt="{name}님, 최근 업무 경험을 간단히 공유해주세요.\n예:\n• 새로운 기능을 성공적으로 출시했어요\n• 어려운 문제를 해결했어요\n• 팀과 협업해서 목표를 달성했어요\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_text
    ),

    "job_meaning": FieldTemplate(
        field_name="job_meaning",
        first_attempt="그러면 이 일이 {name}님에게 어떤 의미인가요? 일하는 이유나 동기에 대해 말씀해주세요.\n예:\n• 성장하는 게 좋아요\n• 문제를 해결하는 게 재밌어요\n• 생계를 위해서예요\n• 아직 잘 모르겠어요",
        second_attempt="{name}님, 현재 하는 일이 본인에게 어떤 의미인지 생각해보셨나요? 다시 솔직한 마음을 들려주세요.",
        third_attempt="{name}님, 일의 의미에 대해 간단히 말씀해주세요.\n예:\n• 성장하는 게 좋아요\n• 문제를 해결하는 게 재밌어요\n• 생계를 위해서예요\n• 아직 잘 모르겠어요\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_text
    ),

    "important_thing": FieldTemplate(
        field_name="important_thing",
        first_attempt="이제 마지막 질문이에요 {name}님! 일할 때 가장 중요하게 생각하는 가치를 알려주세요.\n예: '성장과 배움', '워라밸', '좋은 동료', '자율성', '보상'",
        second_attempt="{name}님, 업무에서 본인이 가장 가치있게 여기는 것이 무엇인지 간단히 알려주세요.\n예: '성장', '워라밸', '동료', '자율성'",
        third_attempt="{name}님, 일할 때 중요한 가치를 선택하거나 직접 말씀해주세요.\n예: '성장과 배움', '워라밸', '좋은 동료', '자율성'\n💡 건너뛰려면 '건너뛰기'라고 말해주세요.",
        validation=validate_text
    )
}


# 필드 순서 (온보딩 진행 순서)
FIELD_ORDER = [
    "name",
    "job_title",
    "total_years",
    "job_years",
    "career_goal",
    "project_name",
    "recent_work",
    "job_meaning",
    "important_thing"
]


def get_field_template(field_name: str) -> Optional[FieldTemplate]:
    """필드명으로 템플릿 조회"""
    return FIELD_TEMPLATES.get(field_name)


def get_next_field(metadata: dict) -> Optional[str]:
    """다음 수집할 필드 반환 (None이면 완료)"""
    for field_name in FIELD_ORDER:
        if metadata.get(field_name) is None:
            return field_name
    return None


def format_welcome_message(name: Optional[str] = None) -> str:
    """첫 온보딩 시작 메시지"""
    if name:
        return f"반가워요, {name}님! 앞으로 커리어를 함께 기록하고 돌아볼 수 있도록 도와드릴게요. 먼저 몇 가지 질문에 답해주시면, 맞춤형 피드백을 드릴 수 있어요."
    else:
        return "안녕하세요! 반가워요. 커리어를 기록하고 돌아보는 시간을 함께 만들어가는 <3분커리어>입니다. 시작하기 전에 몇 가지만 여쭤볼게요."


def format_completion_message(name: Optional[str] = None) -> str:
    """온보딩 완료 메시지"""
    if name:
        return f"좋아요, {name}님! 🎉\n이제 본격적으로 커리어 기록을 시작할 수 있어요. 언제든 오늘의 경험을 남기거나, 지난 주를 돌아볼 수 있습니다. 커리어 여정을 함께 기록해볼까요?\n\n아래 대시보드에서 자세한 작성 템플릿과 가이드를 확인할 수 있어요! \n[대시보드 링크]"
    else:
        return "좋아요! 🎉\n준비가 완료되었어요. 이제 본격적으로 커리어 기록을 시작할 수 있어요. 언제든 오늘의 경험을 남기거나, 지난 주를 돌아볼 수 있습니다. 커리어 여정을 함께 기록해볼까요?\n\n아래 대시보드에서 자세한 작성 템플릿과 가이드를 확인할 수 있어요! \n[대시보드 링크]"
