"""
FastMCP Server Entry Point.
"""

from __future__ import annotations
from app.tools.current_date import current_date
import traceback
import time
import json

from fastmcp import FastMCP

from app.logger import get_logger
from app.tools.web_search import web_search

logger = get_logger(__name__)

logger.info("Creating FastMCP server...")

mcp = FastMCP(
    name="Serper Search",
    instructions="Production MCP server providing Google Serper web search."
)

logger.info("FastMCP server created successfully.")


@mcp.tool(
    name="search",
    description="Search the live web using Google Serper."
)
def search(query: str):

    from pathlib import Path

    Path(r"D:\mcp-server\tool_called.txt").write_text(
        f"Tool called with query: {query}",
        encoding="utf-8",
    )

    logger.info("=" * 100)
    logger.info("Incoming MCP Tool Request")
    logger.info("Tool  : search")
    logger.info("Query : %s", query)

    start = time.perf_counter()

    try:

        result = web_search(query)

        elapsed = time.perf_counter() - start

        logger.info(
            "Tool completed successfully in %.3f sec",
            elapsed,
        )

        logger.info("Return Type : %s", type(result).__name__)

        logger.debug(
            "Return Payload : %s",
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            ),
        )

        return result

    except Exception as exc:

        elapsed = time.perf_counter() - start

        logger.exception("Tool execution failed.")

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 3),
            "traceback": traceback.format_exc(),
        }

    finally:

        logger.info("=" * 100)


@mcp.tool(
    name="current_date",
    description="Returns the current system date and time."
)
def get_current_date():

    logger.info("=" * 100)
    logger.info("Incoming MCP Tool Request")
    logger.info("Tool : current_date")

    start = time.perf_counter()

    try:

        result = current_date()

        elapsed = time.perf_counter() - start

        logger.info(
            "Tool completed successfully in %.3f sec",
            elapsed,
        )

        return result

    except Exception as exc:

        elapsed = time.perf_counter() - start

        logger.exception("Tool execution failed.")

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 3),
            "traceback": traceback.format_exc(),
        }

    finally:

        logger.info("=" * 100)


if __name__ == "__main__":

    logger.info("Log File Location : %s", logger.handlers[1].baseFilename)

    mcp.run("stdio")