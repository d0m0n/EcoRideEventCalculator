import streamlit as st
import pandas as pd
import plotly.express as px
import math
import uuid
import requests
from streamlit_gsheets import GSheetsConnection

# --- 設定・定数 ---
# 根拠: 環境省等の排出係数(ガソリン2.32kg-CO2/L, 軽油2.58kg-CO2/L)を
# 一般的な実燃費(e燃費等の平均値を参考に設定)で割って算出
CO2_EMISSION_FACTORS = {
    "ガソリン車 (普通 / 14km/L)": 166,
    "ガソリン車 (大型・ミニバン / 9km/L)": 258,
    "軽自動車 (16km/L)": 145,
    "ディーゼル車 (13km/L)": 198,
    "ハイブリッド車 (22km/L)": 105,
    "電気自動車 (EV / 走行時ゼロ)": 0,
}

MAX_CAPACITY = {
    "ガソリン車 (普通 / 14km/L)": 5,
    "ガソリン車 (大型・ミニバン / 9km/L)": 8,
    "軽自動車 (16km/L)": 4,
    "ディーゼル車 (13km/L)": 5,
    "ハイブリッド車 (22km/L)": 5,
    "電気自動車 (EV / 走行時ゼロ)": 5,
}

# ページ設定
st.set_page_config(page_title="イベント相乗りCO2削減シミュレーター", layout="wide")

# --- 関数群 ---

def get_place_suggestions(query, api_key):
    if not query:
        return []
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query, "key": api_key, "language": "ja", "components": "country:jp"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            suggestions = []
            for prediction in data["predictions"]:
                suggestions.append({"label": prediction["description"], "value": prediction["description"]})
            return suggestions
    except Exception as e:
        st.error(f"場所検索エラー: {e}")
    return []

def get_distance(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin, "destinations": destination, "key": api_key, "language": "ja"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            rows = data.get("rows", [])
            if rows and rows[0].get("elements"):
                element = rows[0]["elements"][0]
                if element.get("status") == "OK":
                    return element["distance"]["value"] / 1000.0
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

# --- 計算ロジック共通化 ---
def calculate_emissions(df_participants, current_event_id):
    """データフレームからCO2削減量を計算して返すヘルパー関数"""
    if df_participants.empty or "event_id" not in df_participants.columns:
        return None, None, pd.DataFrame()

    df_participants["event_id"] = df_participants["event_id"].astype(str)
    # 元のインデックスを保持
    if 'original_index' not in df_participants.columns:
        df_participants['original_index'] = df_participants.index
        
    df_p = df_participants[df_participants["event_id"] == str(current_event_id)].copy()
    
    if df_p.empty:
        return 0, 0, df_p

    total_solo = 0
    total_share = 0
    
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
            solo = ppl * dist * factor * 2
            share = math.ceil(ppl / capacity) * dist * factor * 2
            total_solo += solo
            total_share += share
        except:
            continue
            
    return total_solo, total_share, df_p

# --- ライブモニター用フラグメント ---
@st.fragment(run_every=10)
def show_live_monitor(current_event_id):
    st.markdown("### 📡 リアルタイム集計モニター (10秒自動更新)")
    st.caption("※この画面は自動で最新情報に更新されます。入力操作は「登録モード」で行ってください。")
    
    # 常に最新データをロード
    all_p = load_sheet("participants")
    total_solo, total_share, df_p = calculate_emissions(all_p, current_event_id)
    
    if df_p.empty:
        st.info("現在、参加者は登録されていません。待機中...")
        return

    # メトリクス表示
    col1, col2 = st.columns(2)
    reduction_kg = (total_solo - total_share) / 1000
    col1.metric("みんなの総CO2削減量", f"{reduction_kg:.2f} kg-CO2")
    col1.success(f"🌲 杉の木 約 {reduction_kg / 14:.1f} 本分の年間吸収量！")
    
    # グラフ表示
    chart_data = pd.DataFrame({
        "シナリオ": ["全員ソロ移動", "相乗り移動"],
        "CO2排出量 (kg)": [total_solo/1000, total_share/1000]
    })
    fig = px.bar(chart_data, x="シナリオ", y="CO2排出量 (kg)", 
                    color="シナリオ", color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
                    text="CO2排出量 (kg)")
    fig.update_traces(texttemplate='%{y:.1f} kg', textposition='inside',
                        textfont=dict(size=40, color='white', family="Arial Black"))
    st.plotly_chart(fig, use_container_width=True)
    
    # リスト表示（閲覧専用・シンプル版）
    st.markdown("#### 📋 最新の参加者リスト")
    # 見やすいように必要な列だけ抽出して表示
    display_df = df_p[["name", "start_point", "people", "car_type", "distance"]].copy()
    display_df.columns = ["グループ名", "出発地", "人数", "車種", "距離(km)"]
    # 最新順
    st.dataframe(display_df.iloc[::-1], use_container_width=True, hide_index=True)


# --- メイン処理 ---

query_params = st.query_params
current_event_id = query_params.get("event_id", None)

try:
    MAPS_API_KEY = st.secrets["general"]["google_maps_api_key"]
except KeyError:
    st.error("SecretsにGoogle Maps APIキーが設定されていません。")
    st.stop()

# ==========================================
# モードA: イベントIDがない場合（主催者用画面）
# ==========================================
if not current_event_id:
    st.title("📅 イベント作成・管理パネル")
    tab1, tab2 = st.tabs(["✨ 新規イベント作成", "🛠 作成済みイベントの管理"])

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
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"### {row['event_name']}")
                        st.caption(f"📅 {row['event_date']} | 📍 {row['location_name']}")
                        st.text(f"URL: {invite_url}")
                    with c2:
                        st.link_button("🚀 参加者画面へ", invite_url)
                    with st.expander("⚙️ 編集・削除"):
                        with st.form(f"edit_{row['event_id']}"):
                            n_name = st.text_input("名", value=row['event_name'])
                            n_loc = st.text_input("場", value=row['location_name'])
                            n_addr = st.text_input("住", value=row['location_address'])
                            n_date = st.text_input("日", value=row['event_date'])
                            c_up, c_del = st.columns(2)
                            if c_up.form_submit_button("更新"):
                                events_df.at[index, 'event_name'] = n_name
                                events_df.at[index, 'location_name'] = n_loc
                                events_df.at[index, 'location_address'] = n_addr
                                events_df.at[index, 'event_date'] = n_date
                                update_sheet_data("events", events_df)
                                st.rerun()
                            if c_del.form_submit_button("削除", type="primary"):
                                events_df = events_df.drop(index)
                                update_sheet_data("events", events_df)
                                st.rerun()
        else:
            st.info("イベントなし")

# ==========================================
# モードB: イベントIDがある場合（参加者・集計画面）
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
        st.title(f"🚗 {event_data['event_name']}")
        loc_name = event_data.get('location_name', event_data.get('location'))
        loc_addr = event_data.get('location_address', loc_name)
        st.markdown(f"**開催日:** {event_data['event_date']}　|　**会場:** {loc_name}")

        # 出典
        with st.expander("📏 CO2排出量の計算式・根拠データ（出典）について"):
            st.markdown("""
            本アプリでは、**環境省「算定・報告・公表制度」** の排出係数を基に、一般的な実燃費を想定して算出しています。
            $$ \\text{1km排出量} = \\frac{\\text{燃料排出係数 (g/L)}}{\\text{想定燃費 (km/L)}} $$
            """)
            data_items = [{"車種設定": k, "設定排出係数": v} for k, v in CO2_EMISSION_FACTORS.items()]
            st.table(pd.DataFrame(data_items))
            st.caption("出典: [環境省 温室効果ガス排出量 算定・報告・公表制度](https://ghg-santeikohyo.env.go.jp/calc)")

        # --- モード切替サイドバー ---
        st.sidebar.title("メニュー")
        app_mode = st.sidebar.radio("モード選択", ["📝 参加登録・編集", "📺 ライブモニター"], index=0)

        # ----------------------------------------------------
        # パターン1: ライブモニター (自動更新あり・閲覧専用)
        # ----------------------------------------------------
        if app_mode == "📺 ライブモニター":
            # ここだけ自動更新がかかる
            show_live_monitor(str(current_event_id))

        # ----------------------------------------------------
        # パターン2: 参加登録・編集 (自動更新なし・入力安全)
        # ----------------------------------------------------
        else:
            st.markdown("### 📝 参加登録・編集モード")
            
            # 1. 登録フォーム
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

            # 2. 集計・リスト表示（自動更新なし）
            all_p = load_sheet("participants")
            total_solo, total_share, df_p = calculate_emissions(all_p, current_event_id)
            
            if not df_p.empty:
                # グラフ
                st.markdown("---")
                col1, col2 = st.columns(2)
                red_kg = (total_solo - total_share) / 1000
                col1.metric("削減量", f"{red_kg:.2f} kg")
                
                c_data = pd.DataFrame({"シナリオ": ["全員ソロ", "相乗り"], "CO2": [total_solo/1000, total_share/1000]})
                fig = px.bar(c_data, x="シナリオ", y="CO2", color="シナリオ", 
                             color_discrete_sequence=["#FF6B6B", "#4ECDC4"], text="CO2")
                fig.update_traces(texttemplate='%{y:.1f} kg', textposition='inside', 
                                  textfont=dict(size=30, color='white', family="Arial Black"))
                st.plotly_chart(fig, use_container_width=True)

                # 編集リスト
                st.markdown("#### 🛠 登録内容の修正・削除")
                car_keys = list(CO2_EMISSION_FACTORS.keys())
                for idx, row in df_p[::-1].iterrows():
                    o_idx = row['original_index']
                    with st.expander(f"👤 {row['name']} ({row['start_point']})"):
                        with st.form(f"edit_{o_idx}"):
                            c1, c2 = st.columns(2)
                            with c1:
                                p_n = st.text_input("名", value=row['name'])
                                p_p = st.number_input("人", 1, 10, int(row['people']))
                                try: c_idx = car_keys.index(row['car_type'])
                                except: c_idx = 0
                                p_c = st.selectbox("車", car_keys, index=c_idx)
                            with c2:
                                p_s = st.text_input("発", value=row['start_point'])
                                p_d = st.number_input("km", value=float(row['distance']))
                            
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("保存"):
                                all_p.at[o_idx, 'name'] = p_n
                                all_p.at[o_idx, 'people'] = p_p
                                all_p.at[o_idx, 'car_type'] = p_c
                                all_p.at[o_idx, 'start_point'] = p_s
                                all_p.at[o_idx, 'distance'] = p_d
                                update_sheet_data("participants", all_p.drop(columns=['original_index']))
                                st.rerun()
                            if b2.form_submit_button("削除", type="primary"):
                                update_sheet_data("participants", all_p.drop(index=o_idx).drop(columns=['original_index']))
                                st.rerun()
            else:
                st.info("参加者なし")

        st.markdown("---")
        if st.button("管理者用トップページに戻る"):
            st.query_params.clear()
            st.rerun()