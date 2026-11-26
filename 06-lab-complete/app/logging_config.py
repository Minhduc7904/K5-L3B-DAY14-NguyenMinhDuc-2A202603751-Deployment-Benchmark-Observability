"""
Structured logging (tiêu chí 10): mỗi dòng log là một JSON object hợp lệ.

Cả log của app lẫn log của uvicorn (startup, shutdown...) đều đi qua formatter này.
Log request truy cập do middleware trong main.py ghi, nên access log mặc định của
uvicorn được tắt để không bị lặp.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", None) or {})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn tự cấu hình logger riêng → ép dùng cùng handler JSON
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False


def log(event: str, level: int = logging.INFO, **fields) -> None:
    """Ghi một sự kiện có cấu trúc: log("request", path="/ask", status=200)."""
    logging.getLogger("agent").log(level, event, extra={"fields": fields})
