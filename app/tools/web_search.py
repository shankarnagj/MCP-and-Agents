"""
Web Search Tool

Contains the business logic for performing web searches.
This module is completely independent of FastMCP.
"""

from __future__ import annotations

import time
from typing import Any

from app.clients.serper import serper
from app.logger import get_logger

logger = get_logger(__name__)


def _normalize_response(
    query: str,
    raw_response: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert raw Serper JSON into a simplified response.
    """

    normalized = {
        "query": query,
        "answer_box": raw_response.get("answerBox"),
        "knowledge_graph": raw_response.get("knowledgeGraph"),
        "results": [],
    }

    for item in raw_response.get("organic", []):

        normalized["results"].append(
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "snippet": item.get("snippet"),
            }
        )

    return normalized


def web_search(query: str) -> dict[str, Any]:

    logger.info("=" * 80)
    logger.info("Web Search Tool Invoked")

    start_time = time.perf_counter()

    query = query.strip()

    if not query:

        logger.error("Empty search query received.")

        raise ValueError(
            "Search query cannot be empty."
        )

    logger.info("Search Query : %s", query)

    try:

        raw_response = serper.search(query)

        normalized_response = _normalize_response(
            query,
            raw_response,
        )

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Search completed successfully in %.3f seconds",
            elapsed,
        )

        logger.info(
            "Returned %d results.",
            len(normalized_response["results"]),
        )

        return normalized_response

    except ValueError:

        logger.exception("Validation error.")

        raise

    except RuntimeError:

        logger.exception("Serper client error.")

        raise

    except Exception:

        logger.exception("Unexpected error occurred.")

        raise

    finally:

        logger.info("=" * 80)