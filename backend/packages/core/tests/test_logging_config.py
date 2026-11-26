"""Tests for logging configuration and fallback behavior."""

from pathlib import Path
from typing import Any

import pytest

from glean_core.logging_config import logger, setup_logging


def test_setup_logging_writes_to_writable_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "app.log"
    try:
        setup_logging(log_level="INFO", log_file=str(log_file))
        logger.info("hello file")
        logger.error("boom error")
        logger.complete()

        error_log_file = log_file.parent / "app_error.log"
        assert log_file.exists()
        assert "hello file" in log_file.read_text(encoding="utf-8")
        assert error_log_file.exists()
        assert "boom error" in error_log_file.read_text(encoding="utf-8")
    finally:
        setup_logging()


def test_setup_logging_falls_back_to_console_on_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_add = logger.add

    def fake_add(sink: Any, *args: Any, **kwargs: Any) -> int:
        if isinstance(sink, str):
            raise PermissionError("Permission denied")
        return original_add(sink, *args, **kwargs)

    monkeypatch.setattr(logger, "add", fake_add)

    try:
        setup_logging(log_level="INFO", log_file=str(tmp_path / "glean-api.log"))
        logger.info("still logging to console")
        captured = capsys.readouterr()
        assert "File logging disabled" in captured.err
        assert "still logging to console" in captured.err
    finally:
        monkeypatch.undo()
        setup_logging()


def test_setup_logging_falls_back_when_parent_cannot_be_created(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file", encoding="utf-8")

    try:
        setup_logging(log_level="INFO", log_file=str(blocker / "glean-api.log"))
        logger.info("console survives")
        captured = capsys.readouterr()
        assert "File logging disabled" in captured.err
        assert "console survives" in captured.err
    finally:
        setup_logging()
