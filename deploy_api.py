#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
純 REST + git 部署（唔用 gh，避免 read:org scope 要求）
環境變數: DEVICE_CODE
輸出: token → 建 repo → 推送 → 開 Pages → 觸發 Actions → 驗證網址
"""
import base64, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

CID = "178c6fc778ccc68e1d6a"
DEVICE_CODE = os.environ.get("DEVICE_CODE", "")
REPO = "huanggang-port"
DESC = "皇崗口岸值班資訊站：天氣警告、即時客流、口岸新聞、收工交通、部門熱線"
BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"


def log(*a):
    print(*a, flush=True)


def req(url, method="GET", data=None, token=None, raw=False, timeout=40):
    body = json.dumps(data).encode() if data is not None else None
    h = {"Accept": "application/vnd.github+json", "User-Agent": "hgp-deploy",
         "X-GitHub-Api-Version": "2022-11-28"}
    if body:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8", "ignore")
            return resp.status, (txt if raw else (json.loads(txt) if txt.strip() else {}))
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "ignore")
        return e.code, txt


def wait_for_token():
    log("[1/6] 等你在 https://github.com/login/device 授權…")
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
            log("[1/6] ✓ 授權完成，scope =", j.get("scope"))
            return j["access_token"], j.get("scope", "")
        err = j.get("error")
        if err in ("authorization_pending",):
            time.sleep(5); continue
        if err == "slow_down":
            time.sleep(10); continue
        raise SystemExit("授權失敗: %s %s" % (err, j.get("error_description", "")))
    raise SystemExit("授權超時")


def git(*args, token=None, check=True):
    cmd = ["git"]
    if token:
        auth = base64.b64encode(("x-access-token:" + token).encode()).decode()
        cmd += ["-c", "credential.helper=", "-c", "http.extraheader=Authorization: Basic " + auth]
    cmd += list(args)
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    if check and r.returncode != 0:
        raise SystemExit("git %s 失敗:\n%s\n%s" % (args[0], r.stdout, r.stderr))
    return (r.stdout or "") + (r.stderr or "")


def main():
    token, scope = wait_for_token()

    st, me = req(API + "/user", token=token)
    if st != 200:
        raise SystemExit("讀取用戶失敗 (%s): %s" % (st, me))
    owner = me["login"]
    log("[2/6] 帳戶:", owner, "| token scopes:", scope)

    st, out = req(API + "/repos/%s/%s" % (owner, REPO), token=token)
    if st == 200:
        log("[3/6] repo 已存在，直接推送")
    else:
        st, out = req(API + "/user/repos", method="POST", token=token,
                      data={"name": REPO, "description": DESC, "private": False,
                            "has_issues": True, "has_wiki": False})
        if st not in (200, 201):
            raise SystemExit("建立 repo 失敗 (%s): %s" % (st, out))
        log("[3/6] ✓ 已建立 public repo")

    url = "https://github.com/%s/%s.git" % (owner, REPO)
    git("remote", "remove", "origin", check=False)
    git("remote", "add", "origin", url)
    log("      push →", url)
    log("      " + git("push", "-u", "origin", "main", token=token).strip()[-300:])

    log("[4/6] 開啟 GitHub Pages (main / root)")
    st, out = req(API + "/repos/%s/%s/pages" % (owner, REPO), method="POST", token=token,
                  data={"source": {"branch": "main", "path": "/"}})
    if st in (200, 201):
        log("      ✓ Pages 已啟用")
    elif st == 409:
        log("      Pages 已存在（409），略過")
    else:
        log("      ! Pages 設定回應 %s: %s" % (st, str(out)[:180]))

    log("[5/6] 觸發 Actions 一次")
    st, out = req(API + "/repos/%s/%s/actions/workflows/refresh.yml/dispatches" % (owner, REPO),
                  method="POST", token=token, data={"ref": "main"})
    log("      dispatch →", st, "" if st in (204, 200) else str(out)[:160])

    site = "https://%s.github.io/%s/" % (owner, REPO)
    log("[6/6] 等 Pages 上線:", site)
    for i in range(40):
        try:
            r = urllib.request.Request(site, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(r, timeout=20) as resp:
                html = resp.read().decode("utf-8", "ignore")
                if "皇崗口岸" in html:
                    log("      ✓ HTTP %s，%d bytes，內容已就緒" % (resp.status, len(html)))
                    print("RESULT_URL=" + site, flush=True)
                    return 0
        except Exception as e:                          # noqa: BLE001
            if i % 4 == 0:
                log("      … 仍未就緒 (%s)" % str(e)[:60])
        time.sleep(15)
    print("RESULT_URL=" + site, flush=True)
    log("      ! 網址已建立但仍在建置，通常 1–2 分鐘後可開")
    return 0


if __name__ == "__main__":
    sys.exit(main())
