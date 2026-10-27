#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皇崗口岸值班資訊站 — 資料抓取
用法: python refresh.py
輸出: data.js (window.HGP_DATA) / data.json
來源: 入境處開放數據、香港天文台（警告 RSS + 天氣）、政府新聞公報 RSS
"""
import json, os, re, sys, urllib.parse, urllib.request, html as htmllib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.abspath(__file__))
HKT = timezone(timedelta(hours=8))

IMMD_R = "https://secure1.info.gov.hk/immd/mobileapps/2bb9ae17/data/CPQueueTimeR.json"
IMMD_V = "https://secure1.info.gov.hk/immd/mobileapps/2bb9ae17/data/CPQueueTimeV.json"
WEATHER = ("https://api.open-meteo.com/v1/forecast?latitude=22.5317&longitude=114.0694"
           "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=Asia%2FHong_Kong&forecast_days=2")
WARN_RSS = "https://rss.weather.gov.hk/rss/WeatherWarningSummaryv2_uc.xml"
NEWS_QUERIES = ("皇崗口岸", "皇崗 通關 高峰")

STATUS = {0: "正常", 1: "繁忙", 2: "非常繁忙", 4: "系統維護", 99: "非服務時間"}
WMO = {0:"天晴",1:"大致晴朗",2:"局部多雲",3:"多雲",45:"有霧",48:"霧凇",51:"毛毛雨",53:"毛毛雨",55:"毛毛雨",
       56:"凍雨",57:"凍雨",61:"小雨",63:"中雨",65:"大雨",66:"凍雨",67:"凍雨",71:"小雪",73:"中雪",75:"大雪",
       77:"雪粒",80:"驟雨",81:"驟雨",82:"強驟雨",85:"陣雪",86:"陣雪",95:"雷暴",96:"雷暴有冰雹",99:"雷暴有冰雹"}
NEWS_KEYS = ("皇崗", "口岸", "通關", "跨境", "邊境管制", "蓮塘", "深圳灣", "落馬洲")


def get_bytes(url, tries=3, timeout=20):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HGP-Duty/1.0",
                "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:      # noqa: BLE001
            last = e
    raise last


def get_json(url):
    return json.loads(get_bytes(url).decode("utf-8"))


def get_text(url):
    return get_bytes(url).decode("utf-8", "ignore")


def rss_field(block, tag):
    m = re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (tag, tag), block, re.S)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def fetch_warnings():
    """天文台天氣警告一覽。無警告時 RSS 只有一條「現時並無警告生效」"""
    try:
        x = get_text(WARN_RSS)
    except Exception as e:      # noqa: BLE001
        print("[warn] 天文台警告抓取失敗:", e, file=sys.stderr)
        return None
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        title = rss_field(it, "title")
        desc = rss_field(it, "description")
        if "並無警告" in title or "no warning" in title.lower():
            continue
        name = re.sub(r"\s*[（(].*?[)）]\s*$", "", title).strip()
        out.append({"title": name, "desc": desc[:300], "updated": rss_field(it, "pubDate")})
    return out


def fetch_news(limit=8, days=7):
    """口岸相關新聞（Google News RSS，標題版權屬原媒體）"""
    now = datetime.now(HKT)
    seen, rows = set(), []
    for q in NEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
               "&hl=zh-HK&gl=HK&ceid=HK:zh-Hant")
        try:
            x = get_text(url)
        except Exception as e:      # noqa: BLE001
            print("[warn] 新聞抓取失敗 (%s): %s" % (q, e), file=sys.stderr)
            continue
        for it in re.findall(r"<item>(.*?)</item>", x, re.S):
            title = rss_field(it, "title")
            src = re.search(r"<source[^>]*>(.*?)</source>", it, re.S)
            src = htmllib.unescape(src.group(1)).strip() if src else ""
            if not title:
                continue
            clean = re.sub(r"\s*#[^\s#]+", "", title)
            clean = re.sub(r"\s+[-\|]\s+[^-\|]{1,14}$", "", clean).strip()
            key = re.sub(r"[\s\u3000]+", "", clean)[:40]
            if key in seen:
                continue
            pub = rss_field(it, "pubDate")
            try:
                dt = parsedate_to_datetime(pub)
            except Exception:       # noqa: BLE001
                dt = None
            if dt and (now - dt) > timedelta(days=days):
                continue
            seen.add(key)
            rows.append({"title": clean,
                         "source": src,
                         "date": dt.strftime("%m-%d %H:%M") if dt else "",
                         "iso": dt.isoformat() if dt else "",
                         "link": rss_field(it, "link")})
    rows.sort(key=lambda r: r["iso"], reverse=True)
    return rows[:limit]


def queue_block(q):
    if not isinstance(q, dict):
        return None
    return {"arr": int(q.get("arrQueue", -1)), "dep": int(q.get("depQueue", -1))}


def build_tips(now, weather, warnings, news):
    """值班提示（規則式，非官方預測）"""
    tips = []
    hour, wd = now.hour, now.weekday()

    if warnings:
        joined = "、".join(w["title"] for w in warnings)
        tips.append(("警告", "天文台現正生效：" + joined + "。戶外崗位（上落客區、落馬洲大橋、交匯處）注意強風、雷擊及地滑。", "warn"))
    elif warnings is not None:
        tips.append(("天氣", "天文台現時無天氣警告生效。", "ok"))

    if 23 <= hour or hour < 6:
        tips.append(("夜更", "地鐵 7 號線已收車；港方只餘 NB73（沙田）、79S（天水圍）、N44B（屯門）、616S（旺角）及市區／新界的士，交更請預留候車時間。", "warn"))
    elif 7 <= hour < 9:
        tips.append(("早更", "跨境上班上學人流集中，出境大堂及 L2 交匯處會出現短時人龍。", "info"))
    elif hour in (17, 18, 19):
        tips.append(("傍晚", "雙向高峰：出境（北上）與入境（返港）同時加壓，L2 候車區最擠。", "info"))

    if wd == 4:
        tips.append(("週五", "每週最擠時段之一（晚上北上），通宵巴士及跨境巴士都會排隊。", "warn"))
    elif wd == 5:
        tips.append(("週六", "早上北上、晚上返港雙高峰；落客區與上客區容易同時塞。", "info"))
    elif wd == 6:
        tips.append(("週日", "傍晚 5 時至 10 時返港高峰，入境大堂壓力最大。", "warn"))

    if weather:
        pop, code, tmax = weather.get("pop"), weather.get("code"), weather.get("tmax")
        if pop is not None and pop >= 60:
            tips.append(("有雨", "預測降雨機率 {}%，室外通道及上落客區會濕滑，提醒旅客及同事小心。".format(pop), "warn"))
        if code in (95, 96, 99):
            tips.append(("雷暴", "雷暴可能影響露天崗位及戶外上落客區，按程序避雷。", "warn"))
        if tmax is not None and tmax >= 33:
            tips.append(("酷熱", "最高約 {}°C，露天崗位注意補水及輪換。".format(tmax), "info"))

    if news:
        tips.append(("通告", "口岸相關新聞 {} 條，見「口岸新聞」。".format(len(news)), "info"))
        hot = [n for n in news if any(k in n["title"] for k in ("塞", "擠", "車龍", "人流", "高峰"))
               and n.get("iso") and (now - datetime.fromisoformat(n["iso"])) < timedelta(hours=36)]
        if len(hot) >= 2:
            tips.append(("車流", "近 36 小時有 {} 篇報道提及口岸擠塞／高峰：上落客區與 L2 交匯處屬樽頸位，建議按現場情況提早分流。".format(len(hot)), "warn"))

    tips.append(("禁區", "港方口岸區屬禁區：過境旅客須持有效旅行證件，非過境人士（包括部分承辦商）須持有效禁區通行證。", "info"))
    return [{"tag": t, "text": x, "level": lv} for t, x, lv in tips]


def main():
    now = datetime.now(HKT)
    out = {"generated_at": now.isoformat(timespec="seconds"),
           "date": now.strftime("%Y-%m-%d"),
           "weekday": "星期" + "一二三四五六日"[now.weekday()],
           "clock": now.strftime("%H:%M"),
           "queue": None, "queue_visitor": None, "others": {},
           "weather": None, "warnings": None, "news": [], "ok": False}

    try:
        r, v = get_json(IMMD_R), get_json(IMMD_V)
        out["queue"] = queue_block(r.get("HGP"))
        out["queue_visitor"] = queue_block(v.get("HGP"))
        out["others"] = {k: queue_block(x) for k, x in r.items() if k != "HGP"}
        out["ok"] = out["queue"] is not None
    except Exception as e:      # noqa: BLE001
        print("[warn] 入境處資料抓取失敗:", e, file=sys.stderr)

    try:
        w = get_json(WEATHER)
        cur, day = w.get("current", {}), w.get("daily", {})
        out["weather"] = {
            "temp": round(cur.get("temperature_2m", 0)),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "code": cur.get("weather_code"),
            "desc": WMO.get(cur.get("weather_code"), "—"),
            "tmax": round(day.get("temperature_2m_max", [0])[0]),
            "tmin": round(day.get("temperature_2m_min", [0])[0]),
            "pop": day.get("precipitation_probability_max", [None])[0],
        }
    except Exception as e:      # noqa: BLE001
        print("[warn] 天氣抓取失敗:", e, file=sys.stderr)

    out["warnings"] = fetch_warnings()
    out["news"] = fetch_news()
    out["tips"] = build_tips(now, out["weather"], out["warnings"], out["news"])

    payload = json.dumps(out, ensure_ascii=False, indent=1)
    with open(os.path.join(BASE, "data.json"), "w", encoding="utf-8") as f:
        f.write(payload)
    with open(os.path.join(BASE, "data.js"), "w", encoding="utf-8") as f:
        f.write("/* 自動生成，請勿手改 — python refresh.py */\n")
        f.write("window.HGP_DATA = " + payload + ";\n")

    q = out["queue"] or {}
    if out["warnings"] == []:
        warn_txt = "無"
    elif out["warnings"]:
        warn_txt = "、".join(w["title"] for w in out["warnings"])
    else:
        warn_txt = "抓取失敗"
    print("[ok] {} {} 皇崗 入境={} 出境={} 天氣={} 警告={} 通告={}".format(
        out["date"], out["clock"],
        STATUS.get(q.get("arr"), "?"), STATUS.get(q.get("dep"), "?"),
        (out["weather"] or {}).get("desc", "?"), warn_txt, len(out["news"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
