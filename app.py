import streamlit as st
import pandas as pd

st.set_page_config(page_title="UmAI 競馬予想アプリ 2026", layout="wide")
st.title("🏇 UmAI 競馬シミュレーター 2026")

# レースと各馬の能力データ
def get_race_data(race_name):
    if race_name == "2026安田記念":
        # 以前の精度の高いデータ構造を維持
        return pd.DataFrame({
            '馬名': ['レーベンスティール', 'ロングラン', 'オフトレイル', 'シックスペンス'],
            '東京適性': [0.9, 0.5, 0.6, 0.95],
            'マイル適性': [0.7, 0.6, 0.6, 0.9],
            '騎手補正': [0.8, 0.5, 0.5, 0.9]
        })
    elif race_name == "2026宝塚記念":
        return pd.DataFrame({
            '馬名': ['ドウデュース', 'ブローザホーン', 'ジャスティンパレス', 'ベラジオオペラ'],
            '阪神適性': [0.9, 0.8, 0.7, 0.9],
            'スタミナ': [0.8, 0.95, 0.9, 0.7],
            '騎手補正': [0.9, 0.7, 0.8, 0.9]
        })

# サイドバー設定
race = st.sidebar.selectbox("レースを選択", ["2026安田記念", "2026宝塚記念"])
df = get_race_data(race)

base_time = st.sidebar.slider("ベースタイム(秒)", 90.0, 150.0, 130.0)
weight = st.sidebar.slider("適性の重要度", 0.1, 1.0, 0.6)

# 予想計算ロジック
if st.button("🚀 2026年の予想を実行"):
    # 選択されたレースに応じて計算式を切り替え
    if "安田記念" in race:
        df['秒'] = base_time - (df['東京適性'] * weight) - (df['マイル適性'] * weight) - (df['騎手補正'] * 0.4)
    else:
        df['秒'] = base_time - (df['阪神適性'] * weight) - (df['スタミナ'] * weight) - (df['騎手補正'] * 0.4)
    
    df_result = df.sort_values(by='秒').reset_index(drop=True)
    df_result['予測着順'] = df_result.index + 1
    df_result['予想タイム'] = df_result['秒'].apply(lambda x: f"{int(x//60)}:{x%60:.3f}")
    
    st.success(f"{race} の予想結果")
    st.table(df_result[['予測着順', '馬名', '予想タイム']])
    st.balloons()
