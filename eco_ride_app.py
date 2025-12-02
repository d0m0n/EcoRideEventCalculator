import streamlit as st
import pandas as pd
import plotly.express as px
import math

# ---------------------------------------------------------
# 1. 設定・定数定義 (CO2排出係数: g-CO2/km)
# ※国土交通省等の目安値を参考にした概算値
# ---------------------------------------------------------
CO2_EMISSION_FACTORS = {
    "ガソリン車 (普通)": 130,
    "ガソリン車 (大型・ミニバン)": 180,
    "軽自動車": 100,
    "ディーゼル車": 110,
    "ハイブリッド車": 70,
    "電気自動車 (EV)": 0,  # 走行時排出ゼロとして計算（電源構成は考慮せず）
}

MAX_CAPACITY = {
    "ガソリン車 (普通)": 5,
    "ガソリン車 (大型・ミニバン)": 8,
    "軽自動車": 4,
    "ディーゼル車": 5,
    "ハイブリッド車": 5,
    "電気自動車 (EV)": 5,
}

# ---------------------------------------------------------
# 2. UI構成
# ---------------------------------------------------------
st.set_page_config(page_title="イベント相乗りCO2削減シミュレーター", layout="wide")

st.title("🚗 イベント相乗り CO2削減ビジュアライザー")
st.markdown("「もし全員が1人で車に来たら」 vs 「相乗りして来たら」 のCO2排出量を比較します。")

# サイドバー：イベント設定
st.sidebar.header("📍 イベント設定")
event_name = st.sidebar.text_input("イベント名", "〇〇音楽フェス 2024")
event_location = st.sidebar.text_input("開催場所", "富士山特設会場")

# セッション状態の初期化（参加者リスト用）
if 'participants' not in st.session_state:
    st.session_state.participants = []

# ---------------------------------------------------------
# 3. 入力フォームエリア
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("参加者グループ登録")

with st.sidebar.form("add_group_form"):
    start_point = st.text_input("出発地点 (例: 東京駅周辺)", "自宅エリア")
    distance = st.number_input("会場までの片道距離 (km)", min_value=1.0, value=50.0)
    num_people = st.number_input("このグループの人数 (人)", min_value=1, value=4)
    car_type = st.selectbox("使用する車両タイプ", list(CO2_EMISSION_FACTORS.keys()))
    
    submitted = st.form_submit_button("リストに追加")
    if submitted:
        st.session_state.participants.append({
            "start": start_point,
            "distance": distance,
            "people": num_people,
            "car_type": car_type
        })
        st.success(f"{start_point} からのグループを追加しました！")

# ---------------------------------------------------------
# 4. 計算ロジック
# ---------------------------------------------------------
if len(st.session_state.participants) > 0:
    df = pd.DataFrame(st.session_state.participants)

    # 計算用リスト
    results = []

    total_solo_co2 = 0
    total_share_co2 = 0

    for index, row in df.iterrows():
        factor = CO2_EMISSION_FACTORS[row['car_type']]
        capacity = MAX_CAPACITY[row['car_type']]
        
        # A. 全員が個別の車 (ソロ) で来た場合
        # 車の台数 = 人数
        solo_cars = row['people']
        solo_emissions = solo_cars * row['distance'] * factor * 2 # 往復計算
        
        # B. 相乗り (シェア) した場合
        # 車の台数 = 人数 / 定員 (切り上げ)
        share_cars = math.ceil(row['people'] / capacity)
        share_emissions = share_cars * row['distance'] * factor * 2 # 往復計算

        total_solo_co2 += solo_emissions
        total_share_co2 += share_emissions

        results.append({
            "出発地": row['start'],
            "人数": row['people'],
            "車種": row['car_type'],
            "距離(往復)": row['distance'] * 2,
            "ソロ時の台数": solo_cars,
            "相乗り時の台数": share_cars,
            "ソロ排出量(kg)": round(solo_emissions / 1000, 2),
            "相乗り排出量(kg)": round(share_emissions / 1000, 2),
            "削減量(kg)": round((solo_emissions - share_emissions) / 1000, 2)
        })

    result_df = pd.DataFrame(results)

    # ---------------------------------------------------------
    # 5. 結果の可視化
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader(f"📊 {event_name} シミュレーション結果")

    # メトリクス表示
    col1, col2, col3 = st.columns(3)
    reduction_kg = (total_solo_co2 - total_share_co2) / 1000
    reduction_pct = (1 - (total_share_co2 / total_solo_co2)) * 100 if total_solo_co2 > 0 else 0
    
    # 杉の木の年間吸収量換算 (1本あたり約14kg/年と仮定)
    cedar_trees = reduction_kg / 14 

    col1.metric("総CO2削減量", f"{reduction_kg:.2f} kg-CO2")
    col2.metric("削減率", f"{reduction_pct:.1f} %")
    col3.metric("杉の木(年間吸収量)換算", f"{cedar_trees:.1f} 本分 🌲")

    # グラフエリア
    st.markdown("#### 排出量の比較")
    
    # データ整形
    chart_data = pd.DataFrame({
        "シナリオ": ["全員ソロ移動 (Before)", "相乗り移動 (After)"],
        "CO2排出量 (kg)": [total_solo_co2/1000, total_share_co2/1000]
    })
    
    fig = px.bar(
        chart_data, 
        x="シナリオ", 
        y="CO2排出量 (kg)", 
        color="シナリオ",
        color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
        text_auto=True,
        title="イベント全体のCO2排出量比較"
    )
    st.plotly_chart(fig, use_container_width=True)

    # 詳細テーブル
    st.markdown("#### グループ別詳細データ")
    st.dataframe(result_df)

    # リセットボタン
    if st.button("データをリセット"):
        st.session_state.participants = []
        st.experimental_rerun()

else:
    st.info("👈 左側のサイドバーから参加者グループを追加してください。")
    
    # デモ用の説明
    st.markdown("""
    ### アプリの使い方
    1. **イベント情報**を入力します。
    2. **参加者グループ**を追加します。
       - 例: Aさん達4人は、50km離れた場所からミニバンで来る。
       - 本来なら車4台ですが、相乗りなら1台で済みます。
    3. **車種**（軽、普通、EVなど）を選ぶことで排出係数が変わります。
    4. **CO2削減量**が自動計算され、グラフで可視化されます。
    """)