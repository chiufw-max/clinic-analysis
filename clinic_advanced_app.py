import streamlit as st
import pandas as pd
import re
from io import BytesIO, StringIO
import os
import json
import math
import altair as alt
from PIL import Image
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import requests
from google_auth_oauthlib.flow import Flow

def google_login_get_email():
    if "google_email" in st.session_state:
        return st.session_state["google_email"]

    client_id = st.secrets["google_oauth"]["client_id"]
    client_secret = st.secrets["google_oauth"]["client_secret"]
    redirect_uri = st.secrets["google_oauth"]["redirect_uri"]

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
        redirect_uri=redirect_uri,
    )

    qp = st.query_params

    # 沒帶 code：顯示登入按鈕
    if "code" not in qp:
        auth_url, _ = flow.authorization_url(
            prompt="select_account",
            include_granted_scopes="true",
        )
        st.link_button("使用 Google 登入", auth_url, type="primary", use_container_width=True)
        return None

    # 帶 code：換 token
    code = qp["code"]
    flow.fetch_token(code=code)

    creds = flow.credentials
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10,
    )
    resp.raise_for_status()
    email = resp.json().get("email")

    if email:
        st.session_state["google_email"] = email
        st.query_params.clear()  # 清掉網址上的 code，避免重整時重跑

    return email


# --- 1. 頁面設定 ---
st.set_page_config(page_title="歐葉豐原診所品項分析", layout="wide", page_icon="🏥")

# === 🛡️ 安全設定：白名單 ===
# 系統會先自動抓取 Google 帳號，若失敗才會比對這裡的輸入
ALLOWED_USERS = [
    "chiufw@gmail.com",
    "mmday11200518@gmail.com",
    # "ming@gmail.com", # 開發測試用，上線可註解掉
]

# 顏色配置
CHART_COLORS = ["#7A8B99", "#A89B9D", "#8F9E8B", "#C6B2A2", "#6D8299", "#B58B8B", "#8C9E9E", "#D8A48F", "#5F7161"]

# 注入 CSS (雙風格: 莫蘭迪/Apple)
st.markdown(f"""
    <style>
    /* === 核心變數定義 === */
    :root {{
        --bg-color: #F5F5F7; --sidebar-bg: #EAEAEA; --text-color: #4A4A4A;
        --primary-color: #7A8B99; --secondary-bg: #FFFFFF; --input-bg: #FFFFFF;
        --border-color: #D1D1D1; --tab-bg: #E0E0E0; --tab-active: #8F9E8B;
        --shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg-color: #000000; --sidebar-bg: #1C1C1E; --text-color: #F5F5F7;
            --primary-color: #0A84FF; --secondary-bg: #1C1C1E; --input-bg: #2C2C2E;
            --border-color: #3A3A3C; --tab-bg: #2C2C2E; --tab-active: #0A84FF;
            --shadow: 0 4px 15px rgba(0,0,0,0.4);
        }}
    }}

    /* === 全站樣式 === */
    html, body, [class*="css"] {{ 
        font-family: -apple-system, "Microsoft JhengHei", sans-serif; font-size: 20px; 
        color: var(--text-color) !important; background-color: var(--bg-color) !important;
    }}
    .stApp {{ background-color: var(--bg-color) !important; }}
    [data-testid="stSidebar"] {{ background-color: var(--sidebar-bg) !important; border-right: 1px solid var(--border-color); }}
    [data-testid="stSidebar"] * {{ color: var(--text-color) !important; }}
    [data-testid="stSidebar"] img {{ display: block; margin: auto; }}
    
    [data-testid="stFileUploaderDropzoneInstructions"], section[data-testid="stFileUploader"] small {{ display: none; }}
    section[data-testid="stFileUploader"] {{ padding-top: 10px; }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{ gap: 12px; background-color: transparent; }}
    .stTabs [data-baseweb="tab"] {{ 
        background-color: var(--tab-bg); border-radius: 12px; color: var(--text-color); border: none !important; 
        padding: 12px 32px !important; font-size: 20px !important; transition: all 0.3s ease;
    }}
    .stTabs [aria-selected="true"] {{ background-color: var(--tab-active) !important; color: white !important; font-weight: 600; box-shadow: var(--shadow); }}
    div[data-baseweb="tab-highlight"] {{ display: none !important; }}

    /* Inputs */
    .stSelectbox div[data-baseweb="select"], .stTextInput input {{ 
        background-color: var(--input-bg) !important; color: var(--text-color) !important; border-radius: 12px; 
        border: 1px solid var(--border-color) !important; min-height: 50px !important; font-size: 20px !important;
    }}
    ul[data-baseweb="menu"] {{ background-color: var(--sidebar-bg) !important; }}
    ul[data-baseweb="menu"] li {{ color: var(--text-color) !important; font-size: 20px !important; }}
    span[data-baseweb="tag"] {{ background-color: var(--tab-bg) !important; font-size: 18px !important; }}

    /* Buttons */
    div.stButton > button {{
        border-radius: 16px !important; border: 1px solid transparent !important; font-weight: 600 !important;
        transition: all 0.2s ease !important; padding: 16px 32px !important; font-size: 20px !important;
        line-height: 1.5 !important; min-height: 60px !important;
    }}
    div.stButton > button[kind="secondary"] {{ background-color: var(--tab-bg) !important; color: var(--text-color) !important; }}
    div.stButton > button[kind="secondary"]:hover {{ filter: brightness(0.9); transform: scale(1.01); }}
    div.stButton > button[kind="primary"] {{ background-color: var(--primary-color) !important; color: white !important; box-shadow: var(--shadow) !important; }}
    div.stButton > button[kind="primary"]:hover {{ filter: brightness(1.1); transform: scale(1.02); }}

    /* DataFrame */
    .stDataFrame {{ font-size: 20px !important; }}
    [data-testid="stDataFrame"] {{ background-color: var(--sidebar-bg); border-radius: 12px; padding: 10px; border: 1px solid var(--border-color); }}
    thead tr th:first-child, tbody th {{ display: none; }}
    
    h1, h2, h3, p, span, label, div {{ color: var(--text-color) !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- Google Drive 連線 ---
CACHE_FILE = "clinic_cache.csv"
GROUPS_FILE_NAME = "clinic_groups.json"
LOG_FILE_NAME = "access_log.csv"

def get_drive_service():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive']
            )
            return build('drive', 'v3', credentials=creds)
        except Exception: return None
    return None

def upload_to_drive(filename, content, mime_type):
    service = get_drive_service()
    if not service: return
    try:
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type)
        results = service.files().list(q=f"name='{filename}' and trashed=false", fields="files(id)").execute()
        items = results.get('files', [])
        if items:
            service.files().update(fileId=items[0]['id'], media_body=media).execute()
        else:
            service.files().create(body={'name': filename}, media_body=media).execute()
    except Exception as e: print(f"Upload Error: {e}")

def download_from_drive(filename):
    service = get_drive_service()
    if not service: return None
    try:
        results = service.files().list(q=f"name='{filename}' and trashed=false", fields="files(id)").execute()
        items = results.get('files', [])
        if items:
            return service.files().get_media(fileId=items[0]['id']).execute()
    except: pass
    return None

def log_access_to_drive(email, action="Login"):
    service = get_drive_service()
    if not service: return
    tw_time = datetime.utcnow() + timedelta(hours=8)
    new_entry = pd.DataFrame([{'Time': tw_time.strftime("%Y-%m-%d %H:%M:%S"), 'User': email, 'Action': action}])
    try:
        content = download_from_drive(LOG_FILE_NAME)
        if content:
            old_df = pd.read_csv(StringIO(content.decode('utf-8')))
            final_df = pd.concat([old_df, new_entry], ignore_index=True)
        else: final_df = new_entry
        upload_to_drive(LOG_FILE_NAME, final_df.to_csv(index=False).encode('utf-8'), 'text/csv')
    except Exception as e: print(f"Log Error: {e}")

def try_auto_detect_email():
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            email = st.context.headers.get("X-Streamlit-User-Email") or st.context.headers.get("x-streamlit-user-email")
            if email: return email
    except: pass
    try:
        if hasattr(st, "user") and st.user and st.user.email: return st.user.email
    except: pass
    try:
        if hasattr(st, "experimental_user") and st.experimental_user.email: return st.experimental_user.email
    except: pass
    return None

# --- 🔐 登入驗證：Google OAuth + 白名單 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False
if "confirmed_email" not in st.session_state:
    st.session_state.confirmed_email = None

if not st.session_state.password_correct:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            st.image(Image.open("logo.png"), width=200)

        st.title("🔒 診所系統登入（Google 驗證）")

        email = google_login_get_email()
        if not email:
            st.stop()

        st.success(f"👋 已登入：{email}")

        if email.lower() in [u.lower() for u in ALLOWED_USERS]:
            st.session_state.password_correct = True
            st.session_state.confirmed_email = email
            log_access_to_drive(email, "Login Success (Google OAuth)")
            st.rerun()
        else:
            st.error("⛔ 此 Google 帳號未獲授權")
            log_access_to_drive(email, "Login Denied (Whitelist, Google OAuth)")
            st.stop()


# --- 主邏輯 ---
def load_groups():
    content = download_from_drive(GROUPS_FILE_NAME)
    if content: return json.loads(content.decode('utf-8'))
    if os.path.exists(GROUPS_FILE_NAME):
        with open(GROUPS_FILE_NAME, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_groups(groups):
    with open(GROUPS_FILE_NAME, "w", encoding="utf-8") as f: json.dump(groups, f, ensure_ascii=False, indent=2)
    upload_to_drive(GROUPS_FILE_NAME, json.dumps(groups, ensure_ascii=False).encode('utf-8'), 'application/json')

def load_data_cache():
    content = download_from_drive(CACHE_FILE)
    if content: return pd.read_csv(StringIO(content.decode('utf-8')))
    if os.path.exists(CACHE_FILE): return pd.read_csv(CACHE_FILE)
    return pd.DataFrame()

def save_data_cache(df):
    csv_bytes = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    with open(CACHE_FILE, "wb") as f: f.write(csv_bytes)
    upload_to_drive(CACHE_FILE, csv_bytes, 'text/csv')

def parse_usage_file(file):
    try: stringio = file.getvalue().decode("utf-8")
    except: stringio = file.getvalue().decode("big5", errors='ignore')
    lines = stringio.splitlines(); parsed_data = []
    month_label = file.name
    num_match = re.search(r'(\d{3,5})', file.name)
    if num_match:
        d = num_match.group(1)
        if len(d) == 5: month_label = f"{int(d[:3])+1911}-{d[3:]}"
    for line in lines:
        s = line.strip()
        if not s or "歐葉" in s or "列印日期" in s or "=====" in s or "本頁" in s or "品名" in s: continue
        m = re.search(r'(\S+)\s+(.+)\s+(\S+)\s+([0-9\.]+)\s*$', line)
        if m:
            code, mid, unit, qty = m.group(1), m.group(2).strip(), m.group(3), float(m.group(4))
            parts = mid.split(maxsplit=1)
            nhi, name = (parts[0], parts[1]) if len(parts)==2 and re.match(r'^[A-Z0-9]{8,12}$', parts[0]) else ("", mid)
            parsed_data.append({'代碼':code, '健保碼':nhi, '名稱':name, '顯示名稱':f"{code} {name}", '單位':unit, '數量':math.ceil(qty), '月份':month_label})
    return pd.DataFrame(parsed_data)

def make_interactive_chart(data_df, x_col, y_col, color_col, chart_type, title, color_range=CHART_COLORS):
    base = alt.Chart(data_df).encode(
        x=alt.X(x_col, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(
            y_col,
            title=None,
            type='quantitative',
            axis=alt.Axis(),
            scale=alt.Scale(nice=True, zero=True)
        ),
        tooltip=[
            alt.Tooltip(x_col, title='月份'),
            alt.Tooltip(color_col, title='品項'),
            alt.Tooltip(y_col, title='數量', format=',')
        ]
    ).properties(
        # ✅ 第 1 個地方：這裡
        title=alt.TitleParams(text=title, fontSize=24, anchor='middle', offset=18),
        height=500
    )

    if "直方圖" in chart_type:
        chart = base.mark_bar().encode(
            color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None))
        )
    else:
        chart = base.mark_line(point=True, strokeWidth=4).encode(
            color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None))
        )

    # ✅ 第 2 個地方：這裡
    return chart.configure(
        padding={'top': 130, 'left': 20, 'right': 20, 'bottom': 20},
        background='transparent'
    )


# --- 介面開始 ---
if st.button("🗑️ 清除所有資料"):
    # 刪本機 cache
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    # 刪雲端 Drive 檔案（用檔名找 id）
    delete_drive_file_by_name(CACHE_FILE)
    delete_drive_file_by_name(GROUPS_FILE_NAME)
    delete_drive_file_by_name(LOG_FILE_NAME)

    st.rerun()

        
    def delete_drive_file_by_name(filename):
    service = get_drive_service()
    if not service:
        return
    try:
        results = service.files().list(
            q=f"name='{filename}' and trashed=false",
            fields="files(id)"
        ).execute()
        for f in results.get("files", []):
            service.files().delete(fileId=f["id"]).execute()
    except Exception as e:
        print(f"Delete Error: {e}")


main_df = load_data_cache() 

if uploaded_files:
    new_dfs = [parse_usage_file(f) for f in uploaded_files if not parse_usage_file(f).empty]
    if new_dfs:
        new_data = pd.concat(new_dfs, ignore_index=True)
        if not main_df.empty:
            main_df = pd.concat([main_df, new_data], ignore_index=True).drop_duplicates()
        else:
            main_df = new_data
        save_data_cache(main_df)

st.title("歐葉豐原診所品項分析")
if not main_df.empty:
    months = sorted(main_df['月份'].unique())
    pivot_df = main_df.pivot_table(index=['代碼', '名稱', '顯示名稱', '單位'], columns='月份', values='數量', aggfunc='sum').fillna(0).astype(int)
    last_month = months[-1]
    pivot_df = pivot_df.sort_values(by=last_month, ascending=False)
    item_options = pivot_df.index.get_level_values('顯示名稱').tolist()

    # 初始化 State
    if 'saved_groups' not in st.session_state: st.session_state.saved_groups = load_groups()
    if 'active_group_view' not in st.session_state: st.session_state.active_group_view = None
    if 'new_group_name_input' not in st.session_state: st.session_state.new_group_name_input = ""
    if 'new_group_items_input' not in st.session_state: st.session_state.new_group_items_input = []
    if 'chart_type_pref' not in st.session_state: st.session_state.chart_type_pref = "直方圖"

    tab1, tab2, tab3, tab4 = st.tabs(["📊 總表", "🔍 單品", "⚔️ 比較", "📑 群組"])

    with tab1:
        st.markdown(f"**區間**：{months[0]}~{months[-1]} ｜ **品項**：{len(pivot_df)}")
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer: pivot_df.reset_index().drop(columns=['顯示名稱']).set_index(['代碼', '名稱', '單位']).to_excel(writer, sheet_name='用量')
        st.download_button("📥 下載 Excel", data=output.getvalue(), file_name='report.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        st.dataframe(pivot_df.reset_index().drop(columns=['顯示名稱']).style.background_gradient(cmap="Blues", subset=months).format(precision=0), use_container_width=True, height=600, hide_index=True)

    with tab2:
        c1, c2 = st.columns([1, 2])
        with c1:
            sel = st.selectbox("藥品", item_options, index=None, placeholder="...", label_visibility="collapsed")
            c_type = st.radio("圖", ["直方圖", "折線圖"], horizontal=True, key="s_chart")
            if sel:
                v = pivot_df.xs(sel, level='顯示名稱').iloc[0][months]
                curr, prev = v.iloc[-1], v.iloc[-2] if len(v)>1 else 0
                st.metric(f"{months[-1]}", int(curr), f"{int(curr-prev)} ({(curr-prev)/prev:.1%})" if prev>0 else None)
        with c2:
            if sel: st.altair_chart(make_interactive_chart(pd.DataFrame({'月份': months, '數量': v.values, '名稱': sel.split(' ', 1)[1]}), '月份', '數量', '名稱', c_type, f"趨勢：{sel.split(' ', 1)[1]}"), use_container_width=True)
            else: st.info("👈 請選擇")

    with tab3:
        c1, c2 = st.columns([1, 2])
        with c1:
            ms = st.multiselect("比較", item_options, placeholder="...")
            mt = st.radio("圖", ["直方圖 (堆疊)", "折線圖 (比較)"], horizontal=True)
        with c2:
            if ms:
                md = pivot_df[pivot_df.index.get_level_values('顯示名稱').isin(ms)][months].reset_index().melt(id_vars=['顯示名稱', '代碼', '名稱', '單位'], var_name='月份', value_name='數量')
                st.altair_chart(make_interactive_chart(md, '月份', '數量', '名稱', mt, "比較"), use_container_width=True)
                with st.expander("數據"): st.dataframe(pivot_df[pivot_df.index.get_level_values('顯示名稱').isin(ms)].reset_index().drop(columns=['顯示名稱', '代碼']).style.format(precision=0), hide_index=True)
            else: st.info("請選兩個以上")

    with tab4:
        st.markdown("##### 📁 群組")
        gs = list(st.session_state.saved_groups.keys())
        cols = st.columns(4)
        for i, g in enumerate(gs):
            with cols[i%4]:
                if st.button(g, key=f"b_{g}", type="primary" if st.session_state.active_group_view==g else "secondary", use_container_width=True): st.session_state.active_group_view = g; st.rerun()
        st.divider()
        cv, ce = st.columns([2, 1])
        
        with cv:
            tg = st.session_state.active_group_view
            # 修正2: 強制綁定 index 以記憶選擇，避免切換群組後跳回預設
            type_idx = 0 if st.session_state.chart_type_pref == "直方圖" else 1
            gt = st.radio("圖", ["直方圖", "折線圖"], index=type_idx, horizontal=True, key="group_chart_radio", label_visibility="collapsed")
            
            # 當使用者手動切換時，更新 session_state
            if gt != st.session_state.chart_type_pref:
                st.session_state.chart_type_pref = gt
                st.rerun()

            if tg and tg in st.session_state.saved_groups:
                st.markdown(f"### {tg}")
                gis = st.session_state.saved_groups[tg]
                gdf = pivot_df[pivot_df.index.get_level_values('顯示名稱').isin(gis)]
                if not gdf.empty:
                    gp = gdf[months].reset_index().melt(id_vars=['顯示名稱', '代碼', '名稱', '單位'], var_name='月份', value_name='數量')
                    st.altair_chart(make_interactive_chart(gp, '月份', '數量', '名稱', st.session_state.chart_type_pref, f"{tg} 趨勢"), use_container_width=True)
                    with st.expander("數據"): st.dataframe(gdf.reset_index().drop(columns=['顯示名稱', '代碼']).style.format(precision=0), hide_index=True)
                else: st.warning("無數據")
        
        with ce:
            st.markdown("<h3>➕ 新增 / ✏️ 編輯</h3>", unsafe_allow_html=True)
            
            if tg and tg in st.session_state.saved_groups:
                if st.button(f"✏️ 載入「{tg}」", key="load_edit_btn", type="secondary", use_container_width=True):
                    st.session_state.new_group_name_input = tg
                    st.session_state.new_group_items_input = st.session_state.saved_groups[tg]
                    st.rerun()
            
            nn = st.text_input("名稱", placeholder="...", key="new_group_name_input")
            ni = st.multiselect("藥品", item_options, placeholder="...", key="new_group_items_input")
            def scb():
                if st.session_state.new_group_name_input and st.session_state.new_group_items_input:
                    st.session_state.saved_groups[st.session_state.new_group_name_input] = st.session_state.new_group_items_input
                    save_groups(st.session_state.saved_groups)
                    st.toast("已儲存！"); st.session_state.active_group_view = st.session_state.new_group_name_input; st.session_state.new_group_name_input = ""; st.session_state.new_group_items_input = []
            st.button("💾 儲存", on_click=scb, type="primary", use_container_width=True)
            if tg:
                st.markdown("---")
                if st.button(f"🗑️ 刪除", type="secondary", use_container_width=True): del st.session_state.saved_groups[tg]; save_groups(st.session_state.saved_groups); st.session_state.active_group_view=None; st.rerun()

else: st.info("👋 請上傳資料 (系統會自動載入上次上傳的資料)")


