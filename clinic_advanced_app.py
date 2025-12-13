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

# --- 1. 頁面設定 ---
st.set_page_config(page_title="歐葉豐原診所品項分析", layout="wide", page_icon="🏥")

# 顏色配置
COLORS = {
    "bg": "#000000", "sidebar_bg": "#1C1C1E", "main": "#0A84FF",
    "tab_bg": "#2C2C2E", "tab_hover": "#3A3A3C", "text": "#FFFFFF",
    "input_bg": "#1C1C1E",
    "chart": ["#CD5C5C", "#DAA520", "#4682B4", "#6A5ACD", "#2E8B57", "#D2691E", "#708090", "#FF69B4", "#00CED1"]
}

# 注入 CSS
st.markdown(f"""
    <style>
    html, body, [class*="css"] {{ font-family: "Microsoft JhengHei", sans-serif; font-size: 18px; }}
    [data-testid="stSidebar"] img {{ display: block; margin: auto; }}
    [data-testid="stFileUploaderDropzoneInstructions"], section[data-testid="stFileUploader"] small {{ display: none; }}
    section[data-testid="stFileUploader"] {{ padding-top: 10px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; background-color: transparent; }}
    .stTabs [data-baseweb="tab"] {{ background-color: {COLORS['tab_bg']}; border-radius: 12px; color: #AEAEB2; border: none !important; }}
    .stTabs [aria-selected="true"] {{ background-color: {COLORS['main']} !important; color: white !important; }}
    div[data-baseweb="tab-highlight"] {{ display: none !important; }}
    .stApp {{ background-color: {COLORS['bg']} !important; }}
    .main h1, .main h2, .main h3, .main p, .main span, .main label, .main div, [data-testid="stSidebar"] * {{ color: {COLORS['text']} !important; }}
    [data-testid="stSidebar"] {{ background-color: {COLORS['sidebar_bg']}; border-right: 1px solid #333; }}
    .stSelectbox div[data-baseweb="select"], .stTextInput input {{ background-color: {COLORS['input_bg']} !important; color: white !important; border-radius: 12px; }}
    ul[data-baseweb="menu"] {{ background-color: {COLORS['input_bg']} !important; }}
    ul[data-baseweb="menu"] li {{ color: white !important; }}
    span[data-baseweb="tag"] {{ background-color: #3A3A3C !important; }}
    span[data-baseweb="tag"] span {{ color: white !important; }}
    .stButton>button {{ border-radius: 20px; border: none; }}
    .stButton>button[kind="secondary"] {{ background-color: {COLORS['tab_bg']} !important; color: #AEAEB2 !important; }}
    .stButton>button[kind="primary"] {{ background-color: {COLORS['main']} !important; color: white !important; }}
    .stDataFrame {{ font-size: 18px !important; }}
    [data-testid="stDataFrame"] {{ background-color: {COLORS['sidebar_bg']}; border-radius: 10px; padding: 10px; }}
    thead tr th:first-child, tbody th {{ display: none; }}
    </style>
    """, unsafe_allow_html=True)

# --- Google Drive 連線邏輯 ---
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

def log_access_to_drive(email, action="Login"):
    """記錄使用者登入資訊到 Google Drive"""
    service = get_drive_service()
    if not service: return 
    
    tw_time = datetime.utcnow() + timedelta(hours=8)
    time_str = tw_time.strftime("%Y-%m-%d %H:%M:%S")
    
    new_entry = pd.DataFrame([{'Time': time_str, 'User': email, 'Action': action}])
    
    try:
        results = service.files().list(q=f"name='{LOG_FILE_NAME}' and trashed=false", fields="files(id, name)").execute()
        items = results.get('files', [])
        
        final_df = new_entry
        file_id = None
        
        if items:
            file_id = items[0]['id']
            content = service.files().get_media(fileId=file_id).execute().decode('utf-8')
            old_df = pd.read_csv(StringIO(content))
            final_df = pd.concat([old_df, new_entry], ignore_index=True)
        
        media = MediaIoBaseUpload(BytesIO(final_df.to_csv(index=False).encode('utf-8')), mimetype='text/csv')
        
        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {'name': LOG_FILE_NAME}
            service.files().create(body=file_metadata, media_body=media).execute()
    except Exception as e:
        print(f"Log Error: {e}")

# --- 安全抓取 Email 的函數 (修復錯誤的核心) ---
def get_current_user_email():
    """嘗試多種方式抓取使用者 Email，失敗則回傳 Local User"""
    try:
        # 方法 1: 新版 Streamlit Context (v1.39+)
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            email = st.context.headers.get("X-Streamlit-User-Email")
            if email: return email
    except: pass
    
    try:
        # 方法 2: 舊版 Experimental User
        if hasattr(st, "experimental_user") and hasattr(st.experimental_user, "email"):
            return st.experimental_user.email
    except: pass

    # 方法 3: 回傳預設值
    return "Local User"

# --- 🔐 登入驗證與記錄 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

if not st.session_state.password_correct:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"): st.image(Image.open("logo.png"), width=200)
        st.title("🔒 診所系統登入")
        
        # 使用修復後的函數抓取 Email
        user_email = get_current_user_email()
        
        st.info(f"您目前的身份：{user_email}")
        
        pwd = st.text_input("請輸入密碼", type="password")
        if st.button("登入系統", type="primary", use_container_width=True):
            if pwd == "8888":
                st.session_state.password_correct = True
                log_access_to_drive(user_email, "Login Success")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
                log_access_to_drive(user_email, "Login Failed (Wrong Password)")
    st.stop()

# --- (以下為系統主邏輯) ---

def load_groups():
    service = get_drive_service()
    if service:
        try:
            results = service.files().list(q=f"name='{GROUPS_FILE_NAME}' and trashed=false", fields="files(id, name)").execute()
            items = results.get('files', [])
            if items:
                content = service.files().get_media(fileId=items[0]['id']).execute()
                return json.loads(content.decode('utf-8'))
        except: pass
    if os.path.exists(GROUPS_FILE_NAME):
        with open(GROUPS_FILE_NAME, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_groups(groups):
    with open(GROUPS_FILE_NAME, "w", encoding="utf-8") as f: json.dump(groups, f, ensure_ascii=False, indent=2)
    service = get_drive_service()
    if service:
        try:
            media = MediaIoBaseUpload(BytesIO(json.dumps(groups, ensure_ascii=False).encode('utf-8')), mimetype='application/json')
            results = service.files().list(q=f"name='{GROUPS_FILE_NAME}' and trashed=false", fields="files(id, name)").execute()
            items = results.get('files', [])
            if items: service.files().update(fileId=items[0]['id'], media_body=media).execute()
            else: service.files().create(body={'name': GROUPS_FILE_NAME}, media_body=media).execute()
        except: pass

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

def make_interactive_chart(data_df, x_col, y_col, color_col, chart_type, title, color_range=COLORS['chart']):
    base = alt.Chart(data_df).encode(
        x=alt.X(x_col, title=None, axis=alt.Axis(labelColor='white', labelAngle=0, domainColor='#555')),
        y=alt.Y(y_col, title=None, type='quantitative', axis=alt.Axis(labelColor='white', gridColor='#333', domainColor='#555'), scale=alt.Scale(nice=True, zero=True)),
        tooltip=[alt.Tooltip(x_col, title='月份'), alt.Tooltip(color_col, title='品項'), alt.Tooltip(y_col, title='數量', format=',')]
    ).properties(title=alt.TitleParams(text=title, color='white', fontSize=22, anchor='middle', offset=30), height=400)
    if "直方圖" in chart_type: chart = base.mark_bar().encode(color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None, labelColor='white')))
    else: chart = base.mark_line(point=True, strokeWidth=4).encode(color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None, labelColor='white')))
    return chart.configure(padding={'top': 80, 'left': 20, 'right': 20, 'bottom': 20})

with st.sidebar:
    if os.path.exists("logo.png"): st.image(Image.open("logo.png"), width=280)
    else: st.header("🏥 歐葉豐原診所")
    st.markdown("---")
    if "gcp_service_account" in st.secrets: st.success("🟢 已連線至雲端硬碟")
    else: st.info("⚪ 本機模式")
    uploaded_files = st.file_uploader("拖曳檔案至此", type=['txt', 'TXT'], accept_multiple_files=True)
    if st.button("🗑️ 清除快取"): 
        if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
        st.rerun()

main_df = pd.DataFrame()
if uploaded_files:
    all_dfs = [parse_usage_file(f) for f in uploaded_files if not parse_usage_file(f).empty]
    if all_dfs: main_df = pd.concat(all_dfs, ignore_index=True); main_df.to_csv(CACHE_FILE, index=False, encoding='utf-8-sig')
elif os.path.exists(CACHE_FILE): main_df = pd.read_csv(CACHE_FILE)

st.title("歐葉豐原診所品項分析")
if not main_df.empty:
    months = sorted(main_df['月份'].unique())
    pivot_df = main_df.pivot_table(index=['代碼', '名稱', '顯示名稱', '單位'], columns='月份', values='數量', aggfunc='sum').fillna(0).astype(int)
    last_month = months[-1]
    pivot_df = pivot_df.sort_values(by=last_month, ascending=False)
    item_options = pivot_df.index.get_level_values('顯示名稱').tolist()

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
            gt = st.radio("圖", ["直方圖", "折線圖"], horizontal=True, key="gr", label_visibility="collapsed")
            if gt!=st.session_state.chart_type_pref: st.session_state.chart_type_pref=gt; st.rerun()
            if tg and tg in st.session_state.saved_groups:
                c1, c2 = st.columns([3, 1])
                with c1: st.markdown(f"### {tg}")
                with c2:
                    if st.button("✏️ 編輯", key="eb", type="secondary"): st.session_state.new_group_name_input=tg; st.session_state.new_group_items_input=st.session_state.saved_groups[tg]; st.rerun()
                gis = st.session_state.saved_groups[tg]
                gdf = pivot_df[pivot_df.index.get_level_values('顯示名稱').isin(gis)]
                if not gdf.empty:
                    gp = gdf[months].reset_index().melt(id_vars=['顯示名稱', '代碼', '名稱', '單位'], var_name='月份', value_name='數量')
                    st.altair_chart(make_interactive_chart(gp, '月份', '數量', '名稱', st.session_state.chart_type_pref, f"{tgt} 趨勢"), use_container_width=True)
                    with st.expander("數據"): st.dataframe(gdf.reset_index().drop(columns=['顯示名稱', '代碼']).style.format(precision=0), hide_index=True)
                else: st.warning("無數據")
        with ce:
            st.markdown("##### ➕ / ✏️")
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

else: st.info("👋 請上傳資料")
