"""Logging utilities for the TTUEX Bot, powered by structlog."""

import sys
import structlog
from ttuex_bot.config import app_config

# Singleton logger instance
_logger = None


def get_logger(name: str, **kwargs) -> structlog.BoundLogger:
    """Returns a configured logger instance."""
    global _logger
    if _logger is None:
        _configure_logger()
        # Debugging: Confirm effective log level
        import logging
        effective_level = logging.getLogger().getEffectiveLevel()
        print(f"[DEBUG] Logger configured. Effective level: {logging.getLevelName(effective_level)}")

    return structlog.get_logger(name).bind(**kwargs)


def reset_logger():
    """Resets the global logger instance to allow reconfiguration."""
    global _logger
    _logger = None
    structlog.reset_defaults()


def _configure_logger():
    """Configures structlog based on application settings."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if app_config.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog
    import logging

    log_level = getattr(logging, app_config.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")
