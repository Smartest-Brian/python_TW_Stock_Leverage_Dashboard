# 臺灣股市槓桿風險指標與情緒儀表板 (TWSE / TAIFEX)

本專案是一個專為雲端開發環境（如 Google Antigravity / Project IDX）設計的專業量化分析系統。透過自動化抓取台灣證券交易所（TWSE）及台灣期貨交易所（TAIFEX）過去 5 年的信用交易與期權數據，計算客製化的「當前市場槓桿風險百分比指標」，並自動生成一個**完全獨立、互動式且高美感的 HTML 儀表板** (`taiwan_leverage_dashboard.html`)，無須任何額外的伺服器即可直接在瀏覽器中預覽。

---

## 📊 系統核心用途

本系統透過雙重維度評估台股市場的極端風險與情緒：

1. **信用交易槓桿（融資融券趨勢）：**
   - 串接 FinMind API 獲取過去 5 年的大盤**融資餘額（Margin Balance）**與**融券餘額（Short Sale Balance）**。
   - 計算「當前槓桿風險百分比」，公式為：
     $$\text{槓桿風險百分比} = \frac{\text{當前融資餘額} - \text{5年最低融資}}{\text{5年最高融資} - \text{5年最低融資}} \times 100\%$$
     反映當前散戶槓桿相對於歷史常態的堆疊程度（低於 40% 為籌碼乾淨，高於 80% 則面臨高度融資多殺多及斷頭風險）。

2. **期權多空情緒（Put/Call Ratio）：**
   - 透過高效的 30 天分片爬蟲，從 TAIFEX 官網精確爬取 5 年的**台指選擇權未平倉量（Open Interest）買賣權比率**。
   - PCR > 100% 代表下方賣權支撐力道強勁（多頭格局）；PCR < 100% 代表上方買權壓制力強，避險情緒高漲（空頭格局）。

---

## 🛠️ 技術相依性

為符合開發規範與保護本機環境，系統嚴格遵循環境隔離原則：
- **數據處理：** `pandas`, `requests`
- **HTML 解析：** `lxml`（用於 `pandas.read_html`）
- **互動圖表：** `plotly.graph_objects` (Plotly)
- **環境隔離：** 必須在專案目錄下的 `.venv` 虛擬環境中運行，不得進行全域套件安裝。

---

## 🚀 執行方法與步驟

請按照以下步驟初始化虛擬環境並執行腳本：

### 步驟 1：建立虛擬環境
在專案根目錄下，執行以下命令初始化 Python 虛擬環境 (`.venv`)：
```bash
python3 -m venv .venv
```

### 步驟 2：安裝相依套件
使用虛擬環境專屬的 `pip` 安裝資料處理與視覺化套件：
```bash
.venv/bin/pip install pandas requests plotly lxml
```

### 步驟 3：執行分析與生成儀表板
啟動主控制器 `generate_dashboard.py`，系統將自動開始拉取 5 年數據、執行量化計算並輸出 HTML 儀表板：
```bash
.venv/bin/python3 generate_dashboard.py
```
> 💡 *註：為維持對交易所伺服器的友善度，抓取 TAIFEX 5 年數據時每次僅查詢 30 天，並於請求間設有 1 秒延遲，整體抓取時間大約為 60–75 秒。*

### 步驟 4：瀏覽儀表板
腳本執行成功後，會在專案根目錄下生成一個 `taiwan_leverage_dashboard.html`。您只需在瀏覽器中雙擊打開此檔案，或在 Cloud IDE 中開啟靜態預覽，即可享受極具視覺美感的暗黑風格專業量化儀表板。

---

## ⚙️ 專案目錄結構

```text
├── .venv/                         # Python 隔離虛擬環境 (Git 已忽略)
├── .gitignore                     # Git 排除清單 (包含環境、日誌與臨時快取)
├── README.md                      # 本專案說明文件 (Traditional Chinese)
├── generate_dashboard.py          # 主分析與爬蟲腳本 (English code, structured logging)
└── taiwan_leverage_dashboard.html # 生成的互動式獨立網頁儀表板 (Traditional Chinese UI)
```

---

## ⚠️ 免責聲明
本專案與生成的儀表板僅供學術研究與量化回測參考，不構成任何實際的投資買賣建議。市場交易有風險，信用槓桿與衍生性商品具備高度槓桿，請審慎評估。