#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
等授權 → 拉平遠端（bot 每 15 分鐘會自己 commit data.js）→ 推送 → 存入 Windows 認證管理員 → 驗證網址
環境變數: DEVICE_CODE, MARKER
"""
import base64, json, os, subprocess, sys, time, urllib.parse, urllib.request

CID = "178c6fc778ccc68e1d6a"
DEVICE_CODE = os.environ.get("DEVICE_CODE", "")
MARKER = os.environ.get("MARKER", "即時車輛排隊")
BASE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://victoryuen99999-commits.github.io/huanggang-port/"


def log(*a):
    print(*a, flush=True)


def wait_for_token():
    log("[1/4] 等授權…")
    deadline = time.time() + 900
    while time.time() < deadline:
        body = urllib.parse.urlencode({
            "client_id": CID, "device_code": DEVICE_CODE,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).encode()
        r = urllib.request.Request("https://github.com/login/oauth/access_token", data=body,
                                   headers={"Accept": "application/json"})
        with urllib.request.urlopen(r, timeout=25) as resp:
            j = json.loads(resp.read().decode())
        if j.get("access_token"):
            log("[1/4] ✓ 已取得授權")
            return j["access_token"]
        err = j.get("error")
        if err == "authorization_pending":
            time.sleep(5); continue
        if err == "slow_down":
            time.sleep(10); continue
        raise SystemExit("授權失敗: %s" % err)
    raise SystemExit("授權超時")


def git(*args, auth=None):
    cmd = ["git"]
    if auth:
        cmd += ["-c", "credential.helper=",
                "-c", "http.extraheader=Authorization: Basic " + auth]
    cmd += list(args)
    return subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                          encoding="utf-8", errors="ignore")


def main():
    token = wait_for_token()
    auth = base64.b64encode(("x-access-token:" + token).encode()).decode()

    log("[2/4] 拉平遠端（rebase）")
    git("fetch", "origin", "main")
    r = git("-c", "rebase.autoStash=true", "rebase", "-X", "ours", "origin/main")
    log("      " + ((r.stdout or "") + (r.stderr or "")).strip()[-160:])

    log("[3/4] 推送 main")
    r = git("push", "origin", "main", auth=auth)
    log("      " + ((r.stdout or "") + (r.stderr or "")).strip()[-200:])
    if r.returncode != 0:
        raise SystemExit("推送失敗")

    store = subprocess.run(
        ["git", "credential", "approve"], cwd=BASE,
        input="protocol=https\nhost=github.com\nusername=x-access-token\npassword=%s\n\n" % token,
        capture_output=True, text=True)
    log("[3/4] 憑證已存入認證管理員 (GCM)" if store.returncode == 0 else "[3/4] ! 憑證儲存失敗")

    log("[4/4] 等 Pages 建置並驗證內容…")
    for _ in range(24):
        try:
            req = urllib.request.Request(SITE + "?cb=" + str(int(time.time())),
                                         headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", "ignore")
                if MARKER in html and 'class="hero"' not in html:
                    log("      ✓ 已上線（含『%s』、頁首已刪）" % MARKER)
                    print("RESULT_URL=" + SITE, flush=True)
                    return 0
        except Exception as e:                          # noqa: BLE001
            log("      …", str(e)[:60])
        time.sleep(15)
    log("      ! 建置可能延遲，稍後再開")
    print("RESULT_URL=" + SITE, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
