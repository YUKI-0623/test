import streamlit as st
import pandas as pd

st.set_page_config(page_title="UmAI 競馬予想アプリ", layout="wide")
st.title("🏇 UmAI 競馬シミュレーター")
st.write("ボタンを押すと、最新ロジックでリアルタイム予想を行います！")

data = {
    '馬名': ['レーベンスティール', 'ロングラン', 'オフトレイル', 'シックスペンス', 'ステレンボッシュ', 'トロヴァトーレ'],
    '騎手': ['戸崎圭太', 'F.ゴンサルベス', '菅原明良', '武豊', 'D.レーン', 'C.ルメール'],
    '東京適性': [0.8, 0.4, 0.5, 0.9, 0.9, 0.9],
    'マイル適性': [0.6, 0.5, 0.5, 0.8, 0.9, 0.9],
    '騎手補正': [0.8, 0.5, 0.5, 0.9, 1.0, 1.0]
}
df = pd.DataFrame(data)

st.sidebar.header("シミュレーション設定")
base_time = st.sidebar.slider("ベースタイム(秒)", 90.0, 95.0, 92.07)
weight = st.sidebar.slider("適性の重要度", 0.1, 1.0, 0.6)

if st.button("🚀 安田記念 予想を実行"):
    df['秒'] = base_time - (df['東京適性'] * weight) - (df['マイル適性'] * weight) - (df['騎手補正'] * 0.4)
    df_result = df.sort_values(by='秒').reset_index(drop=True)
    df_result['予測着順'] = df_result.index + 1
    df_result['予想タイム'] = df_result['秒'].apply(lambda x: f"{int(x//60)}:{x%60:.3f}")
    
    st.success("予想完了！")
    st.table(df_result[['予測着順', '馬名', '騎手', '予想タイム']])
    
    df_result['グラフ用タイム'] = df_result['秒'].max() - df_result['秒']
    st.bar_chart(df_result.set_index('馬名')['グラフ用タイム'])

st.write("---")
st.caption("※このアプリはテスト版です。")
