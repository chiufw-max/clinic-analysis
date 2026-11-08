# CLAUDE.md

給 AI 助理的專案說明。

## 專案內容

- `clinic_advanced_app.py`：歐葉豐原診所品項分析（Streamlit，套件見 `requirements.txt`）
- `index.html`、`LOGO.png`、`background.png`：網站頁面與圖檔
- `finance/`：財經頁面；`finance/archive/` 由每日自動更新（"Daily update" commit）寫入，不要手動修改

## AI 工作區

- AI 產出的檔案一律放在 `ai/`（詳見 `ai/README.md`）：
  - `ai/notes/` 筆記與分析過程
  - `ai/reports/` 報告
  - `ai/scripts/` 實驗用腳本
- 不要在儲存庫中寫入病患個資、密碼或金鑰。
- 回覆使用繁體中文。
