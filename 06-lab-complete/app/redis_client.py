"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

• Đọc REDIS_URL từ config.
• redis.from_url() chỉ tạo client, KHÔNG kết nối ngay → app vẫn khởi động được khi Redis chưa sẵn sàng.
• Timeout ngắn để /ready trả 503 nhanh khi Redis hỏng thay vì treo.
"""
import hashlib

import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: ping được Redis → True, lỗi kết nối → False."""
    try:
        return bool(r.ping())
    except Exception:
        return False


def key_id(api_key: str) -> str:
    """Định danh rút gọn của API key — không đưa key thật vào tên key Redis."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def close_redis() -> None:
    try:
        r.close()
    except Exception:
        pass
