#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皇崗口岸（深方）即時狀態 + 聯檢大樓實時鏡頭
來源：深圳口岸辦「口岸通」https://i.ka.sz.gov.cn/attend/kab-park/
該站 API 有 AES 加密＋簽名，故用無頭瀏覽器讀渲染結果；鏡頭為帶時間戳的 PNG 直連，
只取網址（不存圖），由瀏覽器直接載入。

輸出 sz.js → window.HGP_SZ = {updated, clock, port:{...}, cams:[{f,n,flow,ts,url}]}
失敗時不覆寫舊檔（保留上一次成功快照）。
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "sz.js")
HKT = timezone(timedelta(hours=8))
IDX = "https://i.ka.sz.gov.cn/attend/kab-park/park/index?type=xianggang&language=zhs"
CAMS = ("https://i.ka.sz.gov.cn/attend/kab-park/park/info"
        "?id=2099387710983634944&language=zhs")

LEVEL = {"暢通": 0, "畅通": 0, "正常": 0,
         "繁忙": 1,
         "擁擠": 2, "拥挤": 2, "擁堵": 2, "拥堵": 2, "非常繁忙": 2,
         "非通關時間": 3, "非通关时间": 3, "暫停": 3, "暂停": 3, "關閉": 3, "关闭": 3}
NAME_FIX = {"皇岗口岸": "皇崗口岸"}


def parse_place(raw):
    """'皇崗口岸聯檢大樓內地口岸區L5層西側交通廳（入境人流動線）' → (L5, 西側交通廳, 入境人流動線)"""
    raw = raw.replace("鏡頭地點:", "").replace("鏡頭地點：", "").strip()
    m = re.search(r"([LB]\d)層(.+?)（(.+?)）", raw)
    if m:
        return m.group(1), m.group(2).strip(), m.group(3).strip()
    return "", raw, ""


def scrape():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(locale="zh-CN", user_agent=(
            "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Mobile Safari/537.36"))
        page = ctx.new_page()

        # 1) 皇崗狀態
        page.goto(IDX, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".park-cell", timeout=30000)
        page.wait_for_timeout(1200)
        rows = page.eval_on_selector_all(
            ".park-cell",
            "els => els.map(e => e.innerText.split('\\n').map(s=>s.trim()).filter(Boolean))")
        port = None
        for lines in rows:
            if not lines or ("皇崗" not in lines[0] and "皇岗" not in lines[0]):
                continue
            status, hours = "", ""
            for s in lines[1:]:
                if not status and len(s) <= 6:
                    status = s
                m = re.search(r"運行時間[:：]\s*(.+)", s) or re.search(r"运行时间[:：]\s*(.+)", s)
                if m:
                    hours = m.group(1).strip()
            port = {"name": NAME_FIX.get(lines[0], lines[0]), "status": status,
                    "hours": hours, "level": LEVEL.get(status, 0)}
            break

        # 2) 聯檢大樓鏡頭
        page.goto(CAMS, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".video-item", timeout=45000)
        page.wait_for_timeout(4000)
        raw = page.eval_on_selector_all(".video-item", """els => els.map(e => {
            const im = e.querySelector('img');
            const txt = (e.innerText || '').replace(/\\n+/g,' ').trim();
            return [txt, im ? (im.currentSrc || im.src) : ''];
        })""")
        b.close()

    cams, seen = [], set()
    for txt, url in raw:
        if not url or "/monitor/pic/" not in url or url in seen:
            continue
        seen.add(url)
        f, n, flow = parse_place(txt)
        ts = ""
        m = re.search(r"-(\d{14})\.png", url)
        if m:
            d = m.group(1)
            ts = "%s:%s:%s" % (d[8:10], d[10:12], d[12:14])
        cams.append({"f": f, "n": n, "flow": flow, "ts": ts, "url": url})
    return port, cams


def main():
    try:
        port, cams = scrape()
    except Exception as e:              # noqa: BLE001
        print("[warn] 皇崗口岸抓取失敗:", str(e)[:160], file=sys.stderr)
        return 1
    if not port:
        print("[warn] 解析不到皇崗口岸狀態", file=sys.stderr)
        return 1
    now = datetime.now(HKT)
    data = {"updated": now.isoformat(timespec="seconds"),
            "clock": now.strftime("%H:%M"),
            "source_url": IDX,
            "port": port,
            "cams": cams}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("/* 自動生成：深圳口岸辦口岸通 — 皇崗口岸；請勿手改 */\n")
        f.write("window.HGP_SZ = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("[ok] %s 皇崗口岸=%s｜鏡頭 %d 個" % (now.strftime("%H:%M"), port["status"], len(cams)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
