"""
Google Serper API client.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)


class SerperClient:

    def __init__(self):

        logger.info(
            "Initializing Serper client."
        )

        self.session = requests.Session()

        self.headers = {
            "X-API-KEY": settings.SERPER_API_KEY,
            "Content-Type": "application/json",
        }

        masked = (
            self.headers["X-API-KEY"][:6]
            + "..."
            + self.headers["X-API-KEY"][-4:]
        )

        logger.info(
            "Header API Key : %s",
            masked,
        )

        logger.info(
            "Serper client initialized."
        )

    def search(
        self,
        query: str,
    ) -> dict[str, Any]:

        payload = {
            "q": query,
        }

        logger.info("=" * 80)
        logger.info("Sending request to Serper.")
        logger.info("Query : %s", query)

        start = time.perf_counter()

        try:

            response = self.session.post(
                url=settings.SERPER_ENDPOINT,
                json=payload,
                headers=self.headers,
                timeout=settings.REQUEST_TIMEOUT,
            )

            elapsed = time.perf_counter() - start

            logger.info(
                "HTTP Status : %s",
                response.status_code,
            )

            logger.info(
                "Elapsed : %.3f sec",
                elapsed,
            )

            logger.debug(
                "Response Headers : %s",
                dict(response.headers),
            )

            logger.debug(
                "Response Body : %s",
                response.text,
            )

            response.raise_for_status()

            logger.info(
                "Successfully parsed JSON."
            )

            return response.json()

        except requests.Timeout as exc:

            logger.exception(
                "Timeout calling Serper."
            )

            raise RuntimeError(
                "Serper timeout."
            ) from exc

        except requests.HTTPError as exc:

            logger.exception(
                "HTTP error."
            )

            logger.error(
                "Status : %s",
                response.status_code,
            )

            logger.error(
                "Body : %s",
                response.text,
            )

            raise RuntimeError(
                f"HTTP {response.status_code}: {response.text}"
            ) from exc

        except requests.RequestException as exc:

            logger.exception(
                "Network error."
            )

            raise RuntimeError(
                "Network failure."
            ) from exc

        finally:

            logger.info("=" * 80)


serper = SerperClient()