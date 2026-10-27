# 皇崗口岸 · 每日資訊站

新皇崗口岸（2026-10-12 06:30 啟用，一地兩檢）的每日資訊網站：
實時出入境輪候、天氣、時段提示、港深兩地交通接駁、過關流程、票價與常見問題。

## 檔案

| 檔案 | 作用 |
|---|---|
| `index.html` | 網站本體（單檔，CSS/JS 內嵌，無外部依賴） |
| `data.js` | 每日快照（`window.HGP_DATA`），由 `refresh.py` 自動產生 |
| `data.json` | 同一份資料的 JSON 版，方便其他程式取用 |
| `refresh.py` | 抓入境處輪候 + 天氣，重寫 `data.js` / `data.json` |
| `serve.py` | 本地伺服器（8080）：靜態檔 + `/api/live` 代理 + 每 5 分鐘自動更新 |
| `start.bat` | 雙擊即啟動 `serve.py` 並開瀏覽器 |

## 三種用法

**1. 完整功能（推薦）** — 雙擊 `start.bat`
→ 開啟 http://127.0.0.1:8080/ ，狀態卡每 60 秒自動更新，伺服器每 5 分鐘重寫快照。

**2. 只想睇一次** — 直接雙擊 `index.html`
→ 以 `file://` 開啟，顯示最後一次快照（`data.js`），右上角會標示「離線快照」。
更新快照：`python refresh.py`。

**3. 放上網** — 把 `index.html` + `data.js` 上傳到任何靜態託管（GitHub Pages / Cloudflare Pages）。
→ 能顯示快照內容，但**不會有即時更新**（瀏覽器無法直接抓入境處 JSON，該 API 無 CORS 標頭）。
若要線上即時更新，需將 `serve.py` 的 `build_live()` 搬去 Cloudflare Worker / Vercel Function 等伺服器端。

## 每日自動更新（Windows 工作排程器）

```
schtasks /create /tn "HGP每日更新" /sc daily /st 07:00 ^
 /tr "python \"C:\Users\Neuron\OneDrive - Neuron Operations Limited\Desktop\huanggang-port\refresh.py\""
```

（如路徑含空格，請確認引號；亦可在「工作排程器」圖形介面新增，動作＝啟動程式 `python`，引數＝`refresh.py`，起始於＝本資料夾。）

## 資料來源

| 項目 | 來源 | 更新 |
|---|---|---|
| 出入境輪候（居民／訪客 × 入境／出境） | 入境事務處開放數據 `CPQueueTimeR.json` / `CPQueueTimeV.json`（口岸代號 `HGP`） | 15 分鐘 |
| 狀態碼 | 0 正常／1 繁忙／2 非常繁忙／4 系統維護／99 非服務時間（見入境處數據字典） | — |
| 天氣 | open-meteo（深圳福田 22.5317N, 114.0694E） | 實時 |
| 交通、票價、服務時間 | 運輸署「前往皇崗口岸」頁 | 人手更新 |
| 口岸安排、大樓設施 | 保安局皇崗口岸專頁、深圳市口岸辦 | 人手更新 |

## 自訂

- **改提示文字**：`refresh.py` 的 `build_tips()`，用日期／時間／天氣規則產生；改完跑一次 `python refresh.py`。
- **改票價／路線**：直接改 `index.html` 內的靜態表格（搜尋 `B10`）。
- **換口岸**：`index.html` 最下方 `PORTS` / `NOTE` 兩個物件控制對照表；`HGP` 換成 `LWS`（羅湖）等即可改成其他口岸版。

## 已知限制

- 入境處只公布旅客輪候的**概括評估**（正常／繁忙／非常繁忙），沒有實際分鐘數，也沒有車輛排隊數據。
- 口岸剛開通（2026-10），班次、票價、樓層動線仍在微調，一切以現場指示及官方公布為準。
- 本頁為非官方整合，不構成任何官方資訊。
