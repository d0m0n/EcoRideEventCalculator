import streamlit as st
import pandas as pd
import plotly.express as px
import math
import uuid
import requests
import re
from streamlit_gsheets import GSheetsConnection

# --- 設定・定数 ---
CO2_EMISSION_FACTORS = {
    "ガソリン車 (普通) | 14km/L": 166,
    "ガソリン車 (大型・ミニバン) | 9km/L": 258,
    "軽自動車 | 16km/L": 145,
    "ディーゼル車 | 13km/L": 198,
    "ハイブリッド車 | 22km/L": 105,
    "電気自動車 (EV) | 走行時ゼロ": 0,
}

MAX_CAPACITY = {
    "ガソリン車 (普通) | 14km/L": 5,
    "ガソリン車 (大型・ミニバン) | 9km/L": 8,
    "軽自動車 | 16km/L": 4,
    "ディーゼル車 | 13km/L": 5,
    "ハイブリッド車 | 22km/L": 5,
    "電気自動車 (EV) | 走行時ゼロ": 5,
}

# ページ設定
st.set_page_config(page_title="イベント相乗りCO2削減シミュレーター", layout="wide")

# --- SVG アイコン定義（Feather Icons ベース） ---
def _icon(inner, size=28, color="currentColor"):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
    )

_P_CALENDAR = (
    '<rect x="3" y="4" width="18" height="18" rx="2"/>'
    '<line x1="16" y1="2" x2="16" y2="6"/>'
    '<line x1="8" y1="2" x2="8" y2="6"/>'
    '<line x1="3" y1="10" x2="21" y2="10"/>'
)
_P_CAR = (
    '<path d="M3 17h1M17 17h3a2 2 0 0 0 2-2v-3l-2.5-5H3.5L1 12v3a2 2 0 0 0 2 2z"/>'
    '<circle cx="6.5" cy="17" r="2"/>'
    '<circle cx="16.5" cy="17" r="2"/>'
    '<line x1="8.5" y1="17" x2="14.5" y2="17"/>'
)
_P_LEAF = (
    '<path d="M17 8C8 10 5.9 16.17 3.82 19.5"/>'
    '<path d="M3.82 19.5C6.1 17 9 15 12 13.5c2.5-1 3.5-3 1.5-5.5"/>'
    '<path d="M17 8c0 0-1.5 4-5 5.5"/>'
)
_P_TREE = (
    '<polygon points="12 2 22 20 2 20"/>'
    '<line x1="12" y1="20" x2="12" y2="22"/>'
)
_P_PARKING = (
    '<rect x="3" y="3" width="18" height="18" rx="2"/>'
    '<path d="M9 17V7h4.5a3.5 3.5 0 0 1 0 7H9"/>'
)


# --- UI ヘルパー関数 ---

def inject_css():
    st.markdown("""
    <style>
    /* ===== アニメーション定義 ===== */
    @keyframes fadeSlideUp {
        from { opacity: 0; transform: translateY(20px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes heroFadeIn {
        from { opacity: 0; transform: scale(0.97); }
        to   { opacity: 1; transform: scale(1); }
    }
    @keyframes pulseLive {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.3; }
    }

    /* ===== グローバル ===== */
    * { box-sizing: border-box; }

    /* ダークモード含め背景を強制上書き */
    html,
    body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMain"] > div,
    .main,
    .main > div {
        background: linear-gradient(160deg, #EFF6EF 0%, #F5F9F5 50%, #EEF4EE 100%) !important;
    }

    /* トップナビバーの背景 */
    [data-testid="stHeader"] {
        background: rgba(239, 246, 239, 0.92) !important;
        backdrop-filter: blur(8px) !important;
        border-bottom: 1px solid #C8E6C9 !important;
    }

    /* ===== メインコンテンツ余白 ===== */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1100px !important;
    }

    /* ===== サイドバー ===== */
    [data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 3px solid #C8E6C9 !important;
        box-shadow: 2px 0 12px rgba(46,125,50,0.08) !important;
    }

    /* ===== ボタン ===== */
    .stButton > button {
        background: linear-gradient(135deg, #2E7D32 0%, #43A047 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 3px 10px rgba(46,125,50,0.25) !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(46,125,50,0.38) !important;
        background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%) !important;
    }
    .stButton > button:active { transform: translateY(0) !important; }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #B71C1C 0%, #E53935 100%) !important;
        box-shadow: 0 3px 10px rgba(183,28,28,0.25) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #7F0000 0%, #B71C1C 100%) !important;
        box-shadow: 0 6px 20px rgba(183,28,28,0.38) !important;
    }

    /* ===== フォーム送信ボタン ===== */
    [data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, #2E7D32 0%, #43A047 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 3px 10px rgba(46,125,50,0.25) !important;
        width: 100% !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(46,125,50,0.38) !important;
    }

    /* ===== 入力フィールド ===== */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div {
        border-radius: 8px !important;
        border: 1.5px solid #C8E6C9 !important;
        background: #FAFFFE !important;
        color: #1A2B1A !important;
        transition: border-color 0.2s, box-shadow 0.2s !important;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        border-color: #43A047 !important;
        box-shadow: 0 0 0 3px rgba(67,160,71,0.15) !important;
    }

    /* ===== タブ ===== */
    .stTabs [data-baseweb="tab-list"] {
        background: #FFFFFF !important;
        border-radius: 12px !important;
        padding: 4px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
        gap: 4px !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.2rem !important;
        color: #2A3A2A !important;
        transition: all 0.2s ease !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2E7D32 0%, #43A047 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 3px 10px rgba(46,125,50,0.3) !important;
    }

    /* ===== エクスパンダー ===== */
    [data-testid="stExpander"] {
        background: #FFFFFF !important;
        border-radius: 12px !important;
        border: 1px solid #E8F5E9 !important;
        box-shadow: 0 2px 8px rgba(46,125,50,0.08) !important;
        margin-bottom: 0.75rem !important;
        overflow: hidden !important;
        transition: box-shadow 0.25s ease !important;
    }
    [data-testid="stExpander"]:hover {
        box-shadow: 0 6px 18px rgba(46,125,50,0.15) !important;
    }

    /* ===== コンテナ(border=True) ===== */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background: #FFFFFF !important;
        border-radius: 14px !important;
        border: 2px solid #A5D6A7 !important;
        border-left: 6px solid #43A047 !important;
        box-shadow: 0 4px 16px rgba(46,125,50,0.13) !important;
        margin-bottom: 1.1rem !important;
        transition: box-shadow 0.25s ease, transform 0.25s ease, border-left-color 0.2s ease !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] > div:hover {
        box-shadow: 0 10px 28px rgba(46,125,50,0.2) !important;
        transform: translateY(-3px) !important;
        border-left-color: #2E7D32 !important;
    }

    /* ===== Streamlit デフォルト metric ===== */
    [data-testid="stMetric"] {
        background: #FFFFFF !important;
        border-radius: 14px !important;
        padding: 1.2rem 1.4rem !important;
        box-shadow: 0 3px 12px rgba(46,125,50,0.1) !important;
        border: 1px solid #E8F5E9 !important;
        animation: fadeSlideUp 0.5s ease forwards !important;
        transition: box-shadow 0.25s, transform 0.25s !important;
    }
    [data-testid="stMetric"]:hover {
        box-shadow: 0 8px 24px rgba(46,125,50,0.18) !important;
        transform: translateY(-3px) !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #2E7D32 !important;
    }
    [data-testid="stMetricLabel"] {
        font-weight: 500 !important;
        color: #5C6B5C !important;
    }

    /* ===== データフレーム ===== */
    [data-testid="stDataFrame"] {
        border-radius: 12px !important;
        overflow: hidden !important;
        box-shadow: 0 2px 10px rgba(46,125,50,0.08) !important;
        border: 1px solid #E8F5E9 !important;
    }

    /* ===== リンクボタン ===== */
    .stLinkButton > a {
        background: linear-gradient(135deg, #2E7D32 0%, #43A047 100%) !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        border: none !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important;
        box-shadow: 0 3px 10px rgba(46,125,50,0.25) !important;
        transition: all 0.25s ease !important;
    }
    .stLinkButton > a:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(46,125,50,0.38) !important;
    }

    /* ===== info / success / warning ===== */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: none !important;
        font-weight: 500 !important;
    }

    /* ===== カスタムコンポーネント ===== */
    .hero-header {
        background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 50%, #43A047 100%);
        border-radius: 18px;
        padding: 2.2rem 2.5rem 1.8rem;
        color: white;
        margin-bottom: 1.8rem;
        animation: heroFadeIn 0.6s ease both;
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        gap: 1.4rem;
    }
    .hero-header::before {
        content: '';
        position: absolute;
        top: -40%; right: -10%;
        width: 350px; height: 350px;
        border-radius: 50%;
        background: rgba(255,255,255,0.06);
        pointer-events: none;
    }
    .hero-icon-wrap {
        flex-shrink: 0;
        width: 56px; height: 56px;
        background: rgba(255,255,255,0.15);
        border-radius: 14px;
        display: flex; align-items: center; justify-content: center;
    }
    .hero-text { flex: 1; }
    .hero-title {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        margin: 0 0 0.3rem !important;
        color: white !important;
        line-height: 1.3 !important;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: rgba(255,255,255,0.82) !important;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .metric-cards-row {
        display: flex;
        gap: 1rem;
        margin: 1.2rem 0;
    }
    .metric-card {
        flex: 1;
        background: #FFFFFF;
        border-radius: 16px;
        padding: 1.4rem 1.2rem;
        box-shadow: 0 4px 16px rgba(46,125,50,0.1);
        border: 1px solid #E8F5E9;
        text-align: center;
        animation: fadeSlideUp 0.5s ease both;
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        cursor: default;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(46,125,50,0.18);
    }
    .metric-card:nth-child(2) { animation-delay: 0.1s; }
    .metric-card:nth-child(3) { animation-delay: 0.2s; }
    .metric-card-icon {
        margin-bottom: 0.6rem;
        display: flex;
        justify-content: center;
    }
    .metric-card-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #2E7D32;
        line-height: 1.2;
        margin-bottom: 0.3rem;
    }
    .metric-card-label {
        font-size: 0.8rem;
        color: #5C6B5C;
        font-weight: 500;
    }

    .live-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #FFEBEE;
        color: #C62828;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
        letter-spacing: 0.05em;
        margin-left: 10px;
        vertical-align: middle;
    }
    .live-dot {
        width: 8px; height: 8px;
        background: #E53935;
        border-radius: 50%;
        display: inline-block;
        animation: pulseLive 1.2s ease-in-out infinite;
    }
    .live-monitor-header {
        display: flex;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    .live-monitor-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1A2B1A;
        margin: 0;
    }

    .section-divider {
        border: none;
        border-top: 2px solid #E8F5E9;
        margin: 1.5rem 0;
    }

    .event-card-url {
        font-size: 0.8rem;
        color: #7B9E7B;
        word-break: break-all;
        background: #F1F8F1;
        padding: 0.4rem 0.7rem;
        border-radius: 7px;
        font-family: monospace;
    }

    /* ===== テキスト色（ダークモード対応） ===== */
    .stApp { color: #1A2B1A !important; }
    h1, h2, h3, h4, h5, h6 { color: #1A2B1A !important; }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] em,
    [data-testid="stMarkdownContainer"] span {
        color: #1A2B1A !important;
    }
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #1A2B1A !important;
    }
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        color: #1A2B1A !important;
    }
    .stTextInput label, .stNumberInput label, .stSelectbox label,
    .stDateInput label, .stRadio label, .stRadio p {
        color: #2A3A2A !important;
        font-weight: 500 !important;
    }
    .stSelectbox [data-baseweb="select"] div,
    .stSelectbox [data-baseweb="select"] span,
    .stSelectbox [data-baseweb="select"] input { color: #1A2B1A !important; }
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] p,
    [data-testid="stRadio"] span { color: #1A2B1A !important; }
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p { color: #1A2B1A !important; }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p { color: #4A5A4A !important; }
    [data-testid="stTable"] th,
    [data-testid="stTable"] td,
    [data-testid="stTable"] p { color: #1A2B1A !important; }
    [data-testid="stMetricLabel"] p,
    [data-testid="stMetricLabel"] span { color: #4A5A4A !important; }

    /* spinner */
    .stSpinner > div { border-top-color: #43A047 !important; }

    /* ===== ダーク背景エリアは白文字（最後に記述して優先） ===== */
    .hero-header, .hero-header p, .hero-header h1, .hero-header h2,
    .hero-header h3, .hero-header span, .hero-header div {
        color: white !important;
    }
    .stButton > button, .stButton > button span, .stButton > button p,
    .stButton > button * { color: #FFFFFF !important; }
    [data-testid="stFormSubmitButton"] > button,
    [data-testid="stFormSubmitButton"] > button span,
    [data-testid="stFormSubmitButton"] > button p,
    [data-testid="stFormSubmitButton"] > button * { color: #FFFFFF !important; }
    /* エクスパンダー内ボタン: 詳細度を上げて確実に上書き */
    [data-testid="stExpander"] [data-testid="stFormSubmitButton"] > button,
    [data-testid="stExpander"] [data-testid="stFormSubmitButton"] > button span,
    [data-testid="stExpander"] [data-testid="stFormSubmitButton"] > button p,
    [data-testid="stExpander"] [data-testid="stFormSubmitButton"] > button * { color: #FFFFFF !important; }
    [data-testid="stExpander"] .stButton > button,
    [data-testid="stExpander"] .stButton > button * { color: #FFFFFF !important; }
    /* フォーム内ボタン全般（kind 属性ベース） */
    button[kind="secondaryFormSubmit"],
    button[kind="secondaryFormSubmit"] *,
    button[kind="primaryFormSubmit"],
    button[kind="primaryFormSubmit"] * { color: #FFFFFF !important; }
    .stLinkButton > a, .stLinkButton > a span, .stLinkButton > a p { color: #FFFFFF !important; }
    .stTabs [aria-selected="true"],
    .stTabs [aria-selected="true"] span,
    .stTabs [aria-selected="true"] p { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)


def render_hero_header(icon_svg: str, title: str, subtitle: str) -> None:
    st.markdown(f"""
    <div class="hero-header">
        <div class="hero-icon-wrap">{icon_svg}</div>
        <div class="hero-text">
            <h1 class="hero-title">{title}</h1>
            <p class="hero-subtitle">{subtitle}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_metric_cards(cards: list[dict]) -> None:
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        with col:
            st.markdown(f"""
<div class="metric-card">
<div class="metric-card-icon">{c['icon']}</div>
<div class="metric-card-value">{c['value']}</div>
<div class="metric-card-label">{c['label']}</div>
</div>
""", unsafe_allow_html=True)


# --- 関数群 ---

def get_city_level_address(address):
    if not isinstance(address, str):
        return str(address)
    clean_addr = re.sub(r'日本、\s*〒\d{3}-\d{4}\s*', '', address)
    match = re.search(r'(.+?[都道府県])(.+?[市区町村])', clean_addr)
    if match:
        return match.group(0)
    return clean_addr

def get_place_suggestions(query, api_key):
    if not query: return []
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {"input": query, "key": api_key, "language": "ja", "components": "country:jp"}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            return [{"label": p["description"], "value": p["description"]} for p in data["predictions"]]
    except Exception as e:
        st.error(f"場所検索エラー: {e}")
    return []

def get_distance(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {"origins": origin, "destinations": destination, "key": api_key, "language": "ja"}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            rows = data.get("rows", [])
            if rows and rows[0].get("elements"):
                elm = rows[0]["elements"][0]
                if elm.get("status") == "OK":
                    return elm["distance"]["value"] / 1000.0
    except Exception as e:
        st.error(f"距離計算エラー: {e}")
    return None

def load_sheet(worksheet_name):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        return conn.read(worksheet=worksheet_name, ttl=0)
    except:
        return pd.DataFrame()

def append_to_sheet(worksheet_name, new_data_dict):
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_sheet(worksheet_name)
    new_df = pd.DataFrame([new_data_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True)
    conn.update(worksheet=worksheet_name, data=updated_df)

def update_sheet_data(worksheet_name, df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(worksheet=worksheet_name, data=df)

def calculate_stats(df_participants, current_event_id):
    if df_participants.empty or "event_id" not in df_participants.columns:
        return None, None, 0, 0, pd.DataFrame()

    df_participants["event_id"] = df_participants["event_id"].astype(str)
    if 'original_index' not in df_participants.columns:
        df_participants['original_index'] = df_participants.index

    df_p = df_participants[df_participants["event_id"] == str(current_event_id)].copy()
    if df_p.empty: return 0, 0, 0, 0, df_p

    total_solo, total_share, total_actual_cars, total_people = 0, 0, 0, 0

    for index, row in df_p.iterrows():
        c_type = row.get('car_type', "")
        if c_type in CO2_EMISSION_FACTORS:
            factor = CO2_EMISSION_FACTORS[c_type]
            capacity = MAX_CAPACITY[c_type]
        else:
            factor = 166
            capacity = 5
        try:
            dist = float(row['distance'])
            ppl = int(row['people'])
            cars = math.ceil(ppl / capacity)
            total_solo += ppl * dist * factor * 2
            total_share += cars * dist * factor * 2
            total_actual_cars += cars
            total_people += ppl
        except:
            continue

    return total_solo, total_share, total_actual_cars, total_people, df_p

def split_car_info(car_str):
    if not isinstance(car_str, str):
        return str(car_str), "-"
    if "|" in car_str:
        parts = car_str.split("|")
        return parts[0].strip(), parts[1].strip()
    match = re.search(r'(.+?)[\s\（\(]+(.+?km/L)[\)\）]', car_str)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return car_str, "-"

def make_plotly_fig(chart_data):
    fig = px.bar(
        chart_data,
        x="シナリオ",
        y="CO2排出量 (kg)",
        color="シナリオ",
        color_discrete_sequence=["#EF5350", "#66BB6A"],
        text="CO2排出量 (kg)",
        template="plotly_white",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        yaxis=dict(showgrid=True, gridcolor='rgba(200,230,201,0.6)', gridwidth=1),
        xaxis=dict(showgrid=False),
        font=dict(size=15, color="#1A2B1A"),
        margin=dict(t=20, b=10, l=10, r=10),
        bargap=0.35,
    )
    fig.update_traces(
        texttemplate='<b>%{y:.1f} kg</b>',
        textposition='inside',
        textfont=dict(size=32, color='white'),
        marker=dict(line=dict(width=0), cornerradius=8),
    )
    return fig


# --- ライブモニター用フラグメント ---
@st.fragment(run_every=10)
def show_live_monitor(current_event_id):
    st.markdown("""
    <div class="live-monitor-header">
        <p class="live-monitor-title">リアルタイム集計モニター</p>
        <span class="live-badge"><span class="live-dot"></span>LIVE 10秒更新</span>
    </div>
    """, unsafe_allow_html=True)
    st.caption("この画面は自動で最新情報に更新されます。")

    all_p = load_sheet("participants")
    total_solo, total_share, actual_cars, total_people, df_p = calculate_stats(all_p, current_event_id)

    if df_p.empty:
        st.info("現在、参加者は登録されていません。待機中...")
        return

    reduction_kg = (total_solo - total_share) / 1000
    occupancy_rate = total_people / actual_cars if actual_cars > 0 else 0
    cedar_trees = reduction_kg / 14

    render_metric_cards([
        {"icon": _icon(_P_LEAF,  36, "#2E7D32"), "value": f"{reduction_kg:.2f} kg-CO₂", "label": "みんなの総CO2削減量"},
        {"icon": _icon(_P_CAR,   36, "#2E7D32"), "value": f"{occupancy_rate:.2f} 人/台",  "label": "平均相乗り率"},
        {"icon": _icon(_P_TREE,  36, "#2E7D32"), "value": f"約 {cedar_trees:.1f} 本",      "label": "杉の木の年間吸収量相当"},
    ])

    chart_data = pd.DataFrame({
        "シナリオ": ["全員ソロ移動", "相乗り移動"],
        "CO2排出量 (kg)": [total_solo/1000, total_share/1000]
    })
    st.plotly_chart(make_plotly_fig(chart_data), use_container_width=True)

    st.markdown("#### 最新の参加者リスト")
    display_df = df_p[["name", "start_point", "people", "car_type", "distance"]].copy()
    display_df["start_point"] = display_df["start_point"].apply(get_city_level_address)
    split_data = display_df["car_type"].apply(split_car_info)
    display_df["car_name"] = [x[0] for x in split_data]
    display_df["car_eff"]  = [x[1] for x in split_data]
    display_df = display_df[["name", "start_point", "people", "car_name", "car_eff", "distance"]]
    display_df.columns = ["グループ名", "出発地(市町村)", "人数", "車種", "燃費目安", "距離(km)"]
    st.dataframe(display_df.iloc[::-1], width="stretch", hide_index=True)


# --- メイン処理 ---

inject_css()

query_params = st.query_params
current_event_id = query_params.get("event_id", None)

try:
    MAPS_API_KEY = st.secrets["general"]["google_maps_api_key"]
except KeyError:
    st.error("SecretsにGoogle Maps APIキーが設定されていません。")
    st.stop()

# ==========================================
# モードA: 主催者用画面
# ==========================================
if not current_event_id:
    render_hero_header(
        _icon(_P_CALENDAR, 32, "white"),
        "イベント作成・管理パネル",
        "イベントを作成して参加者に招待URLを共有しましょう",
    )
    tab1, tab2 = st.tabs(["新規イベント作成", "作成済みイベントの管理"])

    with tab1:
        with st.form("create_event"):
            st.subheader("新規イベント作成")
            e_name = st.text_input("イベント名", placeholder="例：〇〇音楽フェス 2025")
            e_date = st.date_input("開催日")
            col1, col2 = st.columns(2)
            with col1: e_loc_name = st.text_input("開催場所名")
            with col2: e_loc_addr = st.text_input("開催場所の住所")
            if st.form_submit_button("イベントを作成"):
                if e_name and e_loc_name and e_loc_addr:
                    new_id = str(uuid.uuid4())[:8]
                    append_to_sheet("events", {
                        "event_id": new_id, "event_name": e_name, "event_date": str(e_date),
                        "location_name": e_loc_name, "location_address": e_loc_addr
                    })
                    st.success("作成しました！")
                    st.rerun()
                else:
                    st.warning("全項目入力してください。")

    with tab2:
        st.subheader("作成済みイベント一覧")
        events_df = load_sheet("events")
        if not events_df.empty and "location_name" in events_df.columns:
            for index, row in events_df[::-1].iterrows():
                base_url = "https://ecorideeventcalculator-2vhvzkr7oenknbuegaremc.streamlit.app/"
                invite_url = f"{base_url}?event_id={row['event_id']}"
                with st.container(border=True):
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"### {row['event_name']}")
                        st.caption(f"{row['event_date']}  |  {row['location_name']}")
                        st.markdown(
                            f'<div class="event-card-url">{invite_url}</div>',
                            unsafe_allow_html=True,
                        )
                    with col_btn:
                        st.link_button("参加者画面へ", invite_url, use_container_width=True)

                    with st.expander("編集・削除"):
                        with st.form(f"edit_{row['event_id']}"):
                            col_l, col_r = st.columns(2)
                            with col_l:
                                n_name = st.text_input("イベント名", value=row['event_name'])
                                n_loc  = st.text_input("開催場所名", value=row['location_name'])
                            with col_r:
                                n_addr = st.text_input("開催場所の住所", value=row['location_address'])
                                n_date = st.text_input("開催日", value=row['event_date'])
                            st.markdown("---")
                            c_up, c_del = st.columns(2)
                            if c_up.form_submit_button("更新する", use_container_width=True):
                                events_df.at[index, 'event_name'] = n_name
                                events_df.at[index, 'location_name'] = n_loc
                                events_df.at[index, 'location_address'] = n_addr
                                events_df.at[index, 'event_date'] = n_date
                                update_sheet_data("events", events_df)
                                st.rerun()
                            if c_del.form_submit_button("削除する", type="primary", use_container_width=True):
                                events_df = events_df.drop(index)
                                update_sheet_data("events", events_df)
                                st.rerun()
        else:
            st.info("イベントなし")

# ==========================================
# モードB: 参加者・集計画面
# ==========================================
else:
    events_df = load_sheet("events")
    events_df["event_id"] = events_df["event_id"].astype(str)
    target_event = events_df[events_df["event_id"] == str(current_event_id)]

    if target_event.empty:
        st.error("イベントが見つかりません。")
        if st.button("トップへ"):
            st.query_params.clear()
            st.rerun()
    else:
        event_data = target_event.iloc[0]
        loc_name = event_data.get('location_name', event_data.get('location'))
        loc_addr = event_data.get('location_address', loc_name)

        render_hero_header(
            _icon(_P_CAR, 32, "white"),
            event_data['event_name'],
            f"{event_data['event_date']}  |  {loc_name}",
        )

        with st.expander("CO2排出量の計算式・根拠データ（出典）"):
            st.markdown("""
            本アプリでは、**環境省「算定・報告・公表制度」** の排出係数を基に、一般的な実燃費を想定して算出しています。
            $$ \\text{1km排出量} = \\frac{\\text{燃料排出係数 (g/L)}}{\\text{想定燃費 (km/L)}} $$
            """)
            data_items = [{"車種設定": k, "設定排出係数": v} for k, v in CO2_EMISSION_FACTORS.items()]
            st.table(pd.DataFrame(data_items))
            st.caption("出典: [環境省_算定方法・排出係数一覧](https://policies.env.go.jp/earth/ghg-santeikohyo/calc.html)")

        st.sidebar.title("メニュー")
        app_mode = st.sidebar.radio("モード選択", ["参加登録・編集", "ライブモニター"], index=0)

        if app_mode == "ライブモニター":
            show_live_monitor(str(current_event_id))

        else:
            st.markdown("### 参加登録・編集モード")

            st.sidebar.markdown("---")
            st.sidebar.header("新規登録")
            st.sidebar.markdown("##### 1. 出発地を検索")
            search_query = st.sidebar.text_input("地名/駅名", key="search_box")
            selected_address = None
            if search_query:
                suggestions = get_place_suggestions(search_query, MAPS_API_KEY)
                if suggestions:
                    options = [s["label"] for s in suggestions]
                    selected_address = st.sidebar.selectbox("候補を選択", options)
                else:
                    st.sidebar.warning("候補なし")

            st.sidebar.markdown("##### 2. 詳細登録")
            with st.sidebar.form("join_form"):
                start_val = selected_address if selected_address else ""
                f_start = st.text_input("出発地(確定)", value=start_val)
                f_name = st.text_input("名前/グループ名")
                f_ppl = st.number_input("人数", 1, 10, 2)
                f_car = st.selectbox("車種", list(CO2_EMISSION_FACTORS.keys()))
                if st.form_submit_button("登録"):
                    if f_start:
                        with st.spinner("計算中..."):
                            dist = get_distance(f_start, loc_addr, MAPS_API_KEY)
                        if dist:
                            append_to_sheet("participants", {
                                "event_id": str(current_event_id), "name": f_name,
                                "start_point": f_start, "distance": dist,
                                "people": f_ppl, "car_type": f_car
                            })
                            st.success("登録しました！")
                            st.rerun()
                        else:
                            st.error("場所不明")
                    else:
                        st.error("出発地を入力してください")

            all_p = load_sheet("participants")
            total_solo, total_share, actual_cars, total_people, df_p = calculate_stats(all_p, current_event_id)

            if not df_p.empty:
                st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

                reduction_kg = (total_solo - total_share) / 1000
                occupancy_rate = total_people / actual_cars if actual_cars > 0 else 0

                render_metric_cards([
                    {"icon": _icon(_P_LEAF,    36, "#2E7D32"), "value": f"{reduction_kg:.2f} kg", "label": "CO2削減量"},
                    {"icon": _icon(_P_CAR,     36, "#2E7D32"), "value": f"{occupancy_rate:.2f} 人/台", "label": "相乗り率"},
                    {"icon": _icon(_P_PARKING, 36, "#2E7D32"), "value": f"{actual_cars} 台",       "label": "現在の実稼働台数"},
                ])

                chart_data = pd.DataFrame({
                    "シナリオ": ["全員ソロ", "相乗り"],
                    "CO2排出量 (kg)": [total_solo/1000, total_share/1000]
                })
                st.plotly_chart(make_plotly_fig(chart_data), use_container_width=True)

                st.markdown("#### 登録内容の修正・削除")
                st.caption("リスト上の出発地はプライバシー保護のため市町村のみ表示されます。")

                car_keys = list(CO2_EMISSION_FACTORS.keys())
                for idx, row in df_p[::-1].iterrows():
                    o_idx = row['original_index']
                    safe_address = get_city_level_address(row['start_point'])
                    c_name, c_eff = split_car_info(row['car_type'])
                    title_str = f"{row['name']}  ({safe_address} | {c_name} | {row['people']}名)"

                    with st.expander(title_str):
                        with st.form(f"edit_{o_idx}"):
                            c1, c2 = st.columns(2)
                            with c1:
                                p_n = st.text_input("名前/グループ名", value=row['name'])
                                p_p = st.number_input("人数", 1, 10, int(row['people']))
                                current_car = row['car_type']
                                car_idx = car_keys.index(current_car) if current_car in car_keys else 0
                                p_c = st.selectbox("車種", car_keys, index=car_idx)
                            with c2:
                                p_s = st.text_input("出発地", value=row['start_point'])
                                p_d = st.number_input("距離 (km)", value=float(row['distance']))

                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("保存", use_container_width=True):
                                all_p.at[o_idx, 'name'] = p_n
                                all_p.at[o_idx, 'people'] = p_p
                                all_p.at[o_idx, 'car_type'] = p_c
                                all_p.at[o_idx, 'start_point'] = p_s
                                all_p.at[o_idx, 'distance'] = p_d
                                update_sheet_data("participants", all_p.drop(columns=['original_index']))
                                st.rerun()
                            if b2.form_submit_button("削除", type="primary", use_container_width=True):
                                update_sheet_data("participants", all_p.drop(index=o_idx).drop(columns=['original_index']))
                                st.rerun()
            else:
                st.info("参加者なし")

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        if st.button("管理者用トップページに戻る"):
            st.query_params.clear()
            st.rerun()
