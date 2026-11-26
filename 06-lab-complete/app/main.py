"""
Production AI Agent — Part 6 Final Project

Luồng của /ask:  xác thực → rate limit → kiểm tra ngân sách → gọi mock LLM → ghi chi phí.

Chạy:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.logging_config import log, setup_logging
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask

# Tiêu chí 10 — mọi dòng log (app + uvicorn) là JSON
setup_logging()

START_TIME = time.time()


# Tiêu chí 11 — Graceful shutdown.
# Uvicorn bắt SIGTERM: ngừng nhận kết nối mới, chờ request đang chạy xong rồi mới chạy
# phần sau `yield` bên dưới và thoát với exit code 0. Không tự đăng ký handler SIGTERM,
# vì làm vậy sẽ ghi đè handler của uvicorn và process không bao giờ tắt.
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(
        "startup",
        environment=settings.environment,
        port=settings.port,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        daily_budget_usd=settings.daily_budget_usd,
    )
    yield
    log("shutdown", detail="in-flight requests finished, closing Redis")
    close_redis()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def request_log(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )


# Tiêu chí 4 — liveness: chỉ cho biết process còn chạy, KHÔNG phụ thuộc Redis.
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
    }


# Tiêu chí 5 — readiness: sẵn sàng nhận traffic khi Redis kết nối được.
@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not available")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    # Tiêu chí 7 → 429 khi vượt giới hạn
    remaining = check_rate_limit(api_key)
    # Tiêu chí 8 → 402 khi hết budget (kiểm tra trước khi tốn tiền gọi LLM)
    check_budget(api_key)

    answer = llm_ask(body.question)

    try:
        cost = record_cost(api_key, estimate_tokens(body.question), estimate_tokens(answer))
    except RedisError:
        # Request đã phục vụ xong, không trả lỗi cho client; chỉ ghi log để theo dõi.
        cost = None
        log("cost_record_failed", level=logging.ERROR)

    log("ask", question_length=len(body.question), answer_length=len(answer), cost_usd=cost)
    return {
        "question": body.question,
        "answer": answer,
        "usage": {"requests_remaining": remaining, "cost_usd": cost},
    }
