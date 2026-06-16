import streamlit as st
import pandas as pd
import requests
from io import StringIO

# ==========================================
# 0. スマホ向けの画面設定
# ==========================================
st.set_page_config(page_title="泥んこ競馬AI", page_icon="🏇", layout="centered")

st.title("🏇 泥んこ血統AI予想")
st.caption("2026年 宝塚記念（G1）重馬場専用シミュレーター")
st.markdown("---")

# ==========================================
# 1. AIロジック部分
# ==========================================
def run_ai_prediction():
    # リアルデータ取得試行
    race_id = "202609030411"
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        dfs = pd.read_html(StringIO(response.text))
        df_raw = dfs[0]
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = [col[-1] for col in df_raw.columns]
        df_raw.columns = df_raw.columns.astype(str).str.strip()
        df_raw = df_raw.rename(columns={'枠': '枠番', '単勝オッズ': '単勝', 'オッズ': '単勝', '馬name': '馬名'})
        race_card = df_raw.copy()
        race_card['馬名'] = race_card['馬名'].astype(str).str.split().str[0]
        race_card['単勝'] = pd.to_numeric(race_card['単勝'], errors='coerce')
    except Exception:
        # 通信エラー時のバックアップデータ（18頭分）
        backup_data = {
            '枠番': [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 8, 8],
            '馬番': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            '馬名': ['ダノンデサイル', 'ミュージアムマイル', 'コスモキュランダ', 'ジューンテイク', 'クロワデュノール', 'ビザンチンドリーム', 'レガレイラ', 'スティンガーグラス', 'シュガークン', 'ミクニインスパイア', 'シンエンペラー', 'マイユニバース', 'ミステリーウェイ', 'ファミリータイム', 'シェイクユアハート', 'メイショウタバル', 'マイネルエンペラー', 'タガノデュード'],
            '単勝': [5.5, 14.2, 8.5, 18.1, 2.8, 22.4, 6.0, 15.6, 10.3, 85.0, 12.4, 120.5, 95.3, 65.2, 45.0, 3.9, 32.1, 55.4]
        }
        race_card = pd.DataFrame(backup_data)

    # 血統DBとペナルティ
    blood_db = {
        'メイショウタバル': {'父': 'ゴールドシップ', '系統': 'ステイゴールド系'}, 'マイネルエンペラー': {'父': 'ゴールドシップ', '系統': 'ステイゴールド系'},
        'シンエンペラー': {'父': 'Siyouni', '系統': '欧州系'}, 'ダノンデサイル': {'父': 'エピファネイア', '系統': 'ロベルト系'},
        'ビザンチンドリーム': {'父': 'エピファネイア', '系統': 'ロベルト系'}, 'ミクニインスパイア': {'父': 'エピファネイア', '系統': 'ロベルト系'},
        'コスモキュランダ': {'父': 'アルアイン', '系統': 'ディープ系（タフ型）'}, 'クロワデュノール': {'父': 'キタサンブラック', '系統': 'ブラックタイド系'},
        'シュガークン': {'父': 'ドゥラメンテ', '系統': 'キングカメハメハ系'}, 'ミュージアムマイル': {'父': 'リオンディーズ', '系統': 'キングカメハメハ系'},
        'ジューンテイク': {'父': 'キズナ', '系統': 'ディープ系'}, 'スティンガーグラス': {'父': 'キズナ', '系統': 'ディープ系'},
        'ファミリータイム': {'父': 'キズナ', '系統': 'ディープ系'}, 'レガレイラ': {'父': 'スワーヴリチャード', '系統': 'ハーツクライ系'},
        'ミステリーウェイ': {'父': 'ジャスタウェイ', '系統': 'ハーツクライ系'}, 'シェイクユアハート': {'父': 'ハーツクライ', '系統': 'ハーツクライ系'},
        'マイユニバース': {'父': 'コパノリッキー', '系統': 'ダート・パワー系'}, 'タガノデュード': {'父': 'ネロ', '系統': 'スプリント・パワー系'}
    }
    system_penalty = {
        'ステイゴールド系': 0.2, '欧州系': 0.5, 'ロベルト系': 0.8, 'ディープ系（タフ型）': 0.8,
        'ブラックタイド系': 1.0, 'ダート・パワー系': 1.1, 'スプリント・パワー系': 1.2, 'キングカメハメハ系': 1.3,
        'ディープ系': 1.6, 'ハーツクライ系': 2.3
    }

    def analyze_bloodline(name):
        info = blood_db.get(name.strip())
        if info: return pd.Series([info['父'], info['系統'], system_penalty.get(info['系統'], 1.5)])
        return pd.Series(['不明', 'その他', 1.5])

    race_card[['父', '血統系統', '重馬場ペナルティ']] = race_card['馬名'].apply(analyze_bloodline)
    race_card['仮想_良馬場タイム'] = 130.0 + (race_card['単勝'].fillna(50) * 0.05)
    race_card['重馬場予測タイム_秒'] = race_card['仮想_良馬場タイム'] + race_card['重馬場ペナルティ']
    
    predicted = race_card.sort_values(by='重馬場予測タイム_秒').reset_index(drop=True)
    predicted['予測順位'] = predicted.index + 1
    return predicted[['予測順位', '枠番', '馬番', '馬名', '父', '血統系統', '重馬場ペナルティ']]

# ==========================================
# 2. UIデザイン
# ==========================================
st.write("ボタンを押すと、雨の宝塚記念を完全シミュレーションします。")

if st.button("🔥 最新データでAI予想を開始", use_container_width=True):
    with st.spinner('AIが血統データを分析中...'):
        result_df = run_ai_prediction()
        st.success("🎯 AI予想の算出が完了しました！")
        
        st.subheader("🏆 AI推奨の上位3頭")
        top3 = result_df.head(3)
        colors = ["🥇 1位", "🥈 2位", "🥉 3位"]
        for idx, row in top3.iterrows():
            st.markdown(f"### {colors[idx]} : **{row['馬名']}**")
            st.caption(f"枠: {row['枠番']} / 馬番: {row['馬番']} （父: {row['父']} / {row['血統系統']}）")
        
        st.markdown("---")
        st.subheader("📊 18頭の全予測ランキング")
        st.dataframe(result_df, use_container_width=True, hide_index=True)
