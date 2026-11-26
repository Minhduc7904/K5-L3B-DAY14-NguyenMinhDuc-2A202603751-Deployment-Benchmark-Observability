"""
Cost guard (tiêu chí 8).

• Chi phí LLM của mỗi API key được cộng dồn trong Redis theo ngày (UTC):
  key `cost:<key_id>:<YYYY-MM-DD>` — sang ngày mới là key mới nên tự về 0.
• check_budget(): gọi TRƯỚC khi gọi LLM, đã dùng >= DAILY_BUDGET_USD → HTTP 402.
• record_cost(): gọi SAU khi gọi LLM, tính tiền từ số token rồi INCRBYFLOAT (nguyên tử).
"""
import time

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import key_id, r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_KEY_TTL_SECONDS = 2 * 24 * 3600  # giữ qua nửa đêm một chút rồi tự xóa


def _cost_key(api_key: str) -> str:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    return f"cost:{key_id(api_key)}:{today}"


def estimate_tokens(text: str) -> int:
    """Ước lượng thô cho mock LLM: ~2 token mỗi từ, tối thiểu 1."""
    return max(1, len(text.split()) * 2)


def check_budget(api_key: str) -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        spent = float(r.get(_cost_key(api_key)) or 0)
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable (Redis error)")

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "used_usd": round(spent, 6),
                "budget_usd": settings.daily_budget_usd,
                "resets_at": "00:00 UTC",
            },
        )


def record_cost(api_key: str, input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    key = _cost_key(api_key)
    pipe = r.pipeline()
    pipe.incrbyfloat(key, cost)
    pipe.expire(key, _KEY_TTL_SECONDS)
    pipe.execute()
    return cost
