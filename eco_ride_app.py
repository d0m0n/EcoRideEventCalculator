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
        elif data["status"] != "OK" and data["status"] != "ZERO_RESULTS":
            # エラーログ（デバッグ用）
            print(f"Places API Error: {data['status']}")
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

# シート書き込み（追記）
def append_to_sheet(worksheet_name, new_data_dict):
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_sheet(worksheet_name)
    new_df = pd.DataFrame([new_data_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True)
    conn.update(worksheet=worksheet_name, data=updated_df)

# シート更新（上書き・削除用）
def update_sheet_data(worksheet_name, df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(worksheet=worksheet_name, data=df)

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
    
    # タブで「新規作成」と「一覧・管理」を分ける
    tab1, tab2 = st.tabs(["✨ 新規イベント作成", "🛠 作成済みイベントの管理"])

    # --- 新規作成タブ ---
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

    # --- 管理タブ ---
    with tab2:
        st.subheader("作成済みイベント一覧")
        events_df = load_sheet("events")
        
        if not events_df.empty and "location_name" in events_df.columns:
            # 最新のイベントが上に来るように逆順表示（任意）
            for index, row in events_df[::-1].iterrows():
                
                # アプリのベースURLを取得（現在のURLを使用）
                # ※ st.rerun() などをしても消えないように動的に取得するのが理想だが、
                # 簡易的に固定ドメイン、またはデプロイ先のURLを想定。
                base_url = "https://ecorideeventcalculator-2vhvzkr7oenknbuegaremc.streamlit.app/"
                invite_url = f"{base_url}?event_id={row['event_id']}"
                
                # カードのような見た目で表示
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"### {row['event_name']}")
                        st.caption(f"📅 {row['event_date']} | 📍 {row['location_name']}")
                        st.text(f"URL: {invite_url}")
                    
                    with c2:
                        # 1. 参加者画面へ直接飛ぶボタン
                        st.link_button("🚀 参加者画面へ", invite_url)
                    
                    # 編集・削除エリア
                    with st.expander("⚙️ 編集・削除"):
                        with st.form(f"edit_form_{row['event_id']}"):
                            # 既存の値を初期値にする
                            new_name = st.text_input("イベント名", value=row['event_name'])
                            new_loc_name = st.text_input("場所名", value=row['location_name'])
                            new_loc_addr = st.text_input("住所", value=row['location_address'])
                            # 日付は文字列からDate型に戻す処理が必要だが、簡易的にTextで扱うか、変換する
                            # ここでは安全のためテキストのまま表示し、日付Widgetは使わない実装例とする
                            new_date_str = st.text_input("開催日 (YYYY-MM-DD)", value=row['event_date'])

                            c_edit, c_del = st.columns(2)
                            with c_edit:
                                update_btn = st.form_submit_button("更新する")
                            with c_del:
                                delete_btn = st.form_submit_button("削除する", type="primary")

                            if update_btn:
                                # データフレームの値を更新
                                events_df.at[index, 'event_name'] = new_name
                                events_df.at[index, 'location_name'] = new_loc_name
                                events_df.at[index, 'location_address'] = new_loc_addr
                                events_df.at[index, 'event_date'] = new_date_str
                                
                                update_sheet_data("events", events_df)
                                st.success("情報を更新しました！")
                                st.rerun()
                            
                            if delete_btn:
                                # その行を削除
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
        
        # タイトル部分
        st.title(f"🚗 {event_data['event_name']}")
        loc_name = event_data['location_name'] if 'location_name' in event_data else event_data['location']
        loc_addr = event_data['location_address'] if 'location_address' in event_data else loc_name
        
        st.markdown(f"**開催日:** {event_data['event_date']}　|　**会場:** {loc_name}")
        
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

        # --- 集計結果 ---
        all_participants = load_sheet("participants")
        
        if not all_participants.empty and "event_id" in all_participants.columns:
            all_participants["event_id"] = all_participants["event_id"].astype(str)
            df_p = all_participants[all_participants["event_id"] == str(current_event_id)]
            
            if not df_p.empty:
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