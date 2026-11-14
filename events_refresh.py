#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近期大型活動（港方 / 深方）—— 供口岸人流預測參考

來源：
  港方  1) HK01 SPACE「hkevents」主題頁（Next.js __NEXT_DATA__，結構化）
        2) 香港公眾假期 1823 iCal JSON（官方）
        3) events_curated.json 人手核對補充（馬拉松等）
  深方  1) 深圳本地寶「深圳演唱會」時間表（HTML）
        2) events_curated.json 人手核對補充（深圳馬拉松等）

輸出 events.js → window.HGP_EVENTS = {updated, checked, hk:[...], sz:[...]}
每筆：{name, start, end, time, venue, type, impact, note, src_kind, confirm}
失敗的來源不影響其他來源；全失敗則不覆寫舊檔。
"""
import json, os, re, sys, html, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "events.js")
CURATED = os.path.join(BASE, "events_curated.json")
HKT = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
HK01 = "https://space.hk01.com/themes/hkevents"
BDB = "http://sz.bendibao.com/xiuxian/yanchanghui/"
HOL = "https://www.1823.gov.hk/common/ical/tc.json"
WINDOW_DAYS = 75          # 只看未來 75 日
MAX_PER_SIDE = 6


def get(url, timeout=25, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            for enc in ("utf-8", "gb18030", "big5"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as e:      # noqa: BLE001
            last = e
    raise last


# ────────────────────────── 分類與影響提示 ──────────────────────────
def classify(name):
    n = name
    if re.search(r"馬拉松|马拉松|單車|单车|三項|三项|賽事|赛事|盃|杯|錦標賽|锦标赛|球賽|球赛|足球|籃球|篮球|網球|网球", n):
        return "sport", "high", "賽事日清晨至中午交通管制；前後時段跨境人流上升"
    if re.search(r"演唱會|演唱会|音樂會|音乐会|巡迴|巡回|concert|live", n, re.I):
        return "show", "high", "散場約 22:00–00:30，深夜出境（返港）高峰"
    if re.search(r"展覽|展览|博覽|博览|會展|会展|會議|会议|論壇|论坛|峰會|峰会|展銷|展销|design|expo", n, re.I):
        return "expo", "mid", "日間入境人流增加，展期首日及週末較明顯"
    return "other", "mid", "大型活動，散場或開場前後人流上升"


try:                                    # 有 opencc 就整段轉繁體，較完整
    from opencc import OpenCC
    _CC = OpenCC("s2t")
except Exception:                       # noqa: BLE001
    _CC = None

S2T = [("体育","體育"),("大运","大運"),("场","場"),("馆","館"),("巡回","巡迴"),("演唱会","演唱會"),
       ("音乐","音樂"),("深圳湾","深圳灣"),("春茧","春繭"),("龙岗","龍崗"),("宝安","寶安"),("罗湖","羅湖"),
       ("福田","福田"),("会展","會展"),("中心","中心"),("体育馆","體育館"),("体育场","體育場")]


def to_trad(txt):
    if _CC is not None:
        try:
            return _CC.convert(txt)
        except Exception:               # noqa: BLE001
            pass
    for a, b in S2T:
        txt = txt.replace(a, b)
    return txt


def clean_name(raw, maxlen=42):
    name = re.split(r"[｜|]", raw)[0].strip()
    name = re.sub(r"\s+", " ", name)
    if len(name) > maxlen:
        name = name[:maxlen] + "…"
    return name


def parse_range(txt):
    """'2026.11.16-2026.11.17' / '2026.12.26' / '2026.12.31-2027.01.01' → (start, end)"""
    txt = txt.replace(" ", "").replace("（", "(").replace("）", ")")
    parts = re.findall(r"(20\d\d)[.\-/年](\d{1,2})[.\-/月](\d{1,2})", txt)
    if not parts:
        return None, None
    def mk(p):
        return "%04d-%02d-%02d" % (int(p[0]), int(p[1]), int(p[2]))
    return mk(parts[0]), mk(parts[-1])


# ────────────────────────── 港方：HK01 SPACE ──────────────────────────
def fetch_hk01():
    s = get(HK01)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', s, re.S)
    if not m:
        raise RuntimeError("no __NEXT_DATA__")
    d = json.loads(m.group(1))
    ent = d["props"]["initialState"]["event"]["eventEntity"]
    out = []
    for e in ent.values():
        try:
            st = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00")).astimezone(HKT)
            en = datetime.fromisoformat(e["endDate"].replace("Z", "+00:00")).astimezone(HKT)
        except Exception:           # noqa: BLE001
            continue
        name = clean_name(e.get("name", ""))
        typ, imp, note = classify(name)
        out.append({
            "name": name,
            "start": st.strftime("%Y-%m-%d"), "end": en.strftime("%Y-%m-%d"),
            "time": "", "venue": e.get("address", ""),
            "type": typ, "impact": imp, "note": note,
            "src_kind": "hk01", "confirm": "",
            "link": "https://space.hk01.com" + e.get("link", ""),
        })
    return out


# ────────────────────────── 港方：公眾假期 ──────────────────────────
def fetch_holidays():
    s = get(HOL).lstrip("\ufeff")
    d = json.loads(s)
    out = []
    for cal in d.get("vcalendar", []):
        for ev in cal.get("vevent", []):
            ds = ev.get("dtstart", "")
            if isinstance(ds, (list, tuple)):
                ds = ds[0] if ds else ""
            m = re.match(r"(\d{4})(\d{2})(\d{2})", str(ds))
            if not m:
                continue
            day = "%s-%s-%s" % m.groups()
            out.append({
                "name": ev.get("summary", "公眾假期"),
                "start": day, "end": day, "time": "全日",
                "venue": "香港", "type": "holiday", "impact": "high",
                "note": "公眾假期：假期首日及最後一日為跨境高峰",
                "src_kind": "1823", "confirm": "",
                "link": "https://www.1823.gov.hk/tc/faq/what-are-the-general-holidays",
            })
    return out


# ────────────────────────── 深方：深圳本地寶 ──────────────────────────
def fetch_bdb():
    s = get(BDB)
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", s)).split("\n") if l.strip()]
    skip = {"查看攻略", "推荐指数", "推薦指數", "即将开始", "即將開始", "推荐", "推薦", "演唱会小助手"}
    out, seen = [], set()
    for i, line in enumerate(lines):
        if line not in ("活动时间", "活動時間"):
            continue
        if i + 1 >= len(lines):
            continue
        st, en = parse_range(lines[i + 1])
        if not st:
            continue
        # 名稱：往前找第一個不是標籤的行
        name = ""
        for k in range(i - 1, max(0, i - 7), -1):
            if lines[k] in skip:
                continue
            name = lines[k]
            break
        venue = ""
        for k in range(i + 1, min(i + 7, len(lines) - 1)):
            if lines[k] in ("活动地址", "活動地址"):
                venue = lines[k + 1]
                break
        name = to_trad(clean_name(name))
        venue = to_trad(re.sub(r"\s+", " ", venue).strip())
        if not name or name in seen:
            continue
        seen.add(name)
        typ, imp, note = classify(name)
        confirm = ""
        m = re.match(r"(20\d\d)", name)          # 標題年份與日期年份不同 → 待確認
        if m and not st.startswith(m.group(1)):
            confirm = "待確認"
        out.append({
            "name": name, "start": st, "end": en or st, "time": "",
            "venue": re.sub(r"\s+", " ", venue).strip(),
            "type": typ, "impact": imp, "note": note,
            "src_kind": "bendibao", "confirm": confirm,
            "link": BDB,
        })
    return out


# ────────────────────────── 合併與過濾 ──────────────────────────
def norm_curated(block, kind):
    out = []
    for e in block or []:
        typ, imp, note = classify(e.get("name", ""))
        out.append({
            "name": e.get("name", ""), "start": e.get("start", ""), "end": e.get("end", e.get("start", "")),
            "time": e.get("time", ""), "venue": e.get("venue", ""),
            "type": e.get("type") or typ, "impact": e.get("impact") or imp,
            "note": e.get("note") or note,
            "src_kind": "curated", "confirm": e.get("confirm", ""),
            "link": e.get("source", ""),
        })
    return out


def finalize(items, today, limit):
    keep, seen = [], set()
    for e in items:
        try:
            st = datetime.strptime(e["start"], "%Y-%m-%d").date()
            en = datetime.strptime(e["end"] or e["start"], "%Y-%m-%d").date()
        except Exception:           # noqa: BLE001
            continue
        if en < today:                       # 已結束
            continue
        if st > today + timedelta(days=WINDOW_DAYS):
            continue
        key = (e["name"][:18], e["start"])
        if key in seen:
            continue
        seen.add(key)
        e["days"] = (st - today).days
        keep.append(e)
    order = {"high": 0, "mid": 1}
    keep.sort(key=lambda e: (e["start"], order.get(e["impact"], 2)))
    return keep[:limit]


def main():
    now = datetime.now(HKT)
    today = now.date()
    got = {"hk": [], "sz": []}
    errs = []

    try:
        got["hk"] += fetch_hk01()
    except Exception as e:              # noqa: BLE001
        errs.append("hk01: %s" % str(e)[:80])
    try:
        got["hk"] += fetch_holidays()
    except Exception as e:              # noqa: BLE001
        errs.append("1823: %s" % str(e)[:80])
    try:
        got["sz"] += fetch_bdb()
    except Exception as e:              # noqa: BLE001
        errs.append("bendibao: %s" % str(e)[:80])

    checked = ""
    try:
        cur = json.load(open(CURATED, encoding="utf-8"))
        got["hk"] += norm_curated(cur.get("hk"), "hk")
        got["sz"] += norm_curated(cur.get("sz"), "sz")
        checked = cur.get("checked", "")
    except Exception as e:              # noqa: BLE001
        errs.append("curated: %s" % str(e)[:80])

    hk = finalize(got["hk"], today, MAX_PER_SIDE * 2)     # 假期多，港方容許多幾筆
    sz = finalize(got["sz"], today, MAX_PER_SIDE)

    if not hk and not sz:
        print("[warn] 全部來源失敗，保留舊檔:", "; ".join(errs), file=sys.stderr)
        return 1

    data = {"updated": now.isoformat(timespec="seconds"),
            "clock": now.strftime("%H:%M"),
            "checked": checked, "hk": hk, "sz": sz}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("/* 自動生成：近期大型活動 — 請勿手改（人手補充在 events_curated.json） */\n")
        f.write("window.HGP_EVENTS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("[ok] %s 港方 %d 筆、深方 %d 筆%s" % (
        now.strftime("%H:%M"), len(hk), len(sz),
        ("｜警告: " + "; ".join(errs)) if errs else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
