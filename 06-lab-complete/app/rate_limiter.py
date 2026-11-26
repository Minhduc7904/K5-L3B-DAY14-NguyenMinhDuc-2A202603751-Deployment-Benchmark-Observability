"""
Rate limiting (tiêu chí 7) — sliding window log lưu trong Redis.

• Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây.
• State là một sorted set `rate:<key_id>` (member = request, score = thời điểm, ms).
  Nằm trong Redis nên mọi worker / instance dùng chung và còn nguyên sau khi restart agent.
• Gói trong một Lua script để "xóa cũ → đếm → thêm" chạy nguyên tử, hai worker
  không thể cùng lọt qua giới hạn. Thời gian lấy từ Redis (TIME) để không lệch đồng hồ.
• Vượt giới hạn → HTTP 429 kèm header Retry-After.
"""
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import key_id, r

WINDOW_SECONDS = 60

_SLIDING_WINDOW = r.register_script(
    """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = math.ceil((tonumber(oldest[2]) + window - now) / 1000)
  if retry < 1 then retry = 1 end
  return {0, count, retry}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {1, count + 1, 0}
"""
)


def check_rate_limit(key: str) -> int:
    """Trả về số request còn lại trong cửa sổ; raise 429 nếu vượt giới hạn."""
    limit = settings.rate_limit_per_minute
    try:
        allowed, count, retry_after = _SLIDING_WINDOW(
            keys=[f"rate:{key_id(key)}"],
            args=[WINDOW_SECONDS * 1000, limit, uuid.uuid4().hex],
        )
    except RedisError:
        # Không đếm được thì không thể bảo vệ → từ chối thay vì bỏ qua giới hạn.
        raise HTTPException(status_code=503, detail="Rate limiter unavailable (Redis error)")

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    return limit - count
