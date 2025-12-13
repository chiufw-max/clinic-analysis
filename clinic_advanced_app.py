import streamlit as st
import pandas as pd
import re
from io import BytesIO
import os
import json
import math
import altair as alt
import streamlit.components.v1 as components
from PIL import Image

# --- 1. 頁面設定 ---
st.set_page_config(page_title="歐葉豐原診所品項分析", layout="wide", page_icon="🏥")

# 顏色配置
COLORS = {
    "bg": "#000000",             
    "sidebar_bg": "#1C1C1E",     
    "main": "#0A84FF",           
    "tab_bg": "#2C2C2E",         
    "tab_hover": "#3A3A3C",      
    "text": "#FFFFFF",           
    "input_bg": "#1C1C1E",       
    "chart": ["#CD5C5C", "#DAA520", "#4682B4", "#6A5ACD", "#2E8B57", "#D2691E", "#708090", "#FF69B4", "#00CED1"] 
}

# 注入 CSS
st.markdown(f"""
    <style>
    html, body, [class*="css"] {{
        font-family: "Microsoft JhengHei", "-apple-system", sans-serif;
        font-size: 18px; 
    }}
    
    [data-testid="stSidebar"] img {{
        display: block;
        margin-left: auto;
        margin-right: auto;
    }}

    [data-testid="stFileUploaderDropzoneInstructions"] {{ display: none; }}
    section[data-testid="stFileUploader"] small {{ display: none; }}
    section[data-testid="stFileUploader"] {{ padding-top: 10px; }}

    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; background-color: transparent; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: {COLORS['tab_bg']};
        border-radius: 12px;
        padding: 10px 24px;
        color: #AEAEB2;
        border: none !important;
        font-weight: 500;
        transition: all 0.3s ease;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: {COLORS['tab_hover']};
        color: #FFFFFF;
        transform: translateY(-2px);
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {COLORS['main']} !important;
        color: #FFFFFF !important;
        font-weight: bold;
        box-shadow: 0 4px 12px rgba(10, 132, 255, 0.4);
    }}
    div[data-baseweb="tab-highlight"] {{ display: none !important; }}

    .stApp {{ background-color: {COLORS['bg']} !important; }}
    .main h1, .main h2, .main h3, .main p, .main span, .main label, .main div {{
        color: {COLORS['text']} !important;
    }}
    
    [data-testid="stSidebar"] {{
        background-color: {COLORS['sidebar_bg']};
        border-right: 1px solid #333;
    }}
    [data-testid="stSidebar"] * {{
        color: {COLORS['text']} !important;
    }}

    .stSelectbox div[data-baseweb="select"], .stTextInput input {{
        background-color: {COLORS['input_bg']} !important;
        color: white !important;
        border: 1px solid #444 !important;
        border-radius: 12px;
    }}
    ul[data-baseweb="menu"] {{ background-color: {COLORS['input_bg']} !important; }}
    ul[data-baseweb="menu"] li {{ color: white !important; }}
    span[data-baseweb="tag"] {{ background-color: #3A3A3C !important; }}
    span[data-baseweb="tag"] span {{ color: white !important; }}

    .stButton>button[kind="secondary"] {{
        background-color: {COLORS['tab_bg']} !important;
        color: #AEAEB2 !important;
        border: 1px solid #444 !important;
        border-radius: 20px;
    }}
    .stButton>button[kind="secondary"]:hover {{
        background-color: {COLORS['tab_hover']} !important;
        color: white !important;
        border-color: #666 !important;
    }}

    .stButton>button[kind="primary"] {{
        background-color: {COLORS['main']} !important;
        color: white !important;
        border: none !important;
        border-radius: 20px;
        box-shadow: 0 0 10px rgba(10, 132, 255, 0.5);
    }}
    .stButton>button[kind="primary"]:hover {{
        background-color: #007AFF !important;
    }}

    .stDataFrame {{ font-size: 18px !important; }}
    [data-testid="stDataFrame"] {{
        background-color: {COLORS['sidebar_bg']};
        border-radius: 10px;
        padding: 10px;
    }}
    
    thead tr th:first-child {{display:none}}
    tbody th {{display:none}}
    </style>
    """, unsafe_allow_html=True)

# --- ESC 鍵監聽 ---
esc_js = """
<script>
document.addEventListener('keydown', function(event) {
    if (event.key === "Escape") {
        window.parent.document.querySelector('section.main').dispatchEvent(new KeyboardEvent('keydown', {'key': 'r'}));
    }
});
</script>
"""
components.html(esc_js, height=0, width=0)

# --- 2. 檔案與群組管理邏輯 ---
CACHE_FILE = "clinic_cache.csv"
GROUPS_FILE = "clinic_groups.json"

def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_groups(groups):
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)

def parse_usage_file(file):
    try:
        stringio = file.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        stringio = file.getvalue().decode("big5", errors='ignore')
    
    lines = stringio.splitlines()
    parsed_data = []
    
    filename = file.name
    num_match = re.search(r'(\d{3,5})', filename)
    month_label = filename 
    if num_match:
        date_str = num_match.group(1)
        if len(date_str) == 5: 
            year = int(date_str[:3]) + 1911
            month = date_str[3:]
            month_label = f"{year}-{month}"
    
    for line in lines:
        s = line.strip()
        if not s or "歐葉" in s or "列印日期" in s or "=====" in s or "本頁" in s or "品名" in s:
            continue
            
        match = re.search(r'(\S+)\s+(.+)\s+(\S+)\s+([0-9\.]+)\s*$', line)
        if match:
            code = match.group(1)
            middle = match.group(2).strip()
            unit = match.group(3)
            qty_raw = float(match.group(4))
            qty = math.ceil(qty_raw) 
            
            parts = middle.split(maxsplit=1)
            if len(parts) == 2 and re.match(r'^[A-Z0-9]{8,12}$', parts[0]):
                nhi = parts[0]
                name = parts[1]
            else:
                nhi = ""
                name = middle
                
            parsed_data.append({
                '代碼': code,
                '健保碼': nhi,
                '名稱': name,
                '顯示名稱': f"{code} {name}", 
                '單位': unit,
                '數量': qty, 
                '月份': month_label
            })
    return pd.DataFrame(parsed_data)

# --- Helper: Altair Chart ---
def make_interactive_chart(data_df, x_col, y_col, color_col, chart_type, title, color_range=COLORS['chart']):
    base = alt.Chart(data_df).encode(
        x=alt.X(x_col, title=None, axis=alt.Axis(labelColor='white', labelAngle=0, domainColor='#555')),
        y=alt.Y(y_col, title=None, type='quantitative', 
                axis=alt.Axis(labelColor='white', gridColor='#333', domainColor='#555'), 
                scale=alt.Scale(nice=True, zero=True)), 
        tooltip=[
            alt.Tooltip(x_col, title='月份'),
            alt.Tooltip(color_col, title='品項'),
            alt.Tooltip(y_col, title='數量', format=',')
        ]
    ).properties(
        # 標題設定：加大字體，往下移 (offset)
        title=alt.TitleParams(text=title, color='white', fontSize=22, anchor='middle', offset=30),
        height=400
    )

    if chart_type == "直方圖" or chart_type == "直方圖 (堆疊)":
        chart = base.mark_bar().encode(
            color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None, labelColor='white'))
        )
    else: 
        line = base.mark_line(point=True, strokeWidth=4).encode(
            color=alt.Color(color_col, scale=alt.Scale(range=color_range), legend=alt.Legend(title=None, labelColor='white'))
        )
        chart = line 

    # === 加大 Padding 防止標題被切掉 ===
    return chart.configure(padding={'top': 80, 'left': 20, 'right': 20, 'bottom': 20})

# --- 側邊欄 ---
with st.sidebar:
    if os.path.exists("logo.png"):
        try:
            image = Image.open("logo.png")
            st.image(image, width=280)
        except:
            st.error("Logo 錯誤")
    else:
        st.header("🏥 歐葉豐原診所")
    
    st.markdown("---")
    st.markdown("### 📂 資料匯入")
    uploaded_files = st.file_uploader(
        "拖曳檔案至此", 
        type=['txt', 'TXT'], 
        accept_multiple_files=True
    )
    if st.button("🗑️ 清除快取資料"):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            st.rerun()

# 資料載入
main_df = pd.DataFrame()
if uploaded_files:
    all_dfs = []
    for uploaded_file in uploaded_files:
        df = parse_usage_file(uploaded_file)
        if not df.empty:
            all_dfs.append(df)
    if all_dfs:
        main_df = pd.concat(all_dfs, ignore_index=True)
        main_df.to_csv(CACHE_FILE, index=False, encoding='utf-8-sig')
elif os.path.exists(CACHE_FILE):
    main_df = pd.read_csv(CACHE_FILE)

# --- 3. 主畫面邏輯 ---
st.title("歐葉豐原診所品項分析")

if not main_df.empty:
    months = sorted(main_df['月份'].unique())
    
    pivot_df = main_df.pivot_table(
        index=['代碼', '名稱', '顯示名稱', '單位'], 
        columns='月份', 
        values='數量', 
        aggfunc='sum'
    ).fillna(0).astype(int)
    
    last_month = months[-1]
    pivot_df = pivot_df.sort_values(by=last_month, ascending=False)
    item_options = pivot_df.index.get_level_values('顯示名稱').tolist()

    if 'saved_groups' not in st.session_state:
        st.session_state.saved_groups = load_groups()
    if 'active_group_view' not in st.session_state:
        st.session_state.active_group_view = None
        
    if 'new_group_name_input' not in st.session_state:
        st.session_state.new_group_name_input = ""
    if 'new_group_items_input' not in st.session_state:
        st.session_state.new_group_items_input = []
        
    if 'chart_type_pref' not in st.session_state:
        st.session_state.chart_type_pref = "直方圖"

    tab1, tab2, tab3, tab4 = st.tabs(["📊 總表與下載", "🔍 單品分析", "⚔️ 多品比較", "📑 群組管理"])

    # === Tab 1: 總表 ===
    with tab1:
        st.markdown(f"**統計區間**：{months[0]} 至 {months[-1]} ｜ **總品項數**：{len(pivot_df)}")
        
        def convert_df(df):
            clean_df = df.reset_index().drop(columns=['顯示名稱']).set_index(['代碼', '名稱', '單位'])
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                clean_df.to_excel(writer, sheet_name='用量統計')
            return output.getvalue()
        
        st.download_button(
            label="📥 下載 Excel 報表",
            data=convert_df(pivot_df),
            file_name='clinic_report_pro.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        
        display_df = pivot_df.reset_index().drop(columns=['顯示名稱'])
        st.dataframe(
            display_df.style.background_gradient(cmap="Blues", subset=months).format(precision=0), 
            use_container_width=True,
            height=600,
            hide_index=True
        )

    # === Tab 2: 單品分析 ===
    with tab2:
        col_search, col_chart = st.columns([1, 2])
        with col_search:
            st.markdown("##### 快速搜尋 (按 ESC 清空)")
            selected_item = st.selectbox(
                "選擇藥品/耗材", 
                item_options, 
                index=None, 
                placeholder="請輸入關鍵字...",
                label_visibility="collapsed"
            )
            
            chart_type_single = st.radio("圖表類型", ["直方圖", "折線圖"], horizontal=True, key="chart_single")

            if selected_item:
                item_data = pivot_df.xs(selected_item, level='顯示名稱').iloc[0]
                values = item_data[months]
                curr_val = values.iloc[-1]
                prev_val = values.iloc[-2] if len(values) > 1 else 0
                diff = curr_val - prev_val
                
                st.metric(
                    label=f"{months[-1]} 用量",
                    value=f"{int(curr_val)}", 
                    delta=f"{int(diff)} ({diff/prev_val:.1%})" if prev_val > 0 else None
                )
        
        with col_chart:
            if selected_item:
                chart_df = pd.DataFrame({'月份': months, '數量': values.values, '名稱': selected_item.split(' ', 1)[1]})
                chart = make_interactive_chart(
                    chart_df, '月份', '數量', '名稱', 
                    chart_type_single, 
                    f"趨勢圖：{selected_item.split(' ', 1)[1]}"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("👈 請從左側選單選擇一個品項以查看圖表。")

    # === Tab 3: 多品比較 ===
    with tab3:
        st.markdown("##### ⚔️ 多品項即時比較")
        col_multi_sel, col_multi_chart = st.columns([1, 2])
        with col_multi_sel:
            multi_selected_items = st.multiselect(
                "選擇要比較的藥品 (可多選)",
                item_options,
                placeholder="搜尋並加入..."
            )
            chart_type_multi = st.radio("圖表類型", ["直方圖 (堆疊)", "折線圖 (比較)"], horizontal=True, key="chart_multi")
            
        with col_multi_chart:
            if multi_selected_items:
                group_mask = pivot_df.index.get_level_values('顯示名稱').isin(multi_selected_items)
                group_data = pivot_df[group_mask]
                plot_data = group_data[months].reset_index().melt(
                    id_vars=['顯示名稱', '代碼', '名稱', '單位'], 
                    var_name='月份', 
                    value_name='數量'
                )
                chart = make_interactive_chart(
                    plot_data, '月份', '數量', '名稱', 
                    chart_type_multi, 
                    "多品比較分析"
                )
                st.altair_chart(chart, use_container_width=True)
                with st.expander("查看比較數據"):
                     display_grp = group_data.reset_index().drop(columns=['顯示名稱', '代碼'])
                     st.dataframe(display_grp.style.format(precision=0), hide_index=True)
            else:
                st.info("請在左側選擇至少兩個品項進行比較。")

    # === Tab 4: 群組管理 ===
    with tab4:
        st.markdown("##### 📁 群組快捷區")
        
        group_names = list(st.session_state.saved_groups.keys())
        
        if not group_names:
            st.info("目前沒有儲存的群組，請在下方新增。")
        else:
            cols = st.columns(4)
            for i, g_name in enumerate(group_names):
                with cols[i % 4]:
                    btn_type = "primary" if st.session_state.active_group_view == g_name else "secondary"
                    if st.button(f"{g_name}", key=f"btn_{g_name}", type=btn_type, use_container_width=True):
                        st.session_state.active_group_view = g_name
                        st.rerun() 

        st.divider()

        col_view, col_edit = st.columns([2, 1])

        with col_view:
            target_group_name = st.session_state.active_group_view
            
            # 記憶圖表類型
            type_options = ["直方圖", "折線圖"]
            current_index = type_options.index(st.session_state.chart_type_pref)
            
            chart_type_group = st.radio(
                "圖表類型", 
                type_options, 
                index=current_index,
                horizontal=True, 
                key="chart_group_radio",
                label_visibility="collapsed"
            )
            
            if chart_type_group != st.session_state.chart_type_pref:
                st.session_state.chart_type_pref = chart_type_group
                st.rerun() 
            
            if target_group_name and target_group_name in st.session_state.saved_groups:
                st.markdown(f"### {target_group_name}")
                
                target_group_items = st.session_state.saved_groups[target_group_name]
                group_mask = pivot_df.index.get_level_values('顯示名稱').isin(target_group_items)
                group_data = pivot_df[group_mask]
                
                if not group_data.empty:
                    plot_data = group_data[months].reset_index().melt(
                        id_vars=['顯示名稱', '代碼', '名稱', '單位'], 
                        var_name='月份', 
                        value_name='數量'
                    )
                    chart = make_interactive_chart(
                        plot_data, '月份', '數量', '名稱', 
                        st.session_state.chart_type_pref, 
                        f"{target_group_name} 趨勢"
                    )
                    st.altair_chart(chart, use_container_width=True)
                    
                    with st.expander("查看詳細數據"):
                        display_grp = group_data.reset_index().drop(columns=['顯示名稱', '代碼'])
                        st.dataframe(display_grp.style.format(precision=0), hide_index=True)
                else:
                    st.warning("⚠️ 群組內的藥品在目前的檔案中找不到數據。")
            elif target_group_name:
                st.warning("群組已被刪除。")
            else:
                st.info("👈 請點擊上方按鈕查看群組圖表。")

        with col_edit:
            st.markdown("##### ➕ 新增 / ✏️ 編輯群組")
            
            if target_group_name and target_group_name in st.session_state.saved_groups:
                if st.button(f"✏️ 載入「{target_group_name}」內容", key="edit_btn", type="secondary", use_container_width=True):
                    st.session_state.new_group_name_input = target_group_name
                    st.session_state.new_group_items_input = st.session_state.saved_groups[target_group_name]
                    st.rerun()
            
            st.caption("填寫下方欄位後按儲存")
            new_group_name = st.text_input("群組名稱", placeholder="例如：三高藥物", key="new_group_name_input")
            new_group_items = st.multiselect("包含藥品", item_options, placeholder="搜尋...", key="new_group_items_input")
            
            def save_group_callback():
                if st.session_state.new_group_name_input and st.session_state.new_group_items_input:
                    st.session_state.saved_groups[st.session_state.new_group_name_input] = st.session_state.new_group_items_input
                    save_groups(st.session_state.saved_groups)
                    st.toast(f"群組「{st.session_state.new_group_name_input}」已儲存！")
                    st.session_state.active_group_view = st.session_state.new_group_name_input 
                    st.session_state.new_group_name_input = ""
                    st.session_state.new_group_items_input = []
                else:
                    st.toast("請輸入名稱並選擇藥品", icon="⚠️")

            st.button("💾 儲存 / 更新", on_click=save_group_callback, type="primary", use_container_width=True)
            
            if target_group_name:
                st.markdown("---")
                if st.button(f"🗑️ 刪除「{target_group_name}」", type="secondary", use_container_width=True):
                    del st.session_state.saved_groups[target_group_name]
                    save_groups(st.session_state.saved_groups)
                    st.session_state.active_group_view = None
                    st.rerun()

else:
    st.info("👋 歡迎使用！請從左側上傳資料開始分析。")