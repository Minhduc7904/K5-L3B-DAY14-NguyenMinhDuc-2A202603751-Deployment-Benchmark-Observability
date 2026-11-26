# ============================================================
# Production Dockerfile — multi-stage, slim, non-root
# Build context: thư mục 06-lab-complete/
#   docker build -t agent .
#   docker run -p 8000:8000 -e AGENT_API_KEY=... agent
# ============================================================

# ── Stage 1: builder — cài dependencies vào một prefix riêng ──
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime — chỉ copy kết quả, không mang theo pip cache hay công cụ build ──
FROM python:3.11-slim AS runtime

RUN groupadd --system agent && useradd --system --gid agent --home-dir /app --no-create-home agent

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY utils/ ./utils/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER agent

EXPOSE 8000

# Gọi /health bằng Python có sẵn (image slim không có curl). Đọc cổng từ PORT.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3)"

# `exec` thay shell bằng uvicorn → uvicorn là PID 1, nhận trực tiếp SIGTERM từ `docker stop`.
# Cổng lấy từ PORT (Railway / Render cấp), mặc định 8000. Hai worker dùng chung state qua Redis.
# --timeout-graceful-shutdown 8: tối đa 8s chờ request đang chạy, để `docker stop` xong trong < 10s.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-graceful-shutdown 8"]
