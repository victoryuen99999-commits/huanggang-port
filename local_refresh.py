#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本機補時：GitHub Actions 被 throttle 時，由本機補上更新（只在遠端快照過舊時才動手）

用法:
  python local_refresh.py            # 檢查一次，太舊就更新＋推送
  python local_refresh.py --force    # 不理年齡，強制更新＋推送
  python local_refresh.py --watch    # 常駐，每 5 分鐘檢查一次（Ctrl+C 停止）

設計:
  - 讀遠端 data.js 的 generated_at，若 < STALE_MIN 分鐘就乜都唔做（避免同 Actions 撞）
  - 否則跑 refresh.py → commit → rebase → push（用 Windows 認證管理員已存的憑證）
"""
import json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = "https://raw.githubusercontent.com/victoryuen99999-commits/huanggang-port/main/data.js"
STALE_MIN = 12          # 遠端快照超過幾多分鐘才補
CHECK_SEC = 300
HKT = timezone(timedelta(hours=8))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def remote_age():
    """回傳遠端 data.js 的年齡（分鐘）；讀不到回傳 None"""
    try:
        req = urllib.request.Request(RAW + "?t=" + str(int(time.time())),
                                     headers={"User-Agent": "hgp-local/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8", "ignore")
        m = re.search(r'"generated_at":\s*"([^"]+)"', txt)
        if not m:
            return None
        ts = datetime.fromisoformat(m.group(1))
        return (datetime.now(HKT) - ts).total_seconds() / 60.0
    except Exception as e:      # noqa: BLE001
        log("讀遠端失敗:", str(e)[:70])
        return None


def sh(*args, check=True):
    r = subprocess.run(args, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore",
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if check and r.returncode != 0:
        raise SystemExit("%s 失敗: %s" % (" ".join(args[:2]), out[-300:]))
    return out


def run_once(force=False):
    age = remote_age()
    if age is None:
        log("遠端讀不到，跳過（避免衝突）")
        return
    log("遠端快照：%.0f 分鐘前" % age)
    if not force and age < STALE_MIN:
        log("仍然新鮮（< %d 分鐘），唔需要補" % STALE_MIN)
        return

    log("開始更新…")
    r = subprocess.run([sys.executable, os.path.join(BASE, "refresh.py")],
                       cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    log(r.stdout.strip() or r.stderr.strip()[-200:])

    sh("git", "add", "data.js", "data.json")
    st = sh("git", "status", "--porcelain", "data.js", "data.json")
    if st:
        stamp = datetime.now(HKT).strftime("%Y-%m-%d %H:%M HKT")
        sh("git", "commit", "-m", "data: 本機補時 %s" % stamp)
        sh("git", "fetch", "origin", "main", check=False)
        subprocess.run(["git", "-c", "rebase.autoStash=true", "rebase", "-X", "ours", "origin/main"],
                       cwd=BASE, capture_output=True, text=True)
        out = sh("git", "push", "origin", "main", check=False)
        log("推送：", out[-160:])
    else:
        log("資料無變化")


def main():
    force = "--force" in sys.argv
    if "--watch" in sys.argv:
        log("常駐模式：每 %d 秒檢查一次（Ctrl+C 停止）" % CHECK_SEC)
        while True:
            try:
                run_once(force=False)
            except Exception as e:      # noqa: BLE001
                log("錯誤:", str(e)[:120])
            time.sleep(CHECK_SEC)
    else:
        run_once(force=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
