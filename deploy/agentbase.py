"""Công cụ deploy Bẫy Ngược lên GreenNode AgentBase (Python thuần, không cần jq).

Gọi đúng các REST API mà bộ AgentBase Skills chính thức (github.com/vngcloud/greennode-agentbase-skills) sử dụng.
Nguyên tắc bảo mật: KHÔNG BAO GIỜ in secret ra màn hình; secret chỉ đi qua bộ nhớ hoặc stdin của `docker login`.

Thông tin xác thực IAM Service Account: biến môi trường GREENNODE_CLIENT_ID / GREENNODE_CLIENT_SECRET
hoặc file .greennode.json {"client_id": "...", "client_secret": "..."} ở thư mục dự án (đã nằm trong .gitignore).

Lệnh:
  python deploy/agentbase.py check                       # kiểm tra token, registry, ví POC, flavor
  python deploy/agentbase.py models                      # liệt kê model MaaS
  python deploy/agentbase.py llm-key --name bay-nguoc-key  # tạo API key MaaS, ghi thẳng vào .env (không in ra)
  python deploy/agentbase.py deploy --name bay-nguoc --flavor 1x1-general --poc true|false
  python deploy/agentbase.py status --name bay-nguoc
  python deploy/agentbase.py logs --name bay-nguoc
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IAM_TOKEN_URL = "https://iam.api.vngcloud.vn/accounts-api/v2/auth/token"
RUNTIME_URL = "https://agentbase.api.vngcloud.vn/runtime"
CR_URL = "https://agentbase.api.vngcloud.vn/cr/api/v1"
AIP_URL = "https://aiplatform-hcm.api.vngcloud.vn"
AUTO_INJECTED = {"GREENNODE_CLIENT_ID", "GREENNODE_CLIENT_SECRET", "GREENNODE_AGENT_IDENTITY", "GREENNODE_ENDPOINT_URL"}
SECRET_KEYS = {"password", "secret", "key", "client_secret", "access_token", "secretKey", "encryptedPassword"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def redact(o):
    if isinstance(o, dict):
        return {k: ("********" if k in SECRET_KEYS and v else redact(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(x) for x in o]
    return o


def show(o) -> None:
    print(json.dumps(redact(o), ensure_ascii=False, indent=2))


def die(msg: str) -> None:
    print("LỖI: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------------- auth ----------------
_TOKEN = None


def credentials() -> tuple[str, str]:
    cid, sec = os.environ.get("GREENNODE_CLIENT_ID", ""), os.environ.get("GREENNODE_CLIENT_SECRET", "")
    f = ROOT / ".greennode.json"
    if (not cid or not sec) and f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        cid, sec = d.get("client_id", ""), d.get("client_secret", "")
    if not cid or not sec:
        die("Chưa có IAM Service Account. Tạo tại https://iam.console.vngcloud.vn/service-accounts rồi lưu vào "
            f"{f} dạng {{\"client_id\": \"...\", \"client_secret\": \"...\"}} (xem deploy/DEPLOY.md).")
    return cid, sec


def token() -> str:
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    cid, sec = credentials()
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    req = urllib.request.Request(IAM_TOKEN_URL, data=b"grant_type=client_credentials", method="POST",
                                 headers={"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _TOKEN = json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        die(f"Lấy IAM token thất bại (HTTP {e.code}). Kiểm tra client_id/client_secret và quyền của service account.")
    return _TOKEN


def api(method: str, url: str, body: dict | None = None, ok_codes=(200, 201, 202, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            detail = redact(json.loads(raw))
        except Exception:
            detail = raw[:500]
        die(f"{method} {url} -> HTTP {e.code}: {json.dumps(detail, ensure_ascii=False)[:800]}")


def unwrap(d):
    return d.get("data", d) if isinstance(d, dict) and isinstance(d.get("data"), (dict, list)) else d


# ---------------- commands ----------------
def can_use_poc() -> bool | None:
    d = api("GET", f"{AIP_URL}/v1/runtime-billing/can-use-poc")
    v = d.get("canUseRuntimePoc", (d.get("data") or {}).get("canUseRuntimePoc") if isinstance(d.get("data"), dict) else None)
    return v if isinstance(v, bool) else None


def cr_repo() -> dict:
    return unwrap(api("GET", f"{CR_URL}/repository"))


def cr_creds() -> dict:
    return unwrap(api("GET", f"{CR_URL}/registry-credential"))


def flavors() -> list:
    d = api("GET", f"{RUNTIME_URL}/flavors")
    return d.get("listData", d.get("data", d)) if isinstance(d, dict) else d


def cmd_login(a) -> None:
    import getpass
    print("Nhập thông tin IAM Service Account (tạo tại https://iam.console.vngcloud.vn/service-accounts).")
    cid = input("Client ID: ").strip()
    sec = getpass.getpass("Client Secret (gõ sẽ không hiện): ").strip()
    if not cid or not sec:
        die("Thiếu Client ID hoặc Client Secret")
    f = ROOT / ".greennode.json"
    f.write_text(json.dumps({"client_id": cid, "client_secret": sec}), encoding="utf-8")
    global _TOKEN
    _TOKEN = None
    os.environ.pop("GREENNODE_CLIENT_ID", None)
    os.environ.pop("GREENNODE_CLIENT_SECRET", None)
    token()
    print(f"✔ Đã lưu {f.name} (nằm trong .gitignore/.dockerignore) và xác thực IAM thành công.")


def cmd_check(a) -> None:
    token()
    print("✔ IAM token OK")
    repo = cr_repo()
    print(f"✔ Container Registry: {repo.get('registryUrl')}/{repo.get('name')}  (images: {repo.get('imageCount')}, quota: {repo.get('quotaUsed')}/{repo.get('quotaLimit')})")
    print(f"✔ Có thể dùng ví POC (credit cuộc thi) cho runtime: {can_use_poc()}")
    fl = flavors()
    print("✔ Flavor hỗ trợ agent-runtime (PUBLIC):")
    for f in fl if isinstance(fl, list) else []:
        if "agent-runtime" in (f.get("supportedResourceTypes") or []):
            print(f"   - {f.get('id') or f.get('name')}: {json.dumps({k: f.get(k) for k in ('cpu', 'memory', 'ram', 'description') if f.get(k) is not None}, ensure_ascii=False)}")


def cmd_models(a) -> None:
    d = api("GET", f"{AIP_URL}/v1/models?page=1&size=100")
    items = d.get("listData", d.get("data", []))
    if isinstance(items, dict):
        items = items.get("listData", [])
    for m in items:
        print(f"- {m.get('modelName') or m.get('name')}  status={m.get('modelStatus') or m.get('status')}  type={m.get('modelType') or m.get('type')}")


def write_env(key: str, value: str, target: str = ".env") -> None:
    env = ROOT / target
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    out, done = [], False
    for ln in lines:
        if ln.startswith(key + "="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_llm_key(a) -> None:
    resp = api("POST", f"{AIP_URL}/v2/api-keys", {"name": a.name, "isDefault": False})
    key = (resp.get("data") or {}).get("key") if isinstance(resp.get("data"), dict) else resp.get("key")
    for _ in range(20):
        if key:
            break
        time.sleep(3)
        g = api("GET", f"{AIP_URL}/v1/api-keys/{urllib.parse.quote(a.name)}")
        key = (g.get("data") or {}).get("key") if isinstance(g.get("data"), dict) else g.get("key")
    if not key:
        die("Đã gửi yêu cầu tạo key nhưng chưa lấy được giá trị. Chạy lại lệnh sau ít phút: python deploy/agentbase.py llm-key-get --name " + a.name)
    write_env("LLM_API_KEY", key, a.out)
    print(f"✔ Đã tạo API key MaaS '{a.name}' và ghi vào {a.out} (LLM_API_KEY) – giá trị không được in ra.")


def cmd_llm_key_get(a) -> None:
    g = api("GET", f"{AIP_URL}/v1/api-keys/{urllib.parse.quote(a.name)}")
    key = (g.get("data") or {}).get("key") if isinstance(g.get("data"), dict) else g.get("key")
    if not key:
        die("Key chưa sẵn sàng (trạng thái chưa ACTIVE?).")
    write_env("LLM_API_KEY", key, a.out)
    print(f"✔ Đã ghi LLM_API_KEY vào {a.out} (không in ra).")


MEMORY_URL = "https://agentbase.api.vngcloud.vn/memory/memories"


def cmd_memory(a) -> None:
    """Tạo (nếu chưa có) AgentBase Memory lưu 'dấu vân tay đường dây' và ghi MEMORY_ID/MEMORY_STRATEGY_ID vào .env + .env.runtime."""
    d = api("GET", f"{MEMORY_URL}?page=1&size=100")
    mem = next((m for m in d.get("listData", []) if m.get("name") == a.name), None)
    if not mem:
        body = {"name": a.name, "description": "Dau van tay duong day mule (tai khoan, thiet bi) - Bay Nguoc",
                "eventExpiryDuration": 30,
                "longTermMemoryStrategies": [{"name": "ring-fingerprints", "type": "SEMANTIC",
                                              "enableAutomaticMemoryRecordGeneration": False,
                                              "namespaceTemplate": "/strategies/{memoryStrategyId}/actors/{actorId}"}]}
        mem = unwrap(api("POST", MEMORY_URL, body))
        print(f"✔ Đã tạo AgentBase Memory '{a.name}'")
    mid = mem.get("id")
    for _ in range(30):
        cur = unwrap(api("GET", f"{MEMORY_URL}/{mid}"))
        if str(cur.get("status", "ACTIVE")).upper() in ("ACTIVE", "READY", "AVAILABLE"):
            break
        print(f"  trạng thái memory: {cur.get('status')}")
        time.sleep(5)
    st = api("GET", f"{MEMORY_URL}/{mid}/long-term-memory-strategies")
    items = st.get("listData", st.get("data", st)) if isinstance(st, dict) else st
    sid = (items[0].get("id") or items[0].get("strategyId")) if isinstance(items, list) and items else "default"
    for target in (".env", ".env.runtime"):
        if (ROOT / target).exists():
            write_env("MEMORY_ID", mid, target)
            write_env("MEMORY_STRATEGY_ID", sid, target)
    print(f"✔ MEMORY_ID={mid} MEMORY_STRATEGY_ID={sid} -> .env, .env.runtime")


def read_env_file(name: str = ".env.runtime") -> dict:
    env = ROOT / name
    if not env.exists():
        return {}
    out = {}
    for ln in env.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.lstrip().startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip()
        if k in AUTO_INJECTED or not v.strip():
            continue
        out[k] = v.strip()
    return out


def find_runtime(name: str) -> dict | None:
    page = 1
    while True:
        d = api("GET", f"{RUNTIME_URL}/agent-runtimes?page={page}&size=100")
        for r in d.get("listData", []):
            if r.get("name") == name:
                return r
        if page >= int(d.get("totalPage") or 1):
            return None
        page += 1


def sh(cmd: list[str], stdin: str | None = None) -> None:
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd, input=stdin, text=True, cwd=ROOT)
    if r.returncode != 0:
        die(f"Lệnh thất bại: {' '.join(cmd)}")


def cmd_deploy(a) -> None:
    repo = cr_repo()
    image = f"{repo['registryUrl']}/{repo['name']}/{a.name}:{a.tag or 'v' + datetime.now().strftime('%Y%m%d%H%M%S')}"
    creds = cr_creds()
    if not a.skip_build:
        sh(["docker", "build", "--platform", "linux/amd64", "-t", image, "."])
    sh(["docker", "login", repo["registryUrl"], "-u", creds["username"], "--password-stdin"], stdin=creds["secret"])
    sh(["docker", "push", image])
    env = read_env_file(a.env_file)
    if "LLM_API_KEY" not in env:
        print(f"⚠ {a.env_file} chưa có LLM_API_KEY: agent sẽ chạy chế độ offline (template).")
    body = {
        "imageUrl": image, "flavorId": a.flavor, "description": "Bay Nguoc - AML mule ring hunter (Smart Banking 2026)",
        "command": [], "args": [], "environmentVariables": env,
        "autoscaling": {"minReplicas": 1, "maxReplicas": a.max_replicas, "cpuUtilization": 60, "memoryUtilization": 70},
        "imageAuth": {"enabled": True, "username": creds["username"], "password": creds["secret"]},
    }
    existing = find_runtime(a.name)
    if existing:
        cur = api("GET", f"{RUNTIME_URL}/agent-runtimes/{existing['id']}")
        body["poc"] = cur.get("poc", False) if isinstance(cur.get("poc"), bool) else False
        print(f"→ Cập nhật runtime {a.name} ({existing['id']}) lên image mới…")
        api("PATCH", f"{RUNTIME_URL}/agent-runtimes/{existing['id']}", body)
        rid = existing["id"]
    else:
        poc = a.poc == "true"
        if poc and can_use_poc() is not True:
            die("Tài khoản không được dùng ví POC cho runtime. Chạy lại với --poc false.")
        body.update({"name": a.name, "poc": poc})
        print(f"→ Tạo runtime {a.name} (flavor {a.flavor}, ví {'POC' if poc else 'thật'})…")
        r = api("POST", f"{RUNTIME_URL}/agent-runtimes", body)
        rid = unwrap(r).get("id")
    wait_active(rid)
    url = endpoint_url(rid)
    print(f"\n✔ DEPLOY XONG\n  Runtime ID: {rid}\n  Image:      {image}\n  Endpoint:   {url}\n  Console:    https://aiplatform.console.vngcloud.vn/agent-runtime?tab=runtime")
    if url:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=30) as r:
                print(f"  Health:     HTTP {r.status}")
        except Exception as e:
            print(f"  Health:     chưa phản hồi ({e}); thử lại sau ít phút")


def wait_active(rid: str, timeout: int = 900) -> None:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        r = api("GET", f"{RUNTIME_URL}/agent-runtimes/{rid}")
        st = r.get("status")
        if st != last:
            print(f"  trạng thái: {st} {r.get('statusReason') or ''}")
            last = st
        if st == "ACTIVE":
            return
        if st in ("ERROR", "FAILED"):
            die(f"Runtime lỗi: {r.get('statusReason')}. Xem log: python deploy/agentbase.py logs --name <tên>")
        time.sleep(10)
    die("Quá thời gian chờ ACTIVE")


def endpoint_url(rid: str) -> str | None:
    d = api("GET", f"{RUNTIME_URL}/agent-runtimes/{rid}/endpoints?page=1&size=20")
    for e in d.get("listData", []):
        if e.get("name") == "DEFAULT":
            return e.get("url")
    lst = d.get("listData", [])
    return lst[0].get("url") if lst else None


def cmd_status(a) -> None:
    r = find_runtime(a.name)
    if not r:
        die(f"Không tìm thấy runtime '{a.name}'")
    show(api("GET", f"{RUNTIME_URL}/agent-runtimes/{r['id']}"))
    show(api("GET", f"{RUNTIME_URL}/agent-runtimes/{r['id']}/endpoints?page=1&size=20"))


def cmd_logs(a) -> None:
    r = find_runtime(a.name)
    if not r:
        die(f"Không tìm thấy runtime '{a.name}'")
    d = api("GET", f"{RUNTIME_URL}/agent-runtimes/{r['id']}/endpoints?page=1&size=20")
    ep = next((e for e in d.get("listData", []) if e.get("name") == "DEFAULT"), None)
    if not ep:
        die("Chưa có endpoint")
    now = int(time.time() * 1000)
    body = {"from": 0, "limit": a.limit, "query": "", "fromTimestamp": str(now - 3600_000), "toTimestamp": str(now), "order": "desc"}
    show(api("POST", f"{RUNTIME_URL}/agent-runtimes/{r['id']}/endpoints/{ep['id']}/logs", body))


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy Bẫy Ngược lên GreenNode AgentBase")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("check")
    sub.add_parser("models")
    k = sub.add_parser("llm-key")
    k.add_argument("--name", default="bay-nguoc-runtime")
    k.add_argument("--out", default=".env.runtime", help="file env nhận key (mặc định .env.runtime dành cho runtime)")
    kg = sub.add_parser("llm-key-get")
    kg.add_argument("--name", default="bay-nguoc-runtime")
    kg.add_argument("--out", default=".env.runtime")
    d = sub.add_parser("deploy")
    d.add_argument("--name", default="bay-nguoc")
    d.add_argument("--flavor", default="1x1-general")
    d.add_argument("--poc", choices=["true", "false"], required=True, help="true = ví POC (credit cuộc thi), false = ví thật")
    d.add_argument("--tag", default="")
    d.add_argument("--max-replicas", type=int, default=2)
    d.add_argument("--skip-build", action="store_true")
    d.add_argument("--env-file", default=".env.runtime", help="biến môi trường đưa vào runtime (KHÔNG phải .env cục bộ)")
    mm = sub.add_parser("memory")
    mm.add_argument("--name", default="bay-nguoc-rings")
    s = sub.add_parser("status")
    s.add_argument("--name", default="bay-nguoc")
    lg = sub.add_parser("logs")
    lg.add_argument("--name", default="bay-nguoc")
    lg.add_argument("--limit", type=int, default=100)
    a = p.parse_args()
    {"login": cmd_login, "check": cmd_check, "models": cmd_models, "llm-key": cmd_llm_key, "llm-key-get": cmd_llm_key_get, "deploy": cmd_deploy,
     "memory": cmd_memory, "status": cmd_status, "logs": cmd_logs}[a.cmd](a)


if __name__ == "__main__":
    main()
