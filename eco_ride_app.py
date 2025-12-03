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

# Google Places API (Autocomplete) で場所の候補を取得する関数
def get_place_suggestions(query, api_key):
    if not query:
        return []
    
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query,
        "key": api_key,
        "language": "ja",
        "components": "country:jp"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            suggestions = []
            for prediction in data["predictions"]:
                suggestions.append({
                    "label": prediction["description"],
                    "value": prediction["description"]
                })
            return suggestions
    except Exception as e:
        st.error(f"場所検索エラー: {e}")
    return []

# Google Maps APIで距離を計算する関数
def get_distance(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": api_key,
        "language": "ja"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            rows = data.get("rows", [])
            if rows and rows[0].get("elements"):
                element = rows[0]["elements"][0]
                if element.get("status") == "OK":
                    distance_m = element["distance"]["value"]
                    return distance_m / 1000.0
    except Exception as e:
        st.error(f"距離計算エラー: {e}")
    return None

# シート読み込み
def load_sheet(worksheet_name):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        return conn.read(worksheet=worksheet_name, ttl=0)
    except:
        return pd.DataFrame()

# シート書き込み
def append_to_sheet(worksheet_name, new_data_dict):
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_sheet(worksheet_name)
    new_df = pd.DataFrame([new_data_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True)
    conn.update(worksheet=worksheet_name, data=updated_df)

# シート更新
def update_sheet_data(worksheet_name, df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(worksheet=worksheet_name, data=df)

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
        st.info("新しいイベント情報を入力してください。")
        with st.form("create_event"):
            e_name = st.text_input("イベント名", placeholder="例：〇〇音楽フェス 2025")
            e_date = st.date_input("開催日")
            
            col1, col2 = st.columns(2)
            with col1:
                e_loc_name = st.text_input("開催場所名", placeholder="例：日本武道館")
            with col2:
                e_loc_addr = st.text_input("開催場所の住所 (距離計算用)", placeholder="例：東京都千代田区北の丸公園2-3")
                st.caption("※Googleマップで検索できる正確な住所を入力してください")
            
            submitted = st.form_submit_button("イベントを作成")
            
            if submitted:
                if not e_name or not e_loc_name or not e_loc_addr:
                    st.warning("すべての項目を入力してください。")
                else:
                    new_id = str(uuid.uuid4())[:8]
                    append_to_sheet("events", {
                        "event_id": new_id,
                        "event_name": e_name,
                        "event_date": str(e_date),
                        "location_name": e_loc_name,
                        "location_address": e_loc_addr
                    })
                    st.success(f"イベント「{e_name}」を作成しました！")
                    st.rerun()

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
                        with st.form(f"edit_form_{row['event_id']}"):
                            new_name = st.text_input("イベント名", value=row['event_name'])
                            new_loc_name = st.text_input("場所名", value=row['location_name'])
                            new_loc_addr = st.text_input("住所", value=row['location_address'])
                            new_date_str = st.text_input("開催日", value=row['event_date'])

                            c_edit, c_del = st.columns(2)
                            with c_edit:
                                update_btn = st.form_submit_button("更新する")
                            with c_del:
                                delete_btn = st.form_submit_button("削除する", type="primary")

                            if update_btn:
                                events_df.at[index, 'event_name'] = new_name
                                events_df.at[index, 'location_name'] = new_loc_name
                                events_df.at[index, 'location_address'] = new_loc_addr
                                events_df.at[index, 'event_date'] = new_date_str
                                update_sheet_data("events", events_df)
                                st.success("情報を更新しました！")
                                st.rerun()
                            
                            if delete_btn:
                                events_df = events_df.drop(index)
                                update_sheet_data("events", events_df)
                                st.warning("イベントを削除しました。")
                                st.rerun()

        else:
            st.info("まだイベントが作成されていません。")

# ==========================================
# モードB: イベントIDがある場合（参加者・集計画面）
# ==========================================
else:
    events_df = load_sheet("events")
    events_df["event_id"] = events_df["event_id"].astype(str)
    target_event = events_df[events_df["event_id"] == str(current_event_id)]
    
    if target_event.empty:
        st.error("指定されたイベントが見つかりません。削除された可能性があります。")
        if st.button("トップに戻る"):
            st.query_params.clear()
            st.rerun()
    else:
        event_data = target_event.iloc[0]
        
        st.title(f"🚗 {event_data['event_name']}")
        loc_name = event_data['location_name'] if 'location_name' in event_data else event_data['location']
        loc_addr = event_data['location_address'] if 'location_address' in event_data else loc_name
        
        st.markdown(f"**開催日:** {event_data['event_date']}　|　**会場:** {loc_name}")

        # --- 出典情報の詳細表示 ---
        with st.expander("📏 CO2排出量の計算式・根拠データ（出典）について"):
            st.markdown("""
            本アプリでは、**環境省「算定・報告・公表制度」** の排出係数を基に、一般的な実燃費を想定して1kmあたりのCO2排出量を算出しています。
            
            ##### 1. 計算の前提（使用係数）
            環境省が定めている、燃料1リットルあたりのCO2排出量は以下の通りです。
            * **ガソリン:** 2.32 kg-CO2 / L
            * **軽油:** 2.58 kg-CO2 / L
            
            ##### 2. 本アプリでの算出ロジック
            $$
            \\text{1km排出量} = \\frac{\\text{燃料の排出係数 (g/L)}}{\\text{想定燃費 (km/L)}}
            $$
            
            実際の道路状況（渋滞・エアコン使用・多人数乗車）を考慮し、カタログ値ではなく**一般的な実燃費**を想定して設定しています。
            """)
            
            # 係数表の作成
            data_items = []
            for k, v in CO2_EMISSION_FACTORS.items():
                data_items.append({"車種設定": k, "設定排出係数 (g-CO2/km)": v})
            
            factor_df = pd.DataFrame(data_items)
            st.table(factor_df)
            
            st.caption("""
            * **出典リンク:** [環境省 温室効果ガス排出量 算定・報告・公表制度](https://ghg-santeikohyo.env.go.jp/calc)
            * **電気自動車 (EV):** 「走行時の排出量」はゼロとして計算しています（発電由来の排出は考慮していません）。
            """)
        
        # --- サイドバー：参加登録 ---
        st.sidebar.header("参加登録フォーム")
        
        st.sidebar.markdown("##### 1. 出発地を検索")
        search_query = st.sidebar.text_input("地名や駅名を入力してください", placeholder="例: 新宿駅", key="search_box")
        
        selected_address = None
        if search_query:
            suggestions = get_place_suggestions(search_query, MAPS_API_KEY)
            if suggestions:
                options = [s["label"] for s in suggestions]
                selected_option = st.sidebar.selectbox("候補から選択してください", options)
                selected_address = selected_option
            else:
                st.sidebar.warning("候補が見つかりませんでした。詳細に入力してください。")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("##### 2. 詳細情報の登録")

        with st.sidebar.form("join_form"):
            initial_val = selected_address if selected_address else ""
            final_start_point = st.text_input("出発地 (確定)", value=initial_val)
            name = st.text_input("グループ名 / お名前")
            num_people = st.number_input("人数", 1, 10, 2)
            
            # 車種選択ロジック（万が一キーが変わった場合の対策でindex取得を修正）
            car_keys = list(CO2_EMISSION_FACTORS.keys())
            car_type = st.selectbox("使用する車両", car_keys)
            
            st.caption(f"目的地: {loc_name}")
            join_submitted = st.form_submit_button("計算して登録")
            
            if join_submitted:
                if not final_start_point:
                    st.error("出発地が入力されていません。")
                else:
                    with st.spinner("Google Mapsで距離を計測中..."):
                        dist_km = get_distance(final_start_point, loc_addr, MAPS_API_KEY)
                    
                    if dist_km:
                        append_to_sheet("participants", {
                            "event_id": str(current_event_id),
                            "name": name,
                            "start_point": final_start_point,
                            "distance": dist_km,
                            "people": num_people,
                            "car_type": car_type
                        })
                        st.success(f"登録完了！ 会場まで約 {dist_km:.1f}km です。")
                        st.rerun()
                    else:
                        st.error("ルートが見つかりませんでした。住所を確認してください。")

        # --- 集計結果 ---
        all_participants = load_sheet("participants")
        
        if not all_participants.empty and "event_id" in all_participants.columns:
            all_participants["event_id"] = all_participants["event_id"].astype(str)
            all_participants['original_index'] = all_participants.index
            df_p = all_participants[all_participants["event_id"] == str(current_event_id)].copy()
            
            if not df_p.empty:
                total_solo_co2 = 0
                total_share_co2 = 0
                for index, row in df_p.iterrows():
                    # 以前のデータでキーが合わない場合のフォールバック
                    c_type = row['car_type']
                    if c_type not in CO2_EMISSION_FACTORS:
                        # 部分一致などを試みるか、デフォルト値を使う
                        factor = 166 # 普通車の値をデフォルトに
                        capacity = 5
                    else:
                        factor = CO2_EMISSION_FACTORS[c_type]
                        capacity = MAX_CAPACITY[c_type]
                    
                    try:
                        dist = float(row['distance'])
                        ppl = int(row['people'])
                    except:
                        continue

                    solo = ppl * dist * factor * 2
                    share = math.ceil(ppl / capacity) * dist * factor * 2
                    total_solo_co2 += solo
                    total_share_co2 += share

                st.markdown("---")
                st.subheader("📊 CO2削減効果")
                col1, col2 = st.columns(2)
                reduction_kg = (total_solo_co2 - total_share_co2) / 1000
                col1.metric("みんなの総CO2削減量", f"{reduction_kg:.2f} kg-CO2")
                col1.success(f"🌲 杉の木 約 {reduction_kg / 14:.1f} 本分の年間吸収量！")
                
                chart_data = pd.DataFrame({
                    "シナリオ": ["全員ソロ移動", "相乗り移動"],
                    "CO2排出量 (kg)": [total_solo_co2/1000, total_share_co2/1000]
                })
                
                fig = px.bar(
                    chart_data, 
                    x="シナリオ", 
                    y="CO2排出量 (kg)", 
                    color="シナリオ", 
                    color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
                    text="CO2排出量 (kg)"
                )
                
                fig.update_traces(
                    texttemplate='%{y:.1f} kg',
                    textposition='inside',
                    textfont=dict(size=30, color='white', family="Arial Black")
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("#### 📝 参加者リスト・編集")
                st.caption("各カードを開くと、登録内容の修正や削除ができます。")
                
                car_keys = list(CO2_EMISSION_FACTORS.keys())
                for idx, row in df_p[::-1].iterrows():
                    original_idx = row['original_index']
                    
                    with st.expander(f"👤 {row['name']} （{row['start_point']} から {row['people']}名）"):
                        with st.form(f"participant_edit_{original_idx}"):
                            c1, c2 = st.columns(2)
                            with c1:
                                p_name = st.text_input("名前", value=row['name'])
                                p_people = st.number_input("人数", min_value=1, value=int(row['people']))
                                
                                # 車種選択の初期値合わせ（データ不整合対策）
                                current_car = row['car_type']
                                car_index = 0
                                if current_car in car_keys:
                                    car_index = car_keys.index(current_car)
                                
                                p_car = st.selectbox("車種", car_keys, index=car_index)
                            with c2:
                                p_start = st.text_input("出発地", value=row['start_point'])
                                p_dist = st.number_input("距離 (km)", value=float(row['distance']))
                            
                            btn_col1, btn_col2 = st.columns(2)
                            with btn_col1:
                                update_p_btn = st.form_submit_button("修正内容を保存")
                            with btn_col2:
                                delete_p_btn = st.form_submit_button("この登録を削除", type="primary")
                            
                            if update_p_btn:
                                all_participants.at[original_idx, 'name'] = p_name
                                all_participants.at[original_idx, 'people'] = p_people
                                all_participants.at[original_idx, 'car_type'] = p_car
                                all_participants.at[original_idx, 'start_point'] = p_start
                                all_participants.at[original_idx, 'distance'] = p_dist
                                save_df = all_participants.drop(columns=['original_index'])
                                update_sheet_data("participants", save_df)
                                st.success("参加者情報を更新しました！")
                                st.rerun()

                            if delete_p_btn:
                                all_participants = all_participants.drop(original_idx)
                                save_df = all_participants.drop(columns=['original_index'])
                                update_sheet_data("participants", save_df)
                                st.warning("参加者情報を削除しました。")
                                st.rerun()

            else:
                st.info("まだ参加者が登録されていません。サイドバーから登録しましょう！")
        else:
             st.info("まだ参加者が登録されていません。")
             
        st.markdown("---")
        if st.button("管理者用トップページに戻る"):
            st.query_params.clear()
            st.rerun()