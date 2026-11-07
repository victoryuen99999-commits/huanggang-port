#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深圳口岸辦「口岸通」即時狀態（皇崗/福田/羅湖/深圳灣/蓮塘/文錦渡/西九龍）
該站以 AES + 簽名保護 API，故用無頭瀏覽器讀取渲染結果。

用法: python sz_refresh.py
輸出: sz.js → window.HGP_SZ = {updated, source_url, ports:[{name,status,hours}]}
失敗時不覆寫舊檔（保留上一次成功快照）。
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "sz.js")
HKT = timezone(timedelta(hours=8))
URL = "https://i.ka.sz.gov.cn/attend/kab-park/park/index?type=xianggang&language=zhs"

# 內地狀態 -> 本站級別（顏色）
LEVEL = {"暢通": 0, "畅通": 0, "正常": 0,
         "繁忙": 1, "擁擠": 2, "拥挤": 2, "擁堵": 2, "拥堵": 2, "暫停": 3, "暂停": 3}


def scrape():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(locale="zh-CN", user_agent=(
            "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Mobile Safari/537.36"))
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".park-cell", timeout=30000)
        page.wait_for_timeout(1500)
        cells = page.eval_on_selector_all(".park-cell", """els => els.map(e => e.innerText.split('\\n').map(s=>s.trim()).filter(Boolean))""")
        b.close()
    ports = []
    for lines in cells:
        if not lines:
            continue
        name = lines[0]
        status = ""
        hours = ""
        for s in lines[1:]:
            if not status and len(s) <= 6:
                status = s
            m = re.search(r"運行時間[:：]\s*(.+)", s) or re.search(r"运行时间[:：]\s*(.+)", s)
            if m:
                hours = m.group(1).strip()
        if name:
            ports.append({"name": name, "status": status, "hours": hours,
                          "level": LEVEL.get(status, 0)})
    return ports


def main():
    try:
        ports = scrape()
    except Exception as e:              # noqa: BLE001
        print("[warn] 深圳口岸抓取失敗:", str(e)[:160], file=sys.stderr)
        return 1
    if not ports:
        print("[warn] 解析不到口岸資料", file=sys.stderr)
        return 1
    now = datetime.now(HKT)
    data = {"updated": now.isoformat(timespec="seconds"),
            "clock": now.strftime("%H:%M"),
            "source_url": URL,
            "ports": ports}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("/* 自動生成：深圳口岸辦口岸通 — 請勿手改 */\n")
        f.write("window.HGP_SZ = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("[ok] 深圳側 %s：%s" % (now.strftime("%H:%M"),
          "、".join("%s=%s" % (p["name"], p["status"]) for p in ports)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
