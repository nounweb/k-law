"""
config.py — 고팡 환경 설정
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

    # DeepSeek (OpenClaw)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    # PDV
    PDV_DB_PATH: str = os.getenv("PDV_DB_PATH", "./data/gopang_pdv.db")

    # 서버
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8443"))

    # IDDM
    IDDM_CONFIDENCE_THRESHOLD: int = 4   # 경고 발령 임계값
    IDDM_BLOCK_THRESHOLD: int = 7        # 전송 차단 옵션 임계값
    IDDM_AUTO_BLOCK_THRESHOLD: int = 9   # 자동 차단 임계값
    CONTEXT_WINDOW: int = 10             # PDV 컨텍스트 슬라이딩 윈도우

    def validate(self) -> None:
        """필수 설정값 검증"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        if not self.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY가 설정되지 않았습니다.")


config = Config()
