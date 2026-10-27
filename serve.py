#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皇崗口岸資訊站 — 本地伺服器
- 提供靜態檔案 (index.html / data.js)
- /api/live 伺服器端代抓入境處 + 天氣 (解決瀏覽器 CORS 限制)
- 背景每 5 分鐘自動更新 data.js
用法: python serve.py [port]     預設 8080
"""
import json, os, sys, threading, time, webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import refresh

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
REFRESH_SEC = 300

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/live":
            try:
                body = json.dumps(build_live(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:                      # noqa: BLE001
                msg = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            return
        if self.path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/live" in (args[0] if args else ""):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

def build_live():
    """即時查入境處兩份 JSON + 天氣，回傳精簡結構"""
    from datetime import datetime, timezone, timedelta
    HKT = timezone(timedelta(hours=8))
    r = refresh.get_json(refresh.IMMD)
    v = refresh.get_json(refresh.IMMD_V)
    now = datetime.now(HKT)
    out = {"ok": True, "generated_at": now.isoformat(timespec="seconds"),
           "clock": now.strftime("%H:%M"),
           "queue": refresh.queue_block(r.get("HGP")),
           "queue_visitor": refresh.queue_block(v.get("HGP")),
           "others": {k: refresh.queue_block(x) for k, x in r.items() if k != "HGP"}}
    try:
        w = refresh.get_json(refresh.WEATHER)
        cur, day = w.get("current", {}), w.get("daily", {})
        out["weather"] = {"temp": round(cur.get("temperature_2m", 0)),
                          "humidity": cur.get("relative_humidity_2m"),
                          "code": cur.get("weather_code"),
                          "desc": refresh.WMO.get(cur.get("weather_code"), "—"),
                          "tmax": round(day.get("temperature_2m_max", [0])[0]),
                          "tmin": round(day.get("temperature_2m_min", [0])[0]),
                          "pop": day.get("precipitation_probability_max", [None])[0]}
    except Exception:                                   # noqa: BLE001
        pass
    return out

def refresher():
    while True:
        try:
            refresh.main()
        except Exception as e:                          # noqa: BLE001
            sys.stderr.write("[refresh] %s\n" % e)
        time.sleep(REFRESH_SEC)

def main():
    threading.Thread(target=refresher, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/" % PORT
    print("皇崗口岸資訊站 → %s   (Ctrl+C 停止)" % url)
    try:
        webbrowser.open(url)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")

if __name__ == "__main__":
    main()
