# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Minh Đức

**Ngày chạy CP7:** 26/11/2026

**Môi trường CP7:** Ubuntu WSL2 trên Windows. Agent và client chạy trên cùng máy. v1 chạy cổng `8001`, v2 chạy cổng `8002`.

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Dùng ngưỡng của `load_test.py` để theo dõi độ trễ mà phần lớn người dùng gặp. |
| Error rate `/ask` | ≤ 2% | Dùng ngưỡng của `load_test.py`, tương ứng ít nhất 98% request thành công. |
| Accuracy trên golden dataset | ≥ 85% trong CI | Ngưỡng chặn merge của bài. So sánh thêm với baseline để phát hiện câu từng đúng bị sai. Lần eval cuối của bài yêu cầu 100%. |

### Exercise 7.1 — Metrics và số lượng chuỗi thời gian

- **Counter:** `http_requests_total` cộng dồn theo method, route và status.
- **Gauge:** Quan sát `agent_info{model="mock-llm-small",version="v2"} 1.0`. Gauge `agent_in_flight_requests` theo dõi số request đang xử lý.
- **Histogram:** `http_request_duration_seconds` phân bố thời gian xử lý theo bucket.

Middleware lấy `route.path` từ route đã khớp, và dùng `unmatched` khi URL không khớp route nào. Trong lần kiểm tra ba URL lạ, cả ba trả 404 và được gộp vào một series `http_requests_total{method="GET",route="unmatched",status="404"} 3.0`. Nếu dùng nguyên URL làm label, mỗi URL có thể tạo thêm một bộ series. Riêng histogram latency có 11 bucket hữu hạn, thêm bucket `+Inf`, `_count` và `_sum`, tức 14 series cho mỗi tổ hợp label. Giới hạn giá trị của label giúp kiểm soát bộ nhớ và chi phí truy vấn. [Middleware và định nghĩa metric](06-lab-complete/benchmark-observability/develop/app.py)

Tôi thêm Histogram `agent_question_length_chars` với bucket `10, 25, 50, 100, 200, 500, 1000, 2000` và gọi `QUESTION_LENGTH.observe(len(body.question))` trước khi gọi LLM. Sau khi restart v2 và gửi hai câu dài 22 và 77 ký tự, metric có `count=2`, `sum=99`, bucket `le=25` có 1 mẫu và bucket `le=100` có 2 mẫu. [Code đo độ dài câu hỏi](06-lab-complete/benchmark-observability/develop/app.py)

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Mỗi lần chạy gửi 300 request. Error rate trong bảng được hiển thị dưới dạng phần trăm.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.81 | 189.1 | 217.1 | 1676.9 | 0.33% | PASS |
| 10 | 41.77 | 190.1 | 216.9 | 1681.0 | 1.33% | PASS |
| 50 | 117.03 | 193.3 | 255.2 | 1724.0 | 0.33% | PASS |
| 100 | 71.39 | 325.2 | 2278.5 | 2445.5 | 0.67% | FAIL |

RPS tăng từ **4.81** ở concurrency 1 lên **117.03** ở concurrency 50. Mức tăng thấp hơn tỷ lệ tăng concurrency, trong khi p50 chỉ tăng từ **189.1** lên **193.3 ms**. Mock LLM đợi bất đồng bộ, nên nhiều request có thể chờ đồng thời. Ở concurrency 100, RPS giảm còn **71.39**, p50 lên **325.2 ms**, p90 lên **2113.4 ms** và p95 lên **2278.5 ms**, vượt ngưỡng SLO. Kết quả phù hợp với hiện tượng xếp hàng hoặc tranh chấp tài nguyên. Lần chạy duy nhất ở mức này chưa tách được ảnh hưởng của một server process, ghi log và client chạy cùng máy WSL. Tất cả mức concurrency đạt ngưỡng error rate. Mức 100 fail SLO do p95. [JSON concurrency 1](reports/load_v2_c1.json) · [load_v2_c10.json](reports/load_v2_c10.json) · [load_v2_c50.json](reports/load_v2_c50.json) · [load_v2_c100.json](reports/load_v2_c100.json)

### 2.2 Tail latency

Mỗi lần chạy gửi 300 request ở concurrency 20.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | SLO |
|---|---|---|---|---|
| 0 | 188.3 | 216.8 | 226.3 | PASS |
| 0.03 (mặc định) | 259.5 | 228.0 | 1705.3 | PASS |
| 0.1 | 371.6 | 1693.7 | 1712.7 | FAIL |

Mock LLM mặc định cộng 1500 ms cho một request rơi vào nhóm chậm. Khi tăng slow rate từ 0 lên 0.03, avg tăng từ **188.3** lên **259.5 ms** (khoảng 38%), còn p99 tăng từ **226.3** lên **1705.3 ms** (khoảng 7.5 lần). Ở mức 0.03, p95 vẫn **228.0 ms**. Ở mức 0.1, p95 lên **1693.7 ms** và vượt SLO dù avg chỉ **371.6 ms**. Trung bình làm loãng tác động của nhóm chậm. p95 và p99 cho thấy trực tiếp trải nghiệm ở phần chậm của phân bố. Slow rate là xác suất cấu hình, nên số request chậm thực tế dao động giữa các lần chạy. [load_v2_slow_0.json](reports/load_v2_slow_0.json) · [load_v2_slow_0.03.json](reports/load_v2_slow_0.03.json) · [load_v2_slow_0.1.json](reports/load_v2_slow_0.1.json)

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 sau khi sửa KB |
|---|---|---|---|
| Accuracy | 1/23 (4.35%) | 21/23 (91.30%) | 23/23 (100.00%) |
| Avg tokens / câu | 57.4 | 109.0 | 115.0 |
| Tổng cost (USD) | 0.000409 | 0.000759 | 0.000802 |
| Cost / câu đúng (USD) | 0.00040875 | 0.00003616 | 0.00003485 |
| p95 latency (ms) | 183.5 | 219.3 | 1531.0 |
| Quality gate | FAIL (ngưỡng 85%) | PASS (ngưỡng 85%) | PASS (ngưỡng 100%) |

v1 chỉ đúng `basic-01`. v2 cải thiện 20 câu so với v1 và có 0 regression. Hai câu v2 sai trước khi sửa đều nhận câu trả lời chung chung vì retrieval thiếu tài liệu phù hợp.

| ID | Keyword bị thiếu | Cách sửa |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry so sánh API key với JWT. Keyword truy xuất gồm `jwt`, `api key`, `xác thực`. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry giải thích Kubernetes HPA, với keyword `kubernetes`, `hpa`, `autoscal`. |

Sau khi sửa KB và restart v2, eval với baseline v2 cũ đạt **23/23**, 0 regression và exit code **0**. Golden dataset giữ nguyên. [Knowledge base](06-lab-complete/benchmark-observability/develop/utils/mock_llm.py) · [eval_v1.json](reports/eval_v1.json) · [eval_v2.json](reports/eval_v2.json) · [eval_v2_fixed.json](reports/eval_v2_fixed.json)

So với v1, v2 dùng nhiều hơn khoảng **90%** token mỗi câu vì prompt có context retrieval, và tổng chi phí tăng khoảng **86%**. Chi phí trên mỗi câu **đúng** giảm khoảng **11.3 lần**, từ **0.00040875** xuống **0.00003616 USD**, vì số câu đúng tăng từ 1 lên 21. Sau khi sửa KB, chi phí trên mỗi câu đúng còn **0.00003485 USD**, giảm thêm khoảng **3.6%**. p95 lần eval cuối lên **1531.0 ms** so với **219.3 ms** ở v2 ban đầu. Hai case `bench-02` và `obs-02` mất **1676.7 ms** và **1681.8 ms**, phù hợp với các request rơi vào tail của mock LLM. Một lần eval chưa đủ để kết luận KB làm thay đổi latency.

### Quality gate trong CI

CI khởi động agent v2, đợi `/health` trả 200, rồi chạy lệnh sau từ thư mục develop. Đường dẫn baseline trỏ tới bản JSON dùng để nộp ở gốc repo.

```bash
python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85 \
  --baseline ../../../reports/eval_v2.json --out reports/eval_ci.json
```

Script trả mã **1** nếu accuracy dưới 85% hoặc một câu từng đúng ở baseline nay sai. Step CI thất bại khi nhận mã 1. Đặt check này là điều kiện bắt buộc trên nhánh chính để PR chỉ merge khi quality gate đạt. Lần chạy v1 thực tế trả mã 1 và lần eval v2 sau khi sửa trả mã 0. [Logic quality gate](06-lab-complete/benchmark-observability/develop/eval/run_eval.py#L194-L214)

## 4. Observability stack (production)

### 4.1 Grafana khi có tải — Exercise 7.4

Locust chạy 30 users, qua Nginx tới hai instance agent. Số bên dưới lấy từ lần quan sát tải ổn định.

| Chỉ số | Kết quả |
|---|---:|
| Prometheus p95 và avg `/ask` | ≈ 299 ms và 257 ms |
| Locust avg và p95 | 246 ms và 220 ms |
| Tổng traffic `/ask` | ≈ 17.4 req/s |
| Traffic theo instance | 8.73 và 8.69 req/s |
| Input và output token | ≈ 1263 và 672 token/s |
| Tỷ lệ HTTP 5xx | ≈ 1.7% |
| Request đang xử lý | 4 |

- **Latency:** Prometheus ước tính p95 bằng `histogram_quantile` trên dữ liệu bucket trong cửa sổ một phút. Nội suy trong bucket 200–300 ms có thể làm giá trị khác p95 tính từ mẫu của Locust. Locust đo từ phía client, còn metric của agent đo phía server, nên phạm vi phép đo và cửa sổ lấy mẫu cũng ảnh hưởng.
- **Phân phối tải:** Hai instance nhận traffic gần bằng nhau. Nginx cân bằng request giữa các agent, còn Prometheus dùng DNS service discovery để scrape riêng từng target.
- **Token:** Input cao hơn output khoảng 1.9 lần vì prompt v2 bao gồm nội dung câu hỏi, chỉ dẫn và context retrieval khi có. Panel Tokens/s cộng dồn các đường, nên độ cao đường trên biểu đồ còn gồm series phía dưới.
- **Metrics:** `GET /metrics` qua Nginx trả 404 theo cấu hình. Prometheus scrape trực tiếp từng agent ở cổng 8000 trong mạng nội bộ, giữ được identity của từng target. Qua load balancer, các lần scrape có thể rơi vào những agent khác nhau và làm sai chuỗi counter. [Nginx](06-lab-complete/benchmark-observability/production/nginx/nginx.conf) · [Prometheus](06-lab-complete/benchmark-observability/production/prometheus/prometheus.yml)

Ảnh Grafana ở một thời điểm khác trong cùng phiên tải cho thấy **17.9 req/s**, **p95 294.54 ms**, **0.59% lỗi**, **3 request in-flight** và **2 instance up**. [Ảnh Grafana](screenshots/grafana-dashboard.png)

### 4.2 Thí nghiệm alert — Exercise 7.6

Mốc 0 của mỗi thí nghiệm là lúc Compose tạo lại agent với biến môi trường mới. Giữ tải 30 users.

| # | Thay đổi | Alert | Điều kiện | Pending sau | Firing sau | Panel |
|---|---|---|---|---:|---:|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | Tỷ lệ 5xx > 5% liên tục 1 phút | 27 s | **86 s** | Error rate |
| B | Thêm `MOCK_SLOW_RATE=0.3`, giữ A | `AgentHighLatencyP95` | p95 > 1 s liên tục 2 phút | 27 s | **150 s** | Latency p95 |

A bắt đầu lúc **16:19:53**, B lúc **16:21:21** và hai alert cùng firing lúc **16:23:51** ngày 26/11/2026 (GMT+7). Thời gian từ pending đến firing xấp xỉ giá trị `for` của từng rule. Scrape và chu kỳ đánh giá đều là 5 giây. Sau khi agent được tạo lại, Prometheus cần thu đủ mẫu để biểu thức `rate()` phản ánh tải mới. `AgentInstanceDown` có lúc pending trong khoảng 5–17 giây khi recreate, dưới điều kiện `for: 30s`.

Trong ảnh, giá trị của `AgentHighErrorRate` là khoảng **19.86%**, còn p95 của `AgentHighLatencyP95` khoảng **1.893 s**. B chạy trong khi A vẫn bật để thu bằng chứng cả hai firing. Kết quả B vì vậy phản ánh cấu hình kết hợp. `LLMCostBurnRateHigh` cũng từng firing trước thí nghiệm ở tải 30 users, khi tốc độ mô phỏng khoảng **0.00059 USD/s**, tương đương khoảng **2.1 USD/giờ**, vượt ngưỡng 2 USD/giờ. `promtool test rules` báo `SUCCESS`. [Ảnh Prometheus](screenshots/prometheus-alert-firing.png) · [Alert rules](06-lab-complete/benchmark-observability/production/prometheus/alert_rules.yml)

**Phát hiện suy giảm chất lượng:** Một câu sai có thể trả HTTP 200 với latency bình thường. Ví dụ CP7, `security-02` và `scaling-03` nhận câu chung chung trước khi bổ sung KB. Chạy eval định kỳ hoặc trong canary theo phiên bản, theo dõi accuracy và alert khi dưới 85% hoặc xuất hiện regression. Có thể theo dõi thêm tỷ lệ retrieval hit, chấm mẫu bằng người đánh giá hoặc LLM-as-judge, và dùng phản hồi của người dùng.

### 4.3 Debug bằng trace — Exercise 7.5

| Trace trong ảnh | Tổng thời gian | Phân tích |
|---|---:|---|
| Chậm, `6b9b59c35a98ffc1c08be2b69f4bd6eb` | 1713.5 ms | `chat mock-llm-small` mất **1687.3 ms**, khoảng **98.5%** thời gian request. `agent.retrieve_context` mất 23.6 ms và span cha `agent.run` mất 1711.1 ms. Điểm chậm nằm ở bước gọi mock LLM. [Ảnh trace chậm](screenshots/jaeger-slow-trace.png) |
| Lỗi, `fcd713184d4fc6ae4b924bd624b058b5` | 85.1 ms | `POST /ask` trả 503. Span LLM báo ERROR, `error.type=upstream_unavailable`, mất 64.3 ms. Span `agent.run` có exception `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`. [Ảnh trace lỗi](screenshots/jaeger-error-trace.png) |

Theo ghi chép lúc đo, log của trace chậm có `llm_call.llm_ms=1687.2` và `http_request.ms=1712.8`. Log của trace lỗi có cùng thông báo upstream error và `http_request.status=503`, `ms=84.6`. Một trace khác có số liệu chênh đáng kể giữa các nguồn nên đã được loại khỏi phân tích. Hai trace trong ảnh đã được xác nhận lại bằng ID đầy đủ từ Jaeger. Log thô tương ứng của hai container cũ không còn trong output Compose sau khi recreate agent.

**Đối chiếu bổ sung bằng log JSON gốc:** Các mẫu dưới đây lấy từ những request khác khi Locust vẫn chạy. Mỗi `trace_id` đã được tìm thấy cả trong Jaeger và trong log agent hiện tại.

- **Trace chậm bổ sung** `ff61e4e5330368af846ff7ea9cc34c74`. Jaeger đo `POST /ask` **1663.3 ms** và span LLM **1643.7 ms**.

```jsonl
{"ts":"2026-11-26T09:26:07.691772+00:00","level":"INFO","service":"observable-agent","instance":"5338f0553432","event":"llm_call","trace_id":"ff61e4e5330368af846ff7ea9cc34c74","span_id":"e1f3cd80f17eff41","request_id":"f2d7a5af29cd","model":"mock-llm-small","agent_version":"v2","input_tokens":95,"output_tokens":55,"cost_usd":0.000047,"llm_ms":1642.5}
{"ts":"2026-11-26T09:26:07.692230+00:00","level":"INFO","service":"observable-agent","instance":"5338f0553432","event":"http_request","trace_id":"ff61e4e5330368af846ff7ea9cc34c74","span_id":"e1f3cd80f17eff41","request_id":"f2d7a5af29cd","method":"POST","route":"/ask","status":200,"ms":1662.7}
```

- **Trace lỗi bổ sung** `b9a2bb7382f0cb35ac7707f3b9476983`. Jaeger đo `POST /ask` **861.4 ms** và span LLM **839.8 ms**.

```jsonl
{"ts":"2026-11-26T09:26:07.208402+00:00","level":"INFO","service":"observable-agent","instance":"5338f0553432","event":"llm_error","trace_id":"b9a2bb7382f0cb35ac7707f3b9476983","span_id":"3c875278360b581a","request_id":"87f622301735","error":"Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts":"2026-11-26T09:26:07.208748+00:00","level":"INFO","service":"observable-agent","instance":"5338f0553432","event":"http_request","trace_id":"b9a2bb7382f0cb35ac7707f3b9476983","span_id":"3c875278360b581a","request_id":"87f622301735","method":"POST","route":"/ask","status":503,"ms":860.8}
```

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

### Phương pháp

Tôi dừng tải 30 users từ Locust Web UI và xác nhận `stopped, users=0`. Hai lượt hợp lệ dùng cùng cấu hình mock mặc định, gồm `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01` và `MOCK_LATENCY_MS=120`. Mỗi lượt đặt **100 users**, tăng **10 users/giây** và chạy **2 phút**. Hai file history đều có **119 dòng** và ghi nhận đủ **100 users**. Số replicas trước và sau mỗi lượt giữ nguyên. Khi chạy 3 replicas, một phép kiểm tra riêng gửi 30 request qua Nginx và quan sát phân phối **10/10/10**.

Hai lần đo thử bị loại. Lần đầu, tải cũ vẫn chạy song song vì thao tác dừng gửi GET và nhận 405. Tôi dừng đúng bằng `POST /stop` rồi kiểm tra số user đã về 0. Lần kế tiếp, pipe qua `head` đóng sớm và Locust sinh CSV thiếu dữ liệu. Tôi chạy lại và ghi log ra file. Bảng sau dùng CSV của hai lượt cuối chạy đủ thời lượng.

### Kết quả tổng hợp

| Số instance | RPS tổng | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---:|---:|---:|---:|---:|
| 1 | 57.41 | 200 | 1400 | 2300 | 70 / 7280 (0.96%) |
| 3 | 62.03 | 190 | 240 | 1700 | 75 / 7847 (0.96%) |

Các cột trên lấy từ hàng `Aggregated`. [CSV 1 replica](benchmark-results/scale_1_stats.csv) · [CSV 3 replicas](benchmark-results/scale_3_stats.csv)

| Chỉ số theo endpoint | 1 replica | 3 replicas |
|---|---:|---:|
| Request `POST /ask` | 6648 | 7144 |
| RPS `/ask` | 52.43 | 56.47 |
| `/ask` avg (ms) | 352.0 | 235.2 |
| `/ask` p50 (ms) | 200 | 190 |
| `/ask` p90 (ms) | 610 | 220 |
| `/ask` p95 (ms) | 1500 | 240 |
| `/ask` p99 (ms) | 2300 | 1700 |
| `/ask` max (ms) | 6800.3 | 1774.3 |
| `GET /health` p95 (ms) | 360 | 11 |

Tất cả failures được Locust ghi nhận là HTTP 503 ở `POST /ask`. Tỷ lệ lỗi riêng trên `/ask` làm tròn là **1.05%** ở cả hai lượt, phù hợp với xác suất lỗi mô phỏng 1%. Tỷ lệ trên tổng request là **0.96%** vì mẫu số còn gồm các request `/health` thành công.

### Giải thích

- **Thông lượng tổng tăng nhẹ:** **57.41 → 62.03 RPS**, khoảng **8.0%**. Đây là tải vòng kín với 100 users cố định. Mỗi user chờ response rồi nghỉ 0.5–2 giây. Khoảng nghỉ trung bình 1.25 giây cùng thời gian xử lý giới hạn tốc độ sinh request mới, nên kết quả này chưa đo được thông lượng tối đa của stack 3 replicas. [Locustfile](06-lab-complete/benchmark-observability/production/locust/locustfile.py)
- **Tail latency giảm mạnh:** p95 của `/ask` giảm **84%**, từ **1500 xuống 240 ms**, tương đương nhanh hơn **6.25 lần** ở percentile này. Avg giảm khoảng **33%**, còn max giảm từ **6.8 s** xuống **1.77 s**. `/health` là endpoint nhẹ nhưng p95 cũng giảm từ **360 xuống 11 ms**. Các dấu hiệu này phù hợp với xếp hàng hoặc tranh chấp tài nguyên ở cấu hình 1 replica. Compose giới hạn mỗi replica ở **0.5 CPU**. Chưa có số đo CPU hoặc throttling để khẳng định CPU là nút thắt. [Giới hạn tài nguyên Compose](06-lab-complete/benchmark-observability/production/docker-compose.yml)
- **p99 còn 1700 ms với 3 replicas:** Phù hợp với nhóm request mock có thêm 1500 ms. Tăng số replica giảm thời gian chờ tại agent nhưng vẫn còn độ trễ do mock LLM tạo ra. Tỷ lệ lỗi gần như giữ nguyên khi xác suất lỗi upstream giữ nguyên.

### Điều chỉnh Dockerfile khi chạy CP8

Tôi thêm `ENV PYTHONUSERBASE=/home/agent/.local` vào Dockerfile của stack observability. App chạy dưới user `agent` có home là `/app`, còn dependencies của Python được copy vào `/home/agent/.local`. Biến này giúp Python tìm đúng dependencies, gồm Uvicorn. [Dockerfile CP8](06-lab-complete/benchmark-observability/production/Dockerfile#L26-L35)

## 6. Kết luận

1. p95 và p99 giúp thấy các request chậm bị che khuất bởi trung bình. Trong phép đo này, 3 replicas cải thiện rõ độ trễ dù RPS tổng chỉ tăng khoảng 8%.
2. Chất lượng câu trả lời cần eval riêng. v2 đạt **23/23** sau khi sửa KB. Alert HTTP và latency vẫn có thể xanh khi một câu trả lời sai.
3. Metrics chỉ ra hiện tượng theo thời gian. Trace cho biết bước chậm nằm ở mock LLM, còn log cùng `trace_id` giúp đối chiếu latency và lỗi 503.

Nếu chạy production thật, tôi sẽ bổ sung metric **CPU throttling và thời gian chờ hàng đợi theo instance** để kiểm chứng nguyên nhân của tail latency. Tôi cũng sẽ theo dõi **accuracy và regression theo phiên bản** từ eval định kỳ, cùng **tỷ lệ lỗi upstream LLM** để phân biệt sự cố model với sự cố tại API.
