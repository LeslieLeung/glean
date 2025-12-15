"""
Unified logging configuration module.

Provides Loguru-based logging configuration with environment variable control,
log rotation, and structured logging support.
"""

import os
import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    log_format: str | None = None,
    rotation: str = "100 MB",
    retention: str = "30 days",
    compression: str = "gz",
    serialize: bool = False,
) -> None:
    """
    Configure Loguru logging system.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path, if None only output to console
        log_format: Log format, if None use default format
        rotation: Log rotation strategy
        retention: Log retention time
        compression: Log compression format
        serialize: Whether to serialize to JSON format
    """
    # Remove default handler
    logger.remove()

    # Default format
    if log_format is None:
        if serialize:
            log_format = None  # Use default JSON format
        else:
            log_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )

    # Console handler
    if log_format is not None:
        logger.add(
            sys.stderr,
            format=log_format,
            level=log_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
            serialize=True,
        )

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Regular log file
        if log_format is not None:
            logger.add(
                log_file,
                format=log_format,
                level=log_level,
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=serialize,
                backtrace=True,
                diagnose=True,
            )
        else:
            logger.add(
                log_file,
                level=log_level,
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=True,
                backtrace=True,
                diagnose=True,
            )

        # Error log separate file
        error_log_file = log_path.parent / f"{log_path.stem}_error{log_path.suffix}"
        if log_format is not None:
            logger.add(
                str(error_log_file),
                format=log_format,
                level="ERROR",
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=serialize,
                backtrace=True,
                diagnose=True,
            )
        else:
            logger.add(
                str(error_log_file),
                level="ERROR",
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=True,
                backtrace=True,
                diagnose=True,
            )


def setup_logging_from_env() -> None:
    """
    Configure logging system from environment variables.

    Environment Variables:
    - LOG_LEVEL: Log level (default: INFO)
    - LOG_FILE: Log file path (default: None)
    - LOG_FORMAT: Log format (default: use built-in format)
    - LOG_ROTATION: Log rotation strategy (default: 100 MB)
    - LOG_RETENTION: Log retention time (default: 30 days)
    - LOG_COMPRESSION: Log compression format (default: gz)
    - LOG_SERIALIZE: Whether to serialize to JSON (default: False)
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE")
    log_format = os.getenv("LOG_FORMAT")
    log_rotation = os.getenv("LOG_ROTATION", "100 MB")
    log_retention = os.getenv("LOG_RETENTION", "30 days")
    log_compression = os.getenv("LOG_COMPRESSION", "gz")
    log_serialize = os.getenv("LOG_SERIALIZE", "false").lower() == "true"

    setup_logging(
        log_level=log_level,
        log_file=log_file,
        log_format=log_format,
        rotation=log_rotation,
        retention=log_retention,
        compression=log_compression,
        serialize=log_serialize,
    )


def intercept_standard_logging() -> None:
    """
    Intercept standard logging module logs and output them through Loguru.
    """
    import logging

    class InterceptHandler(logging.Handler):
        """Intercept standard logging logs and forward to Loguru."""

        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller
            frame, depth = logging.currentframe(), 0
            while frame is not None and depth < 5:
                filename = frame.f_code.co_filename
                is_logging = filename == logging.__file__
                is_frozen = "importlib" in filename and "_bootstrap" in filename
                if depth > 0 and not (is_logging or is_frozen):
                    break
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    # Configure standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Set third-party library log levels
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "arq", "sqlalchemy"]:
        logging.getLogger(logger_name).setLevel(logging.INFO)


def get_logger(name: str | None = None):
    """
    Get Loguru logger instance.

    Args:
        name: Logger name, if None use calling module name

    Returns:
        Loguru logger instance
    """
    if name is None:
        # Automatically get calling module name
        import inspect

        frame = inspect.currentframe()
        if frame is not None and frame.f_back is not None:
            name = frame.f_back.f_globals.get("__name__", "unknown")
        else:
            name = "unknown"

    return logger.bind(name=name)


# Initialize logging configuration
def init_logging(config_file: str | None = None) -> None:
    """
    Initialize logging system.

    Args:
        config_file: Configuration file path, if None use environment variables
    """
    if config_file and os.path.exists(config_file):
        # Load from config file (future extension)
        pass
    else:
        # Configure from environment variables
        setup_logging_from_env()

    # Intercept standard logging
    intercept_standard_logging()
