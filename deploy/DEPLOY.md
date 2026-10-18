# Deploy Bẫy Ngược lên GreenNode AgentBase

Mọi lệnh chạy tại thư mục dự án. Công cụ `deploy/agentbase.py` gọi đúng các REST API của bộ AgentBase Skills chính thức
và **không bao giờ in secret**.

## 0. Thông tin xác thực (chỉ trên máy local)

Cách 1 – từ file credentials BTC cấp (chỉ đọc IAM Client ID/Secret + MaaS Base URL/API key, KHÔNG dùng mật khẩu Root):

```bash
.venv/Scripts/python.exe deploy/load_credentials.py ../Credentials.txt
```

Cách 2 – gõ tay (secret nhập ẩn):

```bash
.venv/Scripts/python.exe deploy/agentbase.py login
```

Kết quả: `.greennode.json` (IAM) và `.env` (MaaS, dùng khi chạy local). Cả hai nằm trong `.gitignore` và `.dockerignore`.

## 1. Kiểm tra

```bash
.venv/Scripts/python.exe deploy/agentbase.py check
.venv/Scripts/python.exe deploy/agentbase.py models
```

## 2. Tài nguyên cho runtime

```bash
.venv/Scripts/python.exe deploy/agentbase.py llm-key --name bay-nguoc-runtime   # key MaaS RIÊNG cho runtime -> .env.runtime
.venv/Scripts/python.exe deploy/agentbase.py memory --name bay-nguoc-rings       # AgentBase Memory -> MEMORY_ID
```

## 3. Build → push vCR → tạo/cập nhật runtime → chờ ACTIVE → in endpoint

```bash
.venv/Scripts/python.exe deploy/agentbase.py deploy --name bay-nguoc --flavor runtime-s2-general-2x4 --poc false
```

Tài khoản thi không được dùng ví POC cho runtime (`check` báo `False`), nên runtime trừ vào Cloud Credit của đội (`--poc false`).
Chạy lại cùng lệnh để ra phiên bản mới; endpoint DEFAULT giữ nguyên URL.

## 4. Trước khi nộp

```bash
.venv/Scripts/python.exe deploy/agentbase.py status --name bay-nguoc
.venv/Scripts/python.exe deploy/agentbase.py logs --name bay-nguoc
```

- Mở endpoint bằng **tab ẩn danh**, bấm "Điều tra ngay" phải chạy được.
- **Không tắt runtime** từ lúc nộp đến hết 22/10/2026.
- Theo dõi chi phí: https://docs.greennode.ai/ai-stack/usage-budget
