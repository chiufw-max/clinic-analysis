# ai/ — AI 專用工作區

這個資料夾給 AI 助理（例如 Claude Code）放產出與工作檔，跟診所系統、財經頁面的正式檔案分開。

| 路徑 | 用途 |
| --- | --- |
| `ai/notes/` | 筆記、分析過程、待辦事項 |
| `ai/reports/` | 給人看的報告（Markdown、HTML、圖表） |
| `ai/scripts/` | 一次性或實驗用的腳本，還沒正式納入主程式 |

## 規則

- AI 新增的檔案預設放在這裡，不要散落在根目錄。
- 要修改正式檔案（`clinic_advanced_app.py`、`index.html`、`finance/`）時，要說明原因，並在分支上進行。
- 不要放病患個資、帳號密碼、API 金鑰。
- 檔名建議加日期，例如 `ai/reports/2026-11-08-品項分析.md`。
