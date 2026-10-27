#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只做推送：等 device 授權 → git push（token 只在指令參數內，不寫入 .git/config）→ 驗證公開網址
環境變數: DEVICE_CODE, MARKER（可選，驗證頁面是否含此字串）
"""
import base64, json, os, subprocess, sys, time, urllib.parse, urllib.request

CID = "178c6fc778ccc68e1d6a"
DEVICE_CODE = os.environ.get("DEVICE_CODE", "")
MARKER = os.environ.get("MARKER", "即時車輛排隊")
BASE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(*a, flush=True)


def wait_for_token():
    log("[1/3] 等授權…")
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
            log("[1/3] ✓ 已取得授權")
            return j["access_token"]
        err = j.get("error")
        if err == "authorization_pending":
            time.sleep(5); continue
        if err == "slow_down":
            time.sleep(10); continue
        raise SystemExit("授權失敗: %s" % err)
    raise SystemExit("授權超時")


def main():
    token = wait_for_token()
    auth = base64.b64encode(("x-access-token:" + token).encode()).decode()
    log("[2/3] 推送 main")
    r = subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "http.extraheader=Authorization: Basic " + auth,
         "push", "origin", "main"],
        cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    log("      " + ((r.stdout or "") + (r.stderr or "")).strip()[-280:])
    if r.returncode != 0:
        raise SystemExit("推送失敗")

    log("[3/3] 等 Pages 重新建置並驗證內容…")
    url = "https://victoryuen99999-commits.github.io/huanggang-port/"
    for _ in range(24):
        try:
            req = urllib.request.Request(url + "?cb=" + str(int(time.time())),
                                         headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", "ignore")
                if MARKER in html:
                    log("      ✓ 已更新，含『%s』" % MARKER)
                    print("RESULT_URL=" + url, flush=True)
                    return 0
        except Exception as e:                          # noqa: BLE001
            log("      …", str(e)[:60])
        time.sleep(15)
    log("      ! 仍未見新內容（Pages 建置可能延遲）")
    print("RESULT_URL=" + url, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
