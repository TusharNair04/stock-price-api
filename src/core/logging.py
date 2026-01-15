"""
Structured logging configuration for the Stock Price API.
Provides JSON logging for production and human-readable logging for development.
"""

import json
import os
import sys
from typing import Any

from loguru import logger


def json_formatter(record: dict[str, Any]) -> str:
    """
    Format log records as JSON for production/CloudWatch.
    """
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add extra fields if present
    if record.get("extra"):
        for key, value in record["extra"].items():
            if key not in log_entry:
                log_entry[key] = value

    return json.dumps(log_entry) + "\n"


def human_formatter(record: dict[str, Any]) -> str:
    """
    Format log records for human readability in development.
    """
    return (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>\n"
    )


def configure_logging(
    level: str = "INFO",
    json_output: bool = None,
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Force JSON output. If None, auto-detect based on environment.
    """
    # Remove existing handlers
    logger.remove()

    # Auto-detect JSON mode if not specified
    if json_output is None:
        # Use JSON in Lambda or when explicitly requested
        json_output = bool(
            os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or
            os.environ.get("LOG_FORMAT") == "json"
        )

    if json_output:
        # JSON format for production/Lambda
        logger.add(
            sys.stderr,
            format=json_formatter,
            level=level,
            serialize=False,
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stderr,
            format=human_formatter,
            level=level,
            colorize=True,
        )

    logger.info(f"Logging configured: level={level}, json={json_output}")


def get_logger(name: str = None):
    """
    Get a logger instance with optional context binding.

    Args:
        name: Optional logger name for context

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(logger_name=name)
    return logger


# Auto-configure on import if in Lambda
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    configure_logging(level="INFO", json_output=True)
