"""Tạo repo GitHub public và push source (bài nộp). Token đọc từ file credentials CỤC BỘ, KHÔNG in ra,
KHÔNG ghi vào .git/config (truyền qua biến môi trường GIT_CONFIG_* chỉ trong tiến trình git push).

Dùng: python deploy/github_publish.py ../Credentials.txt counter-snare
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = ("COUNTER-SNARE – Autonomous Mule Ring Hunter & STR Intelligence Platform on GreenNode AgentBase "
               "(Smart Banking 2026 AI Hackathon, Track C)")


def load_token(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,})", text)
    if not m:
        sys.exit("Không tìm thấy GitHub token trong file credentials")
    return m.group(1)


def gh(method: str, url: str, token: str, body: dict | None = None):
    req = urllib.request.Request("https://api.github.com" + url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "counter-snare-publisher"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def git(*args, env=None, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, env=env)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args[:2])} lỗi: {r.stderr.strip()[:400]}")
    return r.stdout.strip()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cred = Path(args[0] if args else ROOT.parent / "Credentials.txt")
    repo = args[1] if len(args) > 1 else "counter-snare"
    token = load_token(cred)

    code, me = gh("GET", "/user", token)
    if code != 200:
        sys.exit(f"Token không hợp lệ (HTTP {code})")
    login, uid = me["login"], me["id"]
    print(f"✔ GitHub user: {login}")
    # danh tính commit cục bộ của repo = email noreply của GitHub (không lộ email cá nhân trên repo public)
    git("config", "user.name", login)
    git("config", "user.email", f"{uid}+{login}@users.noreply.github.com")
    if "--identity-only" in sys.argv:
        print("✔ Đã đặt danh tính commit cục bộ (noreply)")
        return

    code, info = gh("GET", f"/repos/{login}/{repo}", token)
    if code == 404:
        code, info = gh("POST", "/user/repos", token, {"name": repo, "description": DESCRIPTION, "private": False,
                                                       "has_issues": True, "has_wiki": False, "auto_init": False})
        if code not in (200, 201):
            sys.exit(f"Tạo repo thất bại (HTTP {code}): {info.get('message')}")
        print(f"✔ Đã tạo repo public: {info['html_url']}")
    elif code == 200:
        print(f"✔ Repo đã tồn tại: {info['html_url']}")
    else:
        sys.exit(f"Lỗi kiểm tra repo (HTTP {code})")

    git("branch", "-M", "main")
    remote = f"https://github.com/{login}/{repo}.git"
    if "origin" in git("remote", check=False).split():
        git("remote", "set-url", "origin", remote)
    else:
        git("remote", "add", "origin", remote)

    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
               GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}", GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=ROOT, text=True, capture_output=True, env=env)
    out = (r.stdout + r.stderr).replace(token, "***").replace(basic, "***")
    if r.returncode != 0:
        sys.exit("git push lỗi: " + out.strip()[:600])
    print("✔ Đã push nhánh main →", remote.replace(".git", ""))


if __name__ == "__main__":
    main()
