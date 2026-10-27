#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皇崗口岸每日資訊 — 資料抓取腳本
用法: python refresh.py
輸出: data.js (供 index.html 以 <script> 載入，可離線開檔) 及 data.json
資料來源: 香港入境事務處開放數據 / 香港天文台經 open-meteo
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
HKT = timezone(timedelta(hours=8))

IMMD = "https://secure1.info.gov.hk/immd/mobileapps/2bb9ae17/data/CPQueueTimeR.json"
IMMD_V = "https://secure1.info.gov.hk/immd/mobileapps/2bb9ae17/data/CPQueueTimeV.json"
WEATHER = ("https://api.open-meteo.com/v1/forecast?latitude=22.5317&longitude=114.0694"
           "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=Asia%2FHong_Kong&forecast_days=2")

# 入境處狀態碼 -> 文字 (來源: 入境處數據字典)
STATUS = {0: "正常", 1: "繁忙", 2: "非常繁忙", 4: "系統維護", 99: "非服務時間"}
WMO = {0:"天晴",1:"大致晴朗",2:"局部多雲",3:"多雲",45:"有霧",48:"霧凇",51:"毛毛雨",53:"毛毛雨",55:"毛毛雨",
       56:"凍雨",57:"凍雨",61:"小雨",63:"中雨",65:"大雨",66:"凍雨",67:"凍雨",71:"小雪",73:"中雪",75:"大雪",
       77:"雪粒",80:"驟雨",81:"驟雨",82:"強驟雨",85:"陣雪",86:"陣雪",95:"雷暴",96:"雷暴有冰雹",99:"雷暴有冰雹"}

def get_json(url, tries=3, timeout=20):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HGP-Daily/1.0",
                "Accept": "application/json,*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:      # noqa: BLE001
            last = e
    raise last

def queue_block(q):
    if not isinstance(q, dict):
        return None
    return {"arr": int(q.get("arrQueue", -1)), "dep": int(q.get("depQueue", -1))}

def build_tips(now, weather):
    """依日期/時間/天氣產生今日提示 (規則式，非官方預測)"""
    tips = []
    wd = now.weekday()          # 0=Mon
    hour = now.hour

    # 時段
    if 23 <= hour or hour < 6:
        tips.append(("深夜時段", "口岸 24 小時開放，但深圳地鐵 7 號線已收車。港方只餘通宵巴士 NB73、79S、N44B、616S 及市區／新界的士。", "warn"))
    elif 7 <= hour < 9:
        tips.append(("早上繁忙", "跨境上班上學人流集中，建議預留 20–30 分鐘排隊及轉車時間。", "info"))
    elif hour in (17, 18, 19):
        tips.append(("傍晚高峰", "傍晚為返港／北上雙向高峰，港方 L2 交匯處候車人龍較長。", "info"))

    # 星期
    if wd == 4:
        tips.append(("週五北上", "星期五晚上為每週最擠時段之一，通宵巴士及跨境巴士都會排隊。", "warn"))
    elif wd == 5:
        tips.append(("星期六", "早上北上、晚上返港為雙高峰；想避人潮可選上午 10 時前或下午 2–4 時。", "info"))
    elif wd == 6:
        tips.append(("星期日", "傍晚 5 時至晚上 10 時為返港高峰，建議提早 1 小時出發。", "warn"))
    else:
        tips.append(("平日", "平日人流相對穩定（開通初期平均約 8.3 萬人次／日），自助通道一般 3–5 分鐘完成。", "ok"))

    # 天氣
    if weather:
        pop = weather.get("pop")
        code = weather.get("code")
        if pop is not None and pop >= 60:
            tips.append(("有雨", "預測降雨機率 {}%，口岸大樓至上車位置有蓋但轉車需步行，記得帶傘。".format(pop), "warn"))
        if code in (95, 96, 99):
            tips.append(("雷暴", "雷暴可能影響戶外上落客區，預留額外時間。", "warn"))
        tmax = weather.get("tmax")
        if tmax is not None and tmax >= 33:
            tips.append(("高溫", "最高約 {}°C，大樓內冷氣足夠，但往返交通交匯處會熱。".format(tmax), "info"))

    tips.append(("必記", "港方口岸區屬禁區且不設公眾停車場；私家車請泊沿線停車場再轉公共交通工具。", "info"))
    return [{"tag": t, "text": x, "level": lv} for t, x, lv in tips]

def main():
    now = datetime.now(HKT)
    out = {"generated_at": now.isoformat(timespec="seconds"),
           "date": now.strftime("%Y-%m-%d"),
           "weekday": "星期" + "一二三四五六日"[now.weekday()],
           "clock": now.strftime("%H:%M"),
           "queue": None, "queue_visitor": None, "others": {}, "weather": None, "ok": False}

    try:
        r = get_json(IMMD); v = get_json(IMMD_V)
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

    out["tips"] = build_tips(now, out["weather"])

    payload = json.dumps(out, ensure_ascii=False, indent=1)
    with open(os.path.join(BASE, "data.json"), "w", encoding="utf-8") as f:
        f.write(payload)
    with open(os.path.join(BASE, "data.js"), "w", encoding="utf-8") as f:
        f.write("/* 自動生成，請勿手改 — python refresh.py */\n")
        f.write("window.HGP_DATA = " + payload + ";\n")

    q = out["queue"] or {}
    print("[ok] {} {} 皇崗 入境={} 出境={} 天氣={}".format(
        out["date"], out["clock"],
        STATUS.get(q.get("arr"), "?"), STATUS.get(q.get("dep"), "?"),
        (out["weather"] or {}).get("desc", "?")))
    return 0

if __name__ == "__main__":
    sys.exit(main())
