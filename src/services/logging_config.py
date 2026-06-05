"""Logging configuration for the Ontology NLP Query System.

Sets up structured JSON logging to both console and a rotating log file.
All service calls, responses, and errors are captured with timestamps
and correlation IDs for debugging and audit purposes.

Log files are written to: logs/system.log (rotated daily, 7 days retained)
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "system.log"

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for machine-parseable output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a structured line.

        For messages that are already JSON (from observability decorator),
        passes them through. For other messages, wraps them in a standard
        structure.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname

        # If the message is already structured JSON, prefix with timestamp/level
        msg = record.getMessage()
        if msg.startswith("{"):
            return f"[{timestamp}] [{level:7s}] {msg}"

        # Standard format for non-structured messages
        name = record.name
        return f"[{timestamp}] [{level:7s}] [{name}] {msg}"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging for all services.

    Sets up:
    - Console handler (StreamHandler to stderr) for real-time visibility
    - Rotating file handler for persistence (10MB per file, 7 backups)

    Args:
        level: The minimum log level to capture.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    formatter = StructuredFormatter()

    # Console handler — logs to stderr so it's visible even with stdout redirection
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler — rotating log file for persistence
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
