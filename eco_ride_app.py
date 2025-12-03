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

# Google Maps APIで距離を計算する関数
def get_distance(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": api_key,
        "language": "ja" # 日本語で処理
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            # 距離（メートル）を取得してkmに変換
            distance_m = data["rows"][0]["elements"][0]["distance"]["value"]
            return distance_m / 1000.0
    except Exception as e:
        st.error(f"距離計算エラー: {e}")
        return None
    return None

# シート読み込み（キャッシュなし）
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
MAPS_API_KEY = st.secrets["general"]["google_maps_api_key"]

# ==========================================
# モードA: イベントIDがない場合（主催者用画面）
# ==========================================
if not current_event_id:
    st.title("📅 イベント作成・管理パネル")
    st.info("新しいイベントを作成するか、下のリストからイベントURLをコピーして参加者に送ってください。")

    # 新規イベント作成フォーム
    with st.form("create_event"):
        st.subheader("新規イベント作成")
        e_name = st.text_input("イベント名", "〇〇フェス 2025")
        e_date = st.date_input("開催日")
        e_loc = st.text_input("開催場所 (詳細な住所を入力)", "東京都千代田区千代田1-1")
        
        submitted = st.form_submit_button("イベントを作成")
        if submitted and e_name and e_loc:
            new_id = str(uuid.uuid4())[:8] # ランダムなID生成
            append_to_sheet("events", {
                "event_id": new_id,
                "event_name": e_name,
                "event_date": str(e_date),
                "location": e_loc
            })
            st.success(f"イベントを作成しました！ ID: {new_id}")
            st.experimental_rerun()

    st.markdown("---")
    st.subheader("作成済みイベント一覧")
    
    events_df = load_sheet("events")
    if not events_df.empty:
        for idx, row in events_df.iterrows():
            # 招待用URLの生成
            # ※注意: ローカル環境とCloud環境でベースURLが変わりますが、ブラウザのアドレスバーのURLを使ってください
            base_url = "https://ecorideeventcalculator-2vhvzkr7oenknbuegaremc.streamlit.app/" # あなたのアプリURLに書き換えてもOK
            invite_url = f"{base_url}?event_id={row['event_id']}"
            
            with st.expander(f"📍 {row['event_name']} ({row['event_date']})"):
                st.write(f"**開催地:** {row['location']}")
                st.code(invite_url, language="text")
                st.caption("👆 このURLを参加者に共有してください")

# ==========================================
# モードB: イベントIDがある場合（参加者・集計画面）
# ==========================================
else:
    # イベント情報の取得
    events_df = load_sheet("events")
    # 文字列型に統一して検索
    events_df["event_id"] = events_df["event_id"].astype(str)
    target_event = events_df[events_df["event_id"] == str(current_event_id)]
    
    if target_event.empty:
        st.error("指定されたイベントが見つかりません。URLを確認してください。")
        if st.button("トップに戻る"):
            st.query_params.clear()
            st.experimental_rerun()
    else:
        event_data = target_event.iloc[0]
        st.title(f"🚗 {event_data['event_name']} CO2削減チェッカー")
        st.write(f"**開催日:** {event_data['event_date']} / **会場:** {event_data['location']}")
        
        # サイドバー：参加登録
        st.sidebar.header("参加登録フォーム")
        with st.sidebar.form("join_form"):
            name = st.text_input("グループ名 / お名前")
            start_point = st.text_input("出発地 (住所や建物名)", help="正確な距離計算のために詳細に入力してください")
            
            # 距離の自動計算ボタン（フォーム内では動作しないため、計算ロジックはsubmit後に実施）
            st.caption("※「登録」を押すと、会場までの距離を自動計算して登録します。")
            
            num_people = st.number_input("人数", 1, 10, 2)
            car_type = st.selectbox("使用する車両", list(CO2_EMISSION_FACTORS.keys()))
            
            join_submitted = st.form_submit_button("計算して登録")
            
            if join_submitted and start_point:
                with st.spinner("Google Mapsで距離を計測中..."):
                    dist_km = get_distance(start_point, event_data['location'], MAPS_API_KEY)
                
                if dist_km:
                    append_to_sheet("participants", {
                        "event_id": str(current_event_id),
                        "name": name,
                        "start_point": start_point,
                        "distance": dist_km,
                        "people": num_people,
                        "car_type": car_type
                    })
                    st.success(f"登録完了！ 会場まで約 {dist_km:.1f}km です。")
                    st.experimental_rerun()
                else:
                    st.error("場所が見つかりませんでした。出発地を詳しく入力してください。")

        # 集計結果の表示（そのイベントの参加者のみフィルタリング）
        all_participants = load_sheet("participants")
        
        if not all_participants.empty:
            # IDでフィルタリング
            all_participants["event_id"] = all_participants["event_id"].astype(str)
            df_p = all_participants[all_participants["event_id"] == str(current_event_id)]
            
            if not df_p.empty:
                # ここから計算ロジック（以前と同じ）
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

                # 可視化エリア
                st.markdown("---")
                col1, col2 = st.columns(2)
                reduction_kg = (total_solo_co2 - total_share_co2) / 1000
                
                col1.metric("みんなの総CO2削減量", f"{reduction_kg:.2f} kg-CO2")
                col1.success(f"杉の木 約 {reduction_kg / 14:.1f} 本分の吸収量！ 🌲")
                
                # グラフ
                chart_data = pd.DataFrame({
                    "シナリオ": ["全員ソロ移動", "相乗り移動"],
                    "CO2排出量 (kg)": [total_solo_co2/1000, total_share_co2/1000]
                })
                fig = px.bar(chart_data, x="シナリオ", y="CO2排出量 (kg)", 
                             color="シナリオ", color_discrete_sequence=["#FF6B6B", "#4ECDC4"])
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("#### 参加者リスト")
                st.dataframe(df_p[["name", "start_point", "distance", "people", "car_type"]])
                
                if st.button("トップページ（イベント管理）に戻る"):
                    st.query_params.clear()
                    st.experimental_rerun()
            else:
                st.info("まだ参加者が登録されていません。サイドバーから登録しましょう！")
        else:
             st.info("まだ参加者が登録されていません。")