import streamlit as st
import pandas as pd

st.set_page_config(page_title="UmAI 競馬予想アプリ 2026", layout="wide")
st.title("🏇 UmAI 競馬シミュレーター 2026")

# レースデータを取得する関数（ここに馬を増やせば、自動で全頭出ます！）
def get_race_data(race_name):
    if race_name == "安田記念":
        return pd.DataFrame({
            '馬名': ['レーベンスティール', 'ロングラン', 'オフトレイル', 'シックスペンス', 'ステレンボッシュ', 'トロヴァトーレ'],
            '東京適性': [0.9, 0.5, 0.6, 0.95, 0.8, 0.7],
            'マイル適性': [0.7, 0.6, 0.6, 0.9, 0.85, 0.7],
            '騎手補正': [0.8, 0.5, 0.5, 0.9, 0.9, 0.8]
        })
    elif race_name == "宝塚記念":
        return pd.DataFrame({
            '馬名': ['ドウデュース', 'ブローザホーン', 'ジャスティンパレス', 'ベラジオオペラ', 'ソールオリエンス', 'リバティアイランド'],
            '阪神適性': [0.9, 0.8, 0.7, 0.9, 0.8, 0.85],
            'スタミナ': [0.8, 0.95, 0.9, 0.7, 0.85, 0.9],
            '騎手補正': [0.9, 0.7, 0.8, 0.9, 0.75, 0.9]
        })

# レース選択ボタン
st.subheader("予測したいレースを選択")
if st.button("安田記念の予想をする"):
    st.session_state.selected_race = "安田記念"
if st.button("宝塚記念の予想をする"):
    st.session_state.selected_race = "宝塚記念"

# 選択された後の処理
if 'selected_race' in st.session_state:
    race = st.session_state.selected_race
    df = get_race_data(race)
    
    st.write(f"### {race} 予想シミュレーション")
    base_time = st.slider("ベースタイム(秒)", 90.0, 150.0, 130.0, key=f"time_{race}")
    weight = st.slider("適性の重要度", 0.1, 1.0, 0.6, key=f"weight_{race}")

    if st.button("🚀 予想を実行"):
        # 計算ロジック（列名が違うため分岐）
        if race == "安田記念":
            df['秒'] = base_time - (df['東京適性'] * weight) - (df['マイル適性'] * weight) - (df['騎手補正'] * 0.4)
        else:
            df['秒'] = base_time - (df['阪神適性'] * weight) - (df['スタミナ'] * weight) - (df['騎手補正'] * 0.4)
        
        df_result = df.sort_values(by='秒').reset_index(drop=True)
        df_result['予測着順'] = df_result.index + 1
        df_result['予想タイム'] = df_result['秒'].apply(lambda x: f"{int(x//60)}:{x%60:.3f}")
        
        st.success(f"{race} の予想結果（全出走馬）")
        # 必要な列だけ表示
        st.table(df_result[['予測着順', '馬名', '予想タイム']])
        st.balloons()
