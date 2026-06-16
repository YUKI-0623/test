import streamlit as st
import pandas as pd

st.set_page_config(page_title="UmAI 競馬予想アプリ 2026", layout="wide")
st.title("🏇 UmAI 競馬シミュレーター 2026")

# 1. 精度重視のデータ（適性1と2を個別に持たせます）
def get_race_data():
    return pd.DataFrame({
        '馬名': ['ダノンデサイル', 'コスモキュランダ', 'クロワデュノール', 'メイショウタバル', 'レガレイラ', 'シンエンペラー', 'シュガークン'],
        '馬場適性': [0.9, 0.8, 0.7, 0.95, 0.6, 0.85, 0.7],
        '血統スタミナ': [0.8, 0.9, 0.75, 0.9, 0.8, 0.95, 0.85],
        '騎手補正': [0.9, 0.8, 0.9, 0.95, 0.85, 0.9, 0.8]
    })

# 2. UIと計算ロジック
df = get_race_data()

st.subheader("🛠 予想の微調整（適性パラメーター）")
# 以前の「重要度」を調整できるスライダー
w1 = st.slider("馬場適性の重要度", 0.0, 1.0, 0.5)
w2 = st.slider("血統スタミナの重要度", 0.0, 1.0, 0.5)
base_time = st.slider("ベースタイム(秒)", 120.0, 140.0, 130.0)

if st.button("🚀 この設定で精度重視の予想を実行"):
    # 以前の精度の高い計算式（適性ごとに重み付け）
    df['秒'] = base_time - (df['馬場適性'] * w1 * 10) - (df['血統スタミナ'] * w2 * 10) - (df['騎手補正'] * 5)
    
    # 並び替え
    result = df.sort_values(by='秒').reset_index(drop=True)
    result['着順'] = result.index + 1
    result['予想タイム'] = result['秒'].apply(lambda x: f"{int(x//60)}:{x%60:.3f}")
    
    # グラフ表示（適性の合計値をスコアとして可視化）
    result['スコア'] = (df['馬場適性'] * w1 * 10) + (df['血統スタミナ'] * w2 * 10)
    st.bar_chart(result.set_index('馬名')['スコア'])
    
    # 表表示
    st.table(result[['着順', '馬名', '予想タイム']])
    st.balloons()
