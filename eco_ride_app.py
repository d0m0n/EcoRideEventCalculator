import streamlit as st
import pandas as pd
import plotly.express as px
import math
import uuid
import requests
from streamlit_gsheets import GSheetsConnection

# --- 設定・定数 ---
CO2_EMISSION_FACTORS = {
    "ガソリン車 (普通)": 130, "ガソリン車 (大型・ミニバン)": 180,
    "軽自動車": 100, "ディーゼル車": 110, "ハイブリッド車": 70, "電気自動車 (EV)": 0
}
MAX_CAPACITY = {
    "ガソリン車 (普通)": 5, "ガソリン車 (大型・ミニバン)": 8,
    "軽自動車": 4, "ディーゼル車": 5, "ハイブリッド車": 5, "電気自動車 (EV)": 5
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
        "components": "country:jp" # 日本国内に限定
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            # 候補のリストを作成 (表示名と裏側のデータを保持)
            suggestions = []
            for prediction in data["predictions"]:
                suggestions.append({
                    "label": prediction["description"], # ユーザーに見せる候補名
                    "value": prediction["description"]  # 実際に使う住所
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

# --- メイン処理 ---

# URLパラメータからevent_idを取得
query_params = st.query_params
current_event_id = query_params.get("event_id", None)

# SecretsからAPIキー取得
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
    st.info("イベントの情報を入力してURLを発行してください。")

    # 新規イベント作成フォーム
    with st.form("create_event"):
        st.subheader("新規イベント作成")
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

    st.markdown("---")
    st.subheader("作成済みイベント一覧")
    
    events_df = load_sheet("events")
    if not events_df.empty and "location_name" in events_df.columns:
        for idx, row in events_df.iterrows():
            base_url = "https://ecorideeventcalculator-2vhvzkr7oenknbuegaremc.streamlit.app/"
            invite_url = f"{base_url}?event_id={row['event_id']}"
            
            with st.expander(f"📍 {row['event_name']} ({row['event_date']})"):
                st.write(f"**場所:** {row['location_name']}")
                st.caption(f"住所: {row['location_address']}")
                st.code(invite_url, language="text")
                st.caption("👆 このURLを参加者に共有してください")

# ==========================================
# モードB: イベントIDがある場合（参加者・集計画面）
# ==========================================
else:
    events_df = load_sheet("events")
    events_df["event_id"] = events_df["event_id"].astype(str)
    target_event = events_df[events_df["event_id"] == str(current_event_id)]
    
    if target_event.empty:
        st.error("指定されたイベントが見つかりません。")
        if st.button("トップに戻る"):
            st.query_params.clear()
            st.rerun()
    else:
        event_data = target_event.iloc[0]
        
        # タイトル部分
        st.title(f"🚗 {event_data['event_name']}")
        loc_name = event_data['location_name'] if 'location_name' in event_data else event_data['location']
        loc_addr = event_data['location_address'] if 'location_address' in event_data else loc_name
        
        st.markdown(f"**開催日:** {event_data['event_date']}　|　**会場:** {loc_name}")
        
        # --- サイドバー：参加登録（Autocomplete対応版） ---
        st.sidebar.header("参加登録フォーム")
        
        # 1. 検索ワードの入力（フォームの外に出すことでインタラクティブにする）
        st.sidebar.markdown("##### 1. 出発地を検索")
        search_query = st.sidebar.text_input("地名や駅名を入力してください", placeholder="例: 新宿駅", key="search_box")
        
        # 2. 候補の取得と選択
        selected_address = None
        if search_query:
            suggestions = get_place_suggestions(search_query, MAPS_API_KEY)
            if suggestions:
                # 候補リストを作成（ユーザーにはlabelを見せ、選択されたらvalueを使う）
                options = [s["label"] for s in suggestions]
                selected_option = st.sidebar.selectbox("候補から選択してください", options)
                selected_address = selected_option # 今回はlabel自体を住所として利用
            else:
                st.sidebar.warning("候補が見つかりませんでした。詳細に入力してください。")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("##### 2. 詳細情報の登録")

        # 3. 登録フォーム
        with st.sidebar.form("join_form"):
            # 検索結果があればそれを初期値に、なければ空欄
            initial_val = selected_address if selected_address else ""
            
            # ユーザーが最終確認・修正できるフィールド
            final_start_point = st.text_input("出発地 (確定)", value=initial_val)
            name = st.text_input("グループ名 / お名前")
            num_people = st.number_input("人数", 1, 10, 2)
            car_type = st.selectbox("使用する車両", list(CO2_EMISSION_FACTORS.keys()))
            
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

        # --- 集計結果の表示 ---
        all_participants = load_sheet("participants")
        
        if not all_participants.empty and "event_id" in all_participants.columns:
            all_participants["event_id"] = all_participants["event_id"].astype(str)
            df_p = all_participants[all_participants["event_id"] == str(current_event_id)]
            
            if not df_p.empty:
                # 計算
                total_solo_co2 = 0
                total_share_co2 = 0
                for index, row in df_p.iterrows():
                    factor = CO2_EMISSION_FACTORS.get(row['car_type'], 130)
                    capacity = MAX_CAPACITY.get(row['car_type'], 5)
                    dist = float(row['distance'])
                    ppl = int(row['people'])
                    
                    solo = ppl * dist * factor * 2
                    share = math.ceil(ppl / capacity) * dist * factor * 2
                    total_solo_co2 += solo
                    total_share_co2 += share

                # 表示
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
                fig = px.bar(chart_data, x="シナリオ", y="CO2排出量 (kg)", 
                             color="シナリオ", color_discrete_sequence=["#FF6B6B", "#4ECDC4"])
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("#### 参加者リスト")
                st.dataframe(df_p[["name", "start_point", "distance", "people", "car_type"]])
            else:
                st.info("まだ参加者が登録されていません。")
        else:
             st.info("まだ参加者が登録されていません。")
             
        st.markdown("---")
        if st.button("管理者用トップページに戻る"):
            st.query_params.clear()
            st.rerun()