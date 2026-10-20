"""The package logger keeps writing after a library has closed every handler."""
import logging

import lab_data_parser as ldp


def test_file_handler_survives_logging_shutdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ldp.logging.setup_logger(level="DEBUG", use_file_handler=True, use_console_handler=False)
    logger = logging.getLogger("lab_data_parser.test")
    logger.info("before")
    logging.shutdown()          # what SpectroChemPy does on its first read
    logger.info("after")
    for handler in logging.getLogger("lab_data_parser").handlers:
        handler.flush()
    text = (tmp_path / "lab_data_parser.log").read_text(encoding="utf-8")
    assert "before" in text and "after" in text
    ldp.logging.setup_logger(use_file_handler=False)
