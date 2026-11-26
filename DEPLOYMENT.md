# Deployment Information — Day 14

## Public URL

https://k5-l3b-day14-nguyenminhduc-2a202603751.onrender.com

## Platform

Render Free Web Service chạy Docker từ branch `main` của repo GitHub. Root Directory là `06-lab-complete`, Docker Build Context là `.`, Dockerfile Path là `./Dockerfile` và Health Check Path là `/health`. Agent và instance Key Value `day14-redis` chạy ở Oregon (US West). Agent kết nối Key Value qua Internal URL.

## Test commands

Chạy trong Bash/WSL. Nhập key đã cấu hình trên Render khi terminal hiện dòng nhắc.

```bash
BASE='https://k5-l3b-day14-nguyenminhduc-2a202603751.onrender.com'
read -rsp 'AGENT_API_KEY: ' AGENT_API_KEY
printf '\n'

curl -sS -o /dev/null -w 'GET /health: %{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w 'GET /ready: %{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w 'POST /ask thiếu key: %{http_code}\n' \
  -X POST "$BASE/ask" -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
curl -sS -o /dev/null -w 'POST /ask có key: %{http_code}\n' \
  -X POST "$BASE/ask" -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'

unset AGENT_API_KEY
```

| Request | Kết quả thực tế |
|---|---|
| `GET /health` | **200 OK**, `status: ok`, `environment: production`. |
| `GET /ready` | **200 OK**, `ready: true`. Agent kết nối được Key Value. |
| `POST /ask` thiếu key | **401 Unauthorized**. |
| `POST /ask` có key | **200 OK**, xác nhận từ lần chạy trong WSL. |

## Environment variables

- `ENVIRONMENT` là `production`.
- `AGENT_API_KEY` đặt trong Environment Variables của Render.
- `REDIS_URL` đặt bằng Internal URL của `day14-redis`.
- `PORT` do Render cấp và Dockerfile dùng để khởi động Uvicorn.

## Screenshots

- [Dashboard](screenshots/dashboard.png) — Web Service đang Deployed và Key Value đang Available.
- [Deployment Live](screenshots/running.png) — Render báo Deploy succeeded và hiển thị URL public.
- [Kết quả kiểm tra HTTP](screenshots/test.png) — Terminal hiện bốn mã **200 / 200 / 401 / 200**.
