#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
等 GitHub device 授權 -> gh 登入 -> 建 repo -> 推 -> 開 Pages -> 跑 Actions -> 驗證網址
token 只經 stdin 交俾 gh，唔會 print。
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

CID = "178c6fc778ccc68e1d6a"
DEVICE_CODE = "6b059d369e659343ffe56cedf52bc5ccedf88651"
REPO = "huanggang-port"
BASE = os.path.dirname(os.path.abspath(__file__))
GH = os.path.join(os.path.expanduser("~"), "tools", "gh", "bin", "gh.exe")
ENV = dict(os.environ, PATH=os.path.dirname(GH) + os.pathsep + os.environ.get("PATH", ""), GH_PAGER="")

def log(*a):
    print(*a, flush=True)

def gh(*args, stdin=None, check=True):
    r = subprocess.run([GH] + list(args), cwd=BASE, env=ENV, input=stdin,
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if check and r.returncode != 0:
        raise SystemExit("gh %s 失敗: %s %s" % (" ".join(args), out, err))
    return out or err

def wait_for_token():
    log("[1/6] 等你在 https://github.com/login/device 輸入授權碼…")
    deadline = time.time() + 900
    while time.time() < deadline:
        body = urllib.parse.urlencode({
            "client_id": CID, "device_code": DEVICE_CODE,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).encode()
        req = urllib.request.Request("https://github.com/login/oauth/access_token", data=body,
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            j = json.loads(r.read().decode())
        if j.get("access_token"):
            log("[1/6] ✓ 已取得授權")
            return j["access_token"]
        err = j.get("error")
        if err == "authorization_pending":
            time.sleep(5); continue
        if err == "slow_down":
            time.sleep(8); continue
        raise SystemExit("授權失敗: %s %s" % (err, j.get("error_description", "")))
    raise SystemExit("授權超時（15 分鐘）")

def main():
    token = wait_for_token()

    log("[2/6] gh 登入")
    gh("auth", "login", "--hostname", "github.com", "--git-protocol", "https",
       "--with-token", stdin=token + "\n")
    owner = gh("api", "user", "-q", ".login")
    log("      帳戶:", owner)

    log("[3/6] 建立 repo 並推送")
    exists = subprocess.run([GH, "repo", "view", "%s/%s" % (owner, REPO)], cwd=BASE, env=ENV,
                            capture_output=True, text=True).returncode == 0
    if exists:
        remotes = subprocess.run(["git", "remote"], cwd=BASE, capture_output=True, text=True).stdout
        if "origin" not in remotes:
            subprocess.run(["git", "remote", "add", "origin",
                            "https://github.com/%s/%s.git" % (owner, REPO)], cwd=BASE, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=BASE, check=True)
    else:
        subprocess.run([GH, "repo", "create", REPO, "--public", "--source=.", "--remote=origin",
                        "--push", "--description", "皇崗口岸每日資訊站：24 小時通關、實時輪候、交通接駁"],
                       cwd=BASE, env=ENV, check=True)
    log("      https://github.com/%s/%s" % (owner, REPO))

    log("[4/6] 開啟 GitHub Pages（main / root）")
    r = subprocess.run([GH, "api", "-X", "POST", "repos/%s/%s/pages" % (owner, REPO),
                        "-f", "source[branch]=main", "-f", "source[path]=/"],
                       cwd=BASE, env=ENV, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        log("      POST 回應（409 屬正常，代表已開過）:", (r.stderr or r.stdout).strip()[:200])
    log("      " + gh("api", "repos/%s/%s/pages" % (owner, REPO), "-q",
                      '.html_url + "  status=" + (.status // "pending")', check=False)[:200])

    log("[5/6] 觸發一次 Actions 驗證")
    gh("workflow", "run", "refresh.yml", check=False)

    url = "https://%s.github.io/%s/" % (owner, REPO)
    log("[6/6] 等 Pages 上線:", url)
    code = "000"
    for i in range(40):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                code = str(resp.status)
                html = resp.read().decode("utf-8", "ignore")
                if "皇崗口岸" in html:
                    log("      ✓ %s (%d bytes, 已含頁面內容)" % (code, len(html)))
                    log("完成 →", url)
                    print("RESULT_URL=" + url, flush=True)
                    return 0
        except Exception as e:                          # noqa: BLE001
            code = str(e)[:60]
        time.sleep(15)
    log("      ! 仍未就緒（最後狀態 %s），稍後再開通常就會好" % code)
    print("RESULT_URL=" + url, flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
