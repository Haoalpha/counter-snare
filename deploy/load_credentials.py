"""Nạp thông tin xác thực từ file credentials CỤC BỘ do đội cung cấp -> .greennode.json (IAM) và .env (MaaS).

- KHÔNG in bất kỳ giá trị bí mật nào; chỉ báo trường nào đã nạp.
- KHÔNG đọc/không dùng mật khẩu Root (chỉ dùng IAM service account + API key).
- File đích nằm trong .gitignore và .dockerignore: không lên GitHub, không nằm trong Docker image.

Dùng: python deploy/load_credentials.py ../Credentials.txt
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LABELS = {
    "client_id": r"IAM\s*Client\s*ID",
    "client_secret": r"IAM\s*Client\s*Secret",
    "base_url": r"Base\s*URL",
    "api_key": r"API\s*Key",
}


def parse(path: Path) -> dict:
    found = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for key, pat in LABELS.items():
            m = re.search(rf"{pat}\s*[:=]\s*(\S+)\s*$", line, flags=re.I)
            if m and key not in found:
                found[key] = m.group(1).strip()
    return found


def set_env(env_path: Path, values: dict) -> None:
    base = env_path if env_path.exists() else ROOT / ".env.example"
    lines = base.read_text(encoding="utf-8").splitlines()
    done = set()
    out = []
    for ln in lines:
        k = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if k in values:
            out.append(f"{k}={values[k]}")
            done.add(k)
        else:
            out.append(ln)
    out += [f"{k}={v}" for k, v in values.items() if k not in done]
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "Credentials.txt")
    f = parse(src)
    if f.get("client_id") and f.get("client_secret"):
        (ROOT / ".greennode.json").write_text(json.dumps({"client_id": f["client_id"], "client_secret": f["client_secret"]}), encoding="utf-8")
        print("✔ IAM Client ID/Secret -> .greennode.json")
    else:
        print("✘ Không tìm thấy IAM Client ID/Secret")
    env = {}
    if f.get("base_url"):
        env["LLM_BASE_URL"] = f["base_url"].rstrip("/")
    if f.get("api_key"):
        env["LLM_API_KEY"] = f["api_key"]
    if env:
        set_env(ROOT / ".env", env)
        print("✔ " + ", ".join(env) + " -> .env")
    print(f"Trường đã nạp: {sorted(f)} (giá trị không được in ra)")


if __name__ == "__main__":
    main()
