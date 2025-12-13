import os
import io
import json
import pandas as pd
import streamlit as st
from PIL import Image

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="診所用量分析系統", layout="wide")

CACHE_FILE = "clinic_cache.csv"
GROUPS_FILE_NAME = "clinic_groups.json"
LOG_FILE_NAME = "access_log.csv"

# =========================
# Google Drive 服務
# =========================
def get_drive_service():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        st.error(f"Drive 連線失敗：{e}")
        return None


def find_drive_file_id(filename):
    service = get_drive_service()
    if not service:
        return None

    q = f"name='{filename}' and trashed=false"
    res = service.files().list(q=q, fields="files(id,name)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def download_from_drive(filename):
    service = get_drive_service()
    if not service:
        return None

    file_id = find_drive_file_id(filename)
    if not file_id:
        return None

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.getvalue()


def upload_to_drive(filename, data, mime):
    service = get_drive_service()
    if not service:
        return

    file_id = find_drive_file_id(filename)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=True)

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        service.files().create(
            body={"name": filename},
            media_body=media,
            fields="id"
        ).execute()


def delete_drive_file_by_name(filename):
    service = get_drive_service()
    if not service:
        return
    file_id = find_drive_file_id(filename)
    if file_id:
        service.files().delete(fileId=file_id).execute()


# =========================
# 資料處理
# =========================
def load_data_cache():
    if os.path.exists(CACHE_FILE):
        return pd.read_csv(CACHE_FILE)

    data = download_from_drive(CACHE_FILE)
    if data:
        df = pd.read_csv(io.BytesIO(data))
        df.to_csv(CACHE_FILE, index=False)
        return df

    return pd.DataFrame()


def save_cache(df):
    df.to_csv(CACHE_FILE, index=False)
    upload_to_drive(
        CACHE_FILE,
        df.to_csv(index=False).encode("utf-8"),
        "text/csv"
    )

# =========================
# ⭐⭐⭐ 主程式開始 ⭐⭐⭐
# =========================

# 🔑 保命宣告（一定要在 sidebar 前）
uploaded_files = None

# =========================
# Sidebar
# =========================
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image(Image.open("logo.png"), width=260)
    else:
        st.header("🏥 診所分析系統")

    st.markdown("---")

    uploaded_files = st.file_uploader(
        "上傳用量檔（txt）",
        type=["txt", "TXT"],
        accept_multiple_files=True
    )

    st.markdown("---")

    if st.button("🗑️ 清除所有資料"):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

        delete_drive_file_by_name(CACHE_FILE)
        delete_drive_file_by_name(GROUPS_FILE_NAME)
        delete_drive_file_by_name(LOG_FILE_NAME)

        st.success("已清除")
        st.rerun()

# =========================
# 主畫面
# =========================
st.title("📊 用量分析結果")

main_df = load_data_cache()

if uploaded_files:
    new_rows = []
    for f in uploaded_files:
        text = f.read().decode("utf-8", errors="ignore")
        for line in text.splitlines():
            new_rows.append({"raw": line})

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        main_df = pd.concat([main_df, df_new], ignore_index=True)
        save_cache(main_df)
        st.success(f"已匯入 {len(new_rows)} 筆資料")

if main_df.empty:
    st.info("目前尚無資料")
else:
    st.dataframe(main_df, use_container_width=True)

