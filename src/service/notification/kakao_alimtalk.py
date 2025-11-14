"""카카오 알림톡 발송 서비스"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


async def schedule_weekly_summary_notification(user_id: str, send_time: str):
    """주간요약 알림톡 예약 발송

    Args:
        user_id: 카카오 사용자 ID
        send_time: 발송 시간 (ISO format: "2025-01-11T18:00:00")
    """
    try:
        # TODO: 실제 카카오 알림톡 API 연동
        # 참고: https://ssodaa.com/service/api/kakaoapi

        # 예시 코드:
        # import requests
        # response = requests.post(
        #     "https://api.kakao.com/v2/api/talk/alimtalk/send",
        #     headers={"Authorization": f"Bearer {API_KEY}"},
        #     json={
        #         "receiver_id": user_id,
        #         "template_code": "WEEKLY_SUMMARY_READY",
        #         "message": "주간요약이 생성되었어요! 확인하시겠어요?",
        #         "send_time": send_time,  # 예약 발송 시간
        #         "buttons": [
        #             {
        #                 "label": "주간요약 보기",
        #                 "type": "WL",
        #                 "url_mobile": "kakao://..."
        #             }
        #         ]
        #     }
        # )
        # logger.info(f"[AlimTalk] API 응답: {response.json()}")

        logger.info(f"[AlimTalk] 주간요약 알림톡 예약 완료: user_id={user_id}, send_time={send_time}")

    except Exception as e:
        logger.error(f"[AlimTalk] 알림톡 발송 실패: {e}")
        raise


def calculate_next_saturday_6pm() -> str:
    """다음 토요일 오후 6시 계산

    Returns:
        ISO format 날짜 문자열 (예: "2025-01-11T18:00:00")
    """
    now = datetime.now()
    current_weekday = now.weekday()  # 0=월, 5=토, 6=일

    # 토요일까지 남은 일수 계산
    days_until_saturday = (5 - current_weekday) % 7

    # 이미 토요일이면 다음 주 토요일
    if days_until_saturday == 0:
        days_until_saturday = 7

    next_saturday = now + timedelta(days=days_until_saturday)

    # 오후 6시로 설정
    saturday_6pm = next_saturday.replace(hour=18, minute=0, second=0, microsecond=0)

    return saturday_6pm.isoformat()
