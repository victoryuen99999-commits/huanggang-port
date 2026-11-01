#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 data.gov.hk 官方歷史檔案補回皇崗口岸過去記錄（真實數據，非模擬）

API:
  list-file-versions?url=<enc>&start=YYYYMMDD&end=YYYYMMDD   → timestamps[]
  get-file?url=<enc>&time=<YYYYMMDD-HHMM>                    → 該版本的 JSON（302 後為檔案）

規則:
  - 只取官方有存檔的時間點（狀態有變更才會有新版本）
  - 兩個版本之間狀態視為不變，最多向前填 3 小時
  - 與現有 history.js 合併、去重、按時間排序，保留最近 HIST_MAX 筆
用法: python backfill_history.py [天數]   預設 4
"""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(BASE, "history.js")
HIST_MAX = 288
HKT = timezone(timedelta(hours=8))
SRC = "https://secure1.info.gov.hk/immd/mobileapps/2bb9ae17/data/CPQueueTime%s.json"
API = "https://app.data.gov.hk/v1/historical-archive/"


def get(url, tries=3, timeout=30):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hgp-backfill/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:      # noqa: BLE001
            last = e
    raise RuntimeError(str(last) if last else "unknown error")


def versions(kind, days):
    end = datetime.now(HKT) - timedelta(days=1)      # 官方只存到昨日
    start = end - timedelta(days=days)
    u = API + "list-file-versions?" + urllib.parse.urlencode({
        "url": SRC % kind, "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d")})
    return json.loads(get(u)).get("timestamps", [])


def hgp(kind, stamp):
    u = API + "get-file?" + urllib.parse.urlencode({"url": SRC % kind, "time": stamp})
    d = json.loads(get(u)).get("HGP") or {}
    return int(d.get("arrQueue", -1)), int(d.get("depQueue", -1))


def load_existing():
    try:
        m = re.search(r"window\.HGP_HIST\s*=\s*(\[.*\]);", open(HIST, encoding="utf-8").read(), re.S)
        return json.loads(m.group(1)) if m else []
    except Exception:               # noqa: BLE001
        return []


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    ts = sorted(set(versions("R", days)) | set(versions("V", days)))
    print("官方存檔時間點:", len(ts), ts[:3], "…", ts[-3:])

    stamps, rmap, vmap = [], {}, {}
    for s in ts:
        try:
            rmap[s] = hgp("R", s)
        except Exception as e:      # noqa: BLE001
            print("  R 失敗", s, str(e)[:50])
        try:
            vmap[s] = hgp("V", s)
        except Exception as e:      # noqa: BLE001
            print("  V 失敗", s, str(e)[:50])

    def to_ms(s):
        return datetime.strptime(s, "%Y%m%d-%H%M").replace(tzinfo=HKT).timestamp() * 1000

    pts = {}
    for s in sorted(set(rmap) | set(vmap)):
        a, d = rmap.get(s, (-1, -1))
        va, vd = vmap.get(s, (-1, -1))
        if a < 0 and va < 0:
            continue
        pts[int(to_ms(s))] = {"t": int(to_ms(s)), "a": a, "d": d, "va": va, "vd": vd, "bf": 1}

    # 兩版本之間最多向前填 3 小時（每 30 分鐘一格）
    keys = sorted(pts)
    filled = dict(pts)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i], keys[i + 1]
        if 0 < (t1 - t0) <= 3 * 3600 * 1000:
            step = 30 * 60 * 1000
            t = t0 + step
            while t < t1:
                pc = dict(pts[t0]); pc["t"] = t
                filled[t] = pc
                t += step
    print("補回時間點:", len(pts), "→ 前值填充後:", len(filled))

    hist = {p["t"]: p for p in load_existing() if p.get("t")}
    before = len(hist)
    for t, p in filled.items():
        hist.setdefault(t, p)
    out = [hist[t] for t in sorted(hist)][-HIST_MAX:]

    with open(HIST, "w", encoding="utf-8") as f:
        f.write("/* 自動生成：過去記錄（含官方歷史檔案補回）— 請勿手改 */\n")
        f.write("window.HGP_HIST = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")

    print("history.js：原有 %d → 現有 %d 筆" % (before, len(out)))
    print("最早:", datetime.fromtimestamp(out[0]["t"] / 1000, HKT).strftime("%m-%d %H:%M"),
          "｜最新:", datetime.fromtimestamp(out[-1]["t"] / 1000, HKT).strftime("%m-%d %H:%M"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
