import streamlit as st
import pandas as pd

st.set_page_config(page_title="泥んこ血統AI・カスタマイズ版", layout="wide")
st.title("🏇 泥んこ血統AI & 予想タイム調整")

# 1. データベース設定
def get_base_data():
    return pd.DataFrame({
        '馬名': ['ダノンデサイル', 'ミュージアムマイル', 'コスモキュランダ', 'ジューンテイク', 'クロワデュノール', 'ビザンチンドリーム', 'レガレイラ', 'スティンガーグラス', 'シュガークン', 'ミクニインスパイア', 'シンエンペラー', 'マイユニバース', 'ミステリーウェイ', 'ファミリータイム', 'シェイクユアハート', 'メイショウタバル', 'マイネルエンペラー', 'タガノデュード'],
        '泥適性': [0.9, 0.5, 0.8, 0.6, 0.7, 0.85, 0.6, 0.7, 0.9, 0.5, 0.8, 0.6, 0.7, 0.75, 0.6, 0.95, 0.9, 0.6],
        'スタミナ': [0.8, 0.7, 0.9, 0.85, 0.7, 0.8, 0.95, 0.8, 0.7, 0.6, 0.9, 0.7, 0.8, 0.85, 0.75, 0.9, 0.95, 0.7],
        '騎手補正': [0.9, 0.7, 0.8, 0.75, 0.9, 0.8, 0.95, 0.7, 0.85, 0.6, 0.9, 0.65, 0.7, 0.75, 0.7, 0.95, 0.8, 0.65]
    })

# 2. サイドバーで自由に動かす（リアルタイム調整）
st.sidebar.header("🛠 予想タイムの調整")
mud_val = st.sidebar.slider("泥の影響（タイム加算）", 0.0, 10.0, 5.0)
stamina_val = st.sidebar.slider("スタミナの重要度", 0.0, 5.0, 2.0)
base_val = st.sidebar.slider("ベースタイム(秒)", 130.0, 150.0, 138.0)

# 3. 計算ロジック
df = get_base_data()

# スライダーの値を使って計算（ここを動かすと結果が変わります）
df['予測秒'] = base_val + (mud_val * (1.1 - df['泥適性'])) - (df['スタミナ'] * stamina_val)

# ソートして着順を確定
result = df.sort_values(by='予測秒').reset_index(drop=True)
result['着順'] = result.index + 1
result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")

# 4. 表示
st.subheader("📊 リアルタイム予想ランキング")

# グラフとテーブルで全頭表示
col1, col2 = st.columns([1, 2])
with col1:
    # タイム差をわかりやすくグラフ化
    result['タイム差'] = result['予測秒'].max() - result['予測秒']
    st.bar_chart(result.set_index('馬名')['タイム差'])
with col2:
    st.table(result[['着順', '馬名', '予想タイム', '泥適性', 'スタミナ']])
