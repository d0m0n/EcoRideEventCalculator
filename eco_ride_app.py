import streamlit as st
import pandas as pd
import plotly.express as px
import math
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

st.set_page_config(page_title="イベント相乗りCO2削減シミュレーター", layout="wide")
st.title("🚗 イベント相乗り CO2削減ビジュアライザー (Live版)")

# --- Google Sheets 接続 ---
# スプレッドシートからデータを読み込む関数
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    # キャッシュを無効化して常に最新を取得（ttl=0）
    return conn.read(ttl=0)

# スプレッドシートへデータを追加する関数
def add_data(new_entry):
    conn = st.connection("gsheets", type=GSheetsConnection)
    current_df = conn.read(ttl=0)
    new_df = pd.DataFrame([new_entry])
    updated_df = pd.concat([current_df, new_df], ignore_index=True)
    conn.update(data=updated_df)

# --- UI & ロジック ---
# データの読み込み
try:
    df_participants = load_data()
    # 空の場合の処理
    if df_participants.empty:
        df_participants = pd.DataFrame(columns=["start", "distance", "people", "car_type"])
except:
    st.error("データベース接続設定が完了していません。Secretsを設定してください。")
    df_participants = pd.DataFrame()

# 参加者入力フォーム
st.sidebar.subheader("参加者グループ登録")
with st.sidebar.form("add_group_form"):
    start_point = st.text_input("出発地点", "自宅エリア")
    distance = st.number_input("片道距離 (km)", min_value=1.0, value=50.0)
    num_people = st.number_input("人数 (人)", min_value=1, value=4)
    car_type = st.selectbox("車両タイプ", list(CO2_EMISSION_FACTORS.keys()))
    
    submitted = st.form_submit_button("リストに追加")
    if submitted:
        new_entry = {
            "start": start_point,
            "distance": distance,
            "people": num_people,
            "car_type": car_type
        }
        add_data(new_entry)
        st.success("データを追加しました！画面をリロードすると反映されます。")
        st.experimental_rerun()

# --- 集計と表示 (データがある場合のみ) ---
if not df_participants.empty and len(df_participants) > 0:
    results = []
    total_solo_co2 = 0
    total_share_co2 = 0

    # データフレームのループ処理
    for index, row in df_participants.iterrows():
        # データ型変換（エラー回避）
        c_type = row['car_type']
        dist = float(row['distance'])
        ppl = int(row['people'])
        
        factor = CO2_EMISSION_FACTORS.get(c_type, 130) # デフォルト値対策
        capacity = MAX_CAPACITY.get(c_type, 5)

        solo_cars = ppl
        solo_emissions = solo_cars * dist * factor * 2
        
        share_cars = math.ceil(ppl / capacity)
        share_emissions = share_cars * dist * factor * 2

        total_solo_co2 += solo_emissions
        total_share_co2 += share_emissions
        
        results.append({
            "出発地": row['start'],
            "人数": ppl,
            "車種": c_type,
            "削減量(kg)": round((solo_emissions - share_emissions) / 1000, 2)
        })
    
    # ここから下のグラフ描画などは以前と同じコード...
    # (省略せずに必要な可視化コードを入れてください)
    
    st.metric("みんなで削減した総CO2量", f"{(total_solo_co2 - total_share_co2)/1000:.2f} kg")
    st.dataframe(pd.DataFrame(results))
    
else:
    st.info("まだ登録データがありません。サイドバーから登録してください。")