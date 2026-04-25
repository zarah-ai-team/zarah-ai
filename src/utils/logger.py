import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict


class PipelineLogger:
    """Structured logger with per-stage timing."""

    def __init__(self, name: str):
        self._log = logging.getLogger(name)
        if not self._log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            ))
            self._log.addHandler(handler)
        self._log.setLevel(logging.DEBUG)
        self._starts: Dict[str, float] = {}

    def stage_start(self, stage: str, request_id: str = "", **kw) -> float:
        t = time.time()
        self._starts[stage] = t
        extra = json.dumps({k: v for k, v in kw.items() if v is not None})
        self._log.info(f"[{request_id}] ▶ {stage} {extra}")
        return t

    def stage_end(self, stage: str, request_id: str = "", **kw) -> int:
        elapsed = int((time.time() - self._starts.get(stage, time.time())) * 1000)
        extra = json.dumps({k: v for k, v in kw.items() if v is not None})
        self._log.info(f"[{request_id}] ✓ {stage} {elapsed}ms {extra}")
        return elapsed

    def stage_error(self, stage: str, error: Exception, request_id: str = ""):
        self._log.error(f"[{request_id}] ✗ {stage} {type(error).__name__}: {error}")

    def info(self, msg: str, request_id: str = "", **kw):
        extra = json.dumps({k: v for k, v in kw.items() if v is not None}) if kw else ""
        self._log.info(f"[{request_id}] {msg} {extra}".rstrip())

    def warning(self, msg: str, request_id: str = "", **kw):
        self._log.warning(f"[{request_id}] {msg}")

    def debug(self, msg: str, **kw):
        self._log.debug(msg)

    @contextmanager
    def timed_stage(self, stage: str, request_id: str = "", **kw):
        self.stage_start(stage, request_id, **kw)
        try:
            yield
        except Exception as e:
            self.stage_error(stage, e, request_id)
            raise
        finally:
            self.stage_end(stage, request_id)


def get_logger(name: str) -> PipelineLogger:
    return PipelineLogger(name)
