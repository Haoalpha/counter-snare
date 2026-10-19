# COUNTER-SNARE (Bẫy Ngược)
### Autonomous Mule Ring Hunter & STR Intelligence Platform

**Smart Banking 2026 – AI Hackathon · Track C: Risk, Compliance & Fraud Defense**
Chạy trên **GreenNode AgentBase** (Runtime, Container Registry, Memory, IAM) + **GreenNode MaaS** (Qwen 3.8 Flash, Gemma 4, GLM 5.3 Flash, GLM 5.2, bge-m3).

**Link demo (AgentBase Runtime – mở bằng tab ẩn danh):** https://endpoint-5d5628a3-07a3-459d-a6ad-aa3ca09f389c.agentbase-runtime.aiplatform.vngcloud.vn

> Từ **một tin nhắn lừa đảo** khách hàng chuyển tiếp (hoặc một cảnh báo của hệ thống giám sát), COUNTER-SNARE tìm ra **toàn bộ đường dây tài khoản mule**,
> giải thích vì sao từng tài khoản bị nghi ngờ (Shapley XAI gắn Điều 27–28 Luật PCRT 2022) và soạn **dự thảo báo cáo giao dịch đáng ngờ (STR)**
> mà mọi con số đều truy vết được về kho bằng chứng. Agent **không có quyền** tự trì hoãn giao dịch, nộp STR hay phong tỏa:
> Policy Gateway chặn, chỉ chuyên viên PCRT được duyệt (Human-in-the-Loop). Cảnh báo giả được **tự đóng kèm lý do**, không sinh STR sai.

## 1. Vấn đề

- Tài khoản mule (thuê/mua/mở bằng eKYC giả) **vượt qua KYC và trông bình thường khi xét riêng lẻ** – tín hiệu nằm ở **mạng lưới** liên kết.
- SIMO (NHNN) ghi nhận ~688 nghìn bản ghi tài khoản/ví/thẻ nghi gian lận (23/3/2026), cảnh báo 4,6 triệu lượt khách, bảo vệ hơn 5.200 tỷ đồng (29/6/2026).
- Giám sát theo luật sinh rất nhiều **cảnh báo giả** (dữ liệu thử nghiệm: 84%); soạn STR thủ công mất nhiều giờ trong khi Điều 37 Luật PCRT 2022 yêu cầu báo cáo trong **01 ngày làm việc kể từ khi phát hiện**.

## 2. Giải pháp

| Thành phần | Làm gì | Công nghệ |
|---|---|---|
| **Threat Ingestion & Zero-Trust Guardrails** | Nhận tin nhắn lừa đảo / cảnh báo TM; persona mồi nhử **"Grandma Tu" (Bà Tư AI)** moi số tài khoản nhận tiền (mô phỏng) | Regex-first extraction (LLM chỉ được chọn ứng viên), chống prompt injection, che PII |
| **Mule Ring Hunter & Forensic Graph** | Mở rộng đồ thị dòng tiền + thiết bị dùng chung từ 1 tài khoản hạt giống, gán vai trò (gom / trung chuyển / rút ra / nạn nhân / bị chiếm quyền) | 21 đặc trưng hành vi ánh xạ Điều 27–28, Gradient Boosting **ràng buộc đơn điệu**, giải thích **Shapley (Monte-Carlo)** |
| **Forensic Evidence & STR Synthesis** | Kho bằng chứng EV-xx sinh **tất định** từ sổ cái → LLM soạn STR chỉ được trích EV → **Agent-as-a-Judge** kiểm từng con số, tự sửa câu sai | LangGraph, GreenNode MaaS, RAG căn cứ pháp lý (bge-m3) |
| **Policy Gate & HITL** | Agent thử tự hành động pháp lý → **DENY** (first-match-wins); chuyên viên ký duyệt, phong tỏa cần số quyết định cơ quan có thẩm quyền | Policy Gateway + audit trail |
| **Red Arena** | LLM Red Team lập kế hoạch chiến dịch né phát hiện → bộ mô phỏng thực thi → đo khả năng bắt → điểm mù trở thành dữ liệu huấn luyện (**tự tiến hóa**) | Mô phỏng đối kháng planning–execution, dữ liệu 100% tổng hợp |
| **Alert Triage** | Tự đóng cảnh báo giả có lý do, leo thang ca thật, chuyển nạn nhân bị chiếm quyền sang bảo vệ khách hàng | Cùng risk engine + reason codes |
| **AgentBase Memory** | "Dấu vân tay đường dây" (tài khoản, thiết bị) lưu dài hạn, nhận ra đường dây cũ quay lại | `bay-nguoc-rings` |

### Thực tiễn của ngân hàng hàng đầu thế giới được hiện thực

| Thực tiễn (JPMorgan) | COUNTER-SNARE |
|---|---|
| [Explainable AI Center of Excellence](https://www.jpmorgan.com/technology/artificial-intelligence/initiatives/explainable-ai-center-of-excellence) | Shapley attribution + lý do gắn điều luật + mô hình đơn điệu |
| [LLM phát hiện gian lận, giảm cảnh báo giả](https://americanbanker.com/news/jpmorgan-chase-using-chatgpt-like-large-language-models-to-detect-fraud) | Alert Triage: −78% khối lượng, 0 mule bị bỏ sót |
| ["Mosaic" nhiều tín hiệu & "intelligent exception handling"](https://www.jpmorgan.com/payments/payments-unbound/magazine/articles/next-gen-approaches-payments-privacy-security) | 21 đặc trưng đa tín hiệu; Policy Gateway buộc con người quyết định |
| Nền tảng đa-model [LLM Suite](https://www.ciodive.com/news/JPMorgan-Chase-LLM-Suite-generative-ai-employee-tool/726772/) | LLM Gateway định tuyến theo tác vụ trên 4 model MaaS, giới hạn RPM theo quy định BTC |
| [Chặn "rogue agents"](https://fortune.com/2026/10/15/jamie-dimon-ai-agents-meta-muse-jpmorgan/) (10/2026) | Agent zero-trust: chỉ đọc & soạn thảo, mọi tool qua gateway, ghi kiểm toán |

## 3. Trung tâm Tác chiến An ninh Tài chính (Ops Center)

Không có nút "preset", không có stepper bắt người dắt tay AI. Người dùng (hoặc **Autopilot**) đưa một mối đe dọa vào; **Orchestrator tự quyết định**
cử agent nào, theo kịch bản nào, và mọi bước được phát trực tiếp lên **Agentic Thought Stream**:

- **Threat Inbox (trực tiếp)**: báo cáo khách hàng từ nhiều kênh (app, Zalo, hotline, email, quầy) và cảnh báo TM của hệ thống giám sát theo luật đến dần theo thời gian;
  ô *Report a new threat* nhận bất kỳ văn bản nào; **Simulate unseen threat** để LLM viết một tin nhắn lừa đảo **mới hoàn toàn** cho một đường dây ngẫu nhiên trong sổ cái
  (chứng minh hệ thống không trả JSON dựng sẵn). Bật **Autopilot** để Orchestrator tự nhận việc theo mức ưu tiên.
- **Orchestrator tự chọn playbook**: có tài khoản trong sổ cái → điều tra; **chưa lộ tài khoản → tự cử Decoy Agent** (persona "Bà Tư", mô phỏng LLM-đối-LLM) đến khi kẻ gian đọc
  ra tài khoản rồi tự quay lại điều tra; tài khoản ngân hàng khác → chuyển SIMO/liên ngân hàng; không có đường dây → đóng dương tính giả kèm lý do.
- **Agentic Thought Stream**: suy nghĩ của từng agent, **tool call** (tham số, kết quả, ms), **lệnh gọi GreenNode MaaS** (model, độ trễ, token), quyết định **Policy Gateway**
  (ALLOW/DENY), hội thoại mồi nhử từng lượt, và **thẻ phê duyệt Human-in-the-Loop** ngay trong luồng (Approve / Reject, phong tỏa cần số quyết định cơ quan có thẩm quyền).
  Kỹ thuật: event bus (`app/events.py`) + run store, giao diện polling `GET /api/ops/events/{case}?after=N`.
- **Case Board**: KPI, đồ thị đường dây **mọc dần theo từng hop**, Shapley XAI từng tài khoản, kho bằng chứng EV-xx, dự thảo STR có chứng nhận Judge, sổ hành động.
- **Analyst Copilot**: hỏi đáp về vụ việc bằng tiếng Việt/Anh, **chỉ được trích kho bằng chứng** (mã EV không tồn tại bị gỡ), qua guardrail chống prompt injection, không có quyền hành động.

Thiết kế theo bộ skill *UI/UX Pro Max*: giao diện ngân hàng sáng (đỏ burgundy + be nhạt), IBM Plex Sans/Mono, icon SVG Lucide, focus rõ, tôn trọng reduced-motion,
responsive 375–1760px; đồ thị phân loại bằng **màu + hình dạng**. Các tab khác: **Red Arena**, **Alert Triage**, **Governance** (runtime, RPM, audit trail, Policy Group, kiến trúc).

## 4. Tuân thủ quy định kỹ thuật của BTC

- **Image agent deploy trên GreenNode AgentBase** (Custom Agent runtime, image trên AgentBase Container Registry).
- **Chỉ dùng model GreenNode MaaS**; không dùng model bên ngoài.
- **Rate limit theo user**: GLM 5.2 = 15, GLM 5.3 Flash = 10, Qwen 3.8 Flash = 10, Gemma 4 = 15 RPM. `app/llm.py` giới hạn cửa sổ trượt 60s từng model (chừa 1 request an toàn), hết hạn mức thì chuyển model, tất cả hết thì chờ có giới hạn rồi rơi về template tất định; có test `tests/test_rate_limit.py`. Theo dõi trực tiếp ở tab Governance (`/api/llm_status`).
- **Bí mật**: key MaaS của runtime là key **riêng** tạo bằng IAM (`deploy/agentbase.py llm-key`); `.env`, `.env.runtime`, `.greennode.json` không nằm trong repo hay image.
- Theo dõi chi phí MaaS: https://docs.greennode.ai/ai-stack/usage-budget

## 5. Kết quả đánh giá (dữ liệu tổng hợp)

Giao thức: huấn luyện trên 3 thế giới tổng hợp (3 thủ đoạn); đánh giá trên **thế giới chưa từng thấy** (seed khác, thêm thủ đoạn "chiếm quyền điện thoại"
không có khi huấn luyện) và **Red Arena** 3 mức độ × 5 seed độc lập. Xem `data/eval.json` (sinh khi build).

| Chỉ số | Kết quả |
|---|---|
| Khoanh vùng đường dây từ 1 tài khoản (6 đường dây, gồm thủ đoạn chưa thấy) | 44/44 mule, 84/84 nạn nhân, 0 tài khoản thừa |
| Alert Triage: 278 cảnh báo, 234 là giả | Tự đóng đúng 217, leo thang 44/44 mule, 17 chuyển bảo vệ nạn nhân, **0 mule bị bỏ sót**, −78% khối lượng |
| Red Arena mức "Khó" (giữ tiền 4–33 giờ, không chia nhỏ, không dùng chung thiết bị) | v1: **0%** → v2 (tự tiến hóa): **100%**, không tăng cảnh báo nhầm |
| Tin nhắn → hồ sơ STR có Judge (LLM thật trên MaaS) | ~20–25 giây; cảnh báo giả đóng trong ~5 giây |

**Giới hạn trung thực:** số liệu đo trên dữ liệu **tổng hợp** do chính bộ mô phỏng sinh ra nên lạc quan hơn thực tế.
Triển khai thật bắt đầu bằng **shadow mode** trên dữ liệu ngân hàng (chạy song song, không can thiệp) để đo lại.

## 6. An toàn, bảo mật & tuân thủ

- **Human-in-the-loop ép buộc ở tầng gateway** (`app/policy.py`, first-match-wins): agent chỉ ALLOW `read_*`, `draft_*`, `memory_*`; DENY `delay_transactions` (Điều 44), `submit_str` (Điều 26), `freeze_account` (Điều 45 – chỉ khi có quyết định cơ quan có thẩm quyền).
- **Chống prompt injection**: tin nhắn kẻ gian là dữ liệu thù địch; LLM **không có quyền** đổi điểm rủi ro.
- **Chống bịa**: số tài khoản trích bằng regex; mọi con số trong STR phải khớp kho bằng chứng EV-xx (Judge tất định + rubric LLM), câu sai được thay bằng câu sinh từ dữ liệu.
- **Bảo vệ dữ liệu cá nhân**: che SĐT/CCCD/email trước khi gửi LLM, che tên chủ tài khoản trong STR; model chạy trên GreenNode MaaS tại Việt Nam.
- **Kiểm toán**: mọi lệnh gọi LLM / tool / quyết định policy / phê duyệt ghi vết (`/api/audit`).
- **Căn cứ pháp lý**: Luật Phòng, chống rửa tiền 2022 (14/2022/QH15) Điều 26, 27, 28, 37, 44, 45; QĐ 2345/QĐ-NHNN; Luật Bảo vệ dữ liệu cá nhân 2025; Quy chế phối hợp NHNN – Bộ Công an (23/6/2026).
- **Persona mồi nhử** chỉ chạy **mô phỏng** (LLM đối LLM). Ngoài đời mặc định là thụ động (khách chuyển tiếp tin nhắn); chủ động chỉ khi phối hợp cơ quan công an.

## 7. Kiến trúc trên GreenNode

```
Ops Center (UI) ──► AgentBase Runtime (Custom Agent, container :8080)
                      ├─ GET /health · POST /invocations (AgentBase SDK) · GET / + /static + /api/* + /api/ops/*
                      ├─ Orchestrator (playbook) ─┬─► Decoy Agent (khi chưa lộ tài khoản) ─┐
                      │                           └──────────────────────────────────────────┴─► LangGraph:
                      │      Guardrail → Intel → Ring Hunter ─┬─► Investigator → Judge → Policy → Memory
                      │                                       └─► False-positive closure (no STR)
                      ├─ Event bus → Agentic Thought Stream · Analyst Copilot (grounded on EV-xx)
                           ├─► GreenNode MaaS qua LLM Gateway (định tuyến theo tác vụ + RPM guard), bge-m3 (RAG)
                           └─► AgentBase Memory (ring fingerprints)
Image: build → push AgentBase Container Registry (vcr.vngcloud.vn) → runtime PUBLIC
```

## 8. Chạy thử

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip
python -m scripts.build_assets        # sinh dữ liệu tổng hợp, huấn luyện, đánh giá -> data/
cp .env.example .env                  # điền LLM_API_KEY (GreenNode MaaS); để trống = chế độ offline
python main.py                        # http://localhost:8080
python -m pytest -q                   # 19 bài kiểm thử (end-to-end, orchestrator tự chủ, copilot, false-positive, honeypot, Shapley, rate limit)
```

Gọi agent theo chuẩn AgentBase:

```bash
curl -X POST "$ENDPOINT/invocations" -H "Content-Type: application/json" \
  -H "X-GreenNode-AgentBase-Session-Id: s1" -H "X-GreenNode-AgentBase-User-Id: u1" \
  -d '{"message": "Chuyển ngay 50 triệu vào tài khoản 1903xxxxxxxx ngân hàng NHX ..."}'
```

Deploy: xem `deploy/DEPLOY.md` (`deploy/agentbase.py deploy` = build → push vCR → tạo/cập nhật runtime → chờ ACTIVE).

## 9. Khai báo xuất xứ (bắt buộc theo thể lệ)

- **Dữ liệu**: 100% **tổng hợp** do `app/simulator.py` sinh ra (tên, số tài khoản, giao dịch đều giả); ngân hàng dùng mã giả định (NHX, NHB…). Không dùng dữ liệu khách hàng/giao dịch thật.
  Kỹ thuật mô phỏng planning–execution tham khảo bài báo Borrajo, Veloso, Shah – *Simulating and classifying behavior in adversarial environments based on action-state traces* (ICAIF 2020).
  Số liệu SIMO trích từ thông cáo báo chí của NHNN.
- **Ý tưởng tham khảo**: Co-Investigator AI (arXiv 2509.08380 – agent soạn STR + Agent-as-a-Judge); Apate.ai (bot mồi nhử thu thập tài khoản mule);
  ScamBot/VictimBot (arXiv 2601.03134); bộ sinh Tide (arXiv 2601.21446) cho thấy GBM cạnh tranh tốt với GNN trên dữ liệu AML.
- **Mã nguồn**: toàn bộ code viết trong Build Week (16–21/10/2026), có hỗ trợ của công cụ lập trình AI (Claude Code).
  Thư viện mã nguồn mở: LangGraph, OpenAI Python SDK (gọi endpoint OpenAI-compatible của GreenNode), scikit-learn, pandas, Starlette/uvicorn;
  giao diện: Tailwind CSS (CDN), vis-network, Lucide icons, Google Fonts (IBM Plex Sans/Mono). SDK nền tảng: `greennode-agentbase`.
- **Mô hình**: GreenNode MaaS – `qwen/qwen3.8-flash`, `google/gemma-4-31b-it`, `z-ai/glm-5.3-flash-thirdparty`, `z-ai/glm-5.2-hackathon`, `baai/bge-m3`; mô hình chấm điểm mule tự huấn luyện trên dữ liệu tổng hợp.
- **Không chứa** key/credential/password trong repo (`.env`, `.env.runtime`, `.greennode.json` nằm trong `.gitignore`).
