"""
Application configuration.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from app.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Load .env explicitly from the project root.
# override=True ensures values from .env replace any existing
# environment variables (important when launched by AnythingLLM).
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

load_dotenv(
    dotenv_path=ENV_FILE,
    override=True,
)


class Settings:
    """
    Application settings.
    """

    def __init__(self):

        logger.info("Loading configuration")

        self.SERPER_API_KEY = os.getenv(
            "SERPER_API_KEY",
            "",
        ).strip()

        self.SERPER_ENDPOINT = os.getenv(
            "SERPER_ENDPOINT",
            "https://google.serper.dev/search",
        )

        self.REQUEST_TIMEOUT = int(
            os.getenv(
                "REQUEST_TIMEOUT",
                "30",
            )
        )

        self.LOG_LEVEL = os.getenv(
            "LOG_LEVEL",
            "DEBUG",
        )

        self.validate()

        logger.info("Configuration loaded successfully")

        logger.info("Project Root : %s", BASE_DIR)
        logger.info("Environment File : %s", ENV_FILE)

        masked = (
            self.SERPER_API_KEY[:6]
            + "..."
            + self.SERPER_API_KEY[-4:]
        )

        logger.info("Loaded API Key : %s", masked)
        logger.info(
            "API Key Length : %d",
            len(self.SERPER_API_KEY),
        )

        logger.debug(
            "Endpoint : %s",
            self.SERPER_ENDPOINT,
        )

        logger.debug(
            "Timeout : %d",
            self.REQUEST_TIMEOUT,
        )

    def validate(self):

        if not self.SERPER_API_KEY:

            logger.error(
                "SERPER_API_KEY missing."
            )

            raise ValueError(
                "SERPER_API_KEY not found."
            )


settings = Settings()