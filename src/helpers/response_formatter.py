from typing import Dict, Any

# 주의: 기존 온보딩 관련 헬퍼 함수들은 더 이상 사용되지 않음
# 현재는 database/user_repository.py의 함수들로 대체됨


def simple_text_response(text: str) -> Dict[str, Any]:
    """간단한 텍스트 응답"""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": text
                }
            }]
        }
    }


def error_response(error_message: str) -> Dict[str, Any]:
    """에러 응답"""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": error_message
                }
            }]
        }
    }
