import streamlit as st
import pandas as pd
import re
import numpy as np

# 画面全体の基本設定
st.set_page_config(page_title="ガチ実績連動 × 展開シミュレーター", layout="wide")
st.title("🏇 ガチ実績連動 × 展開シミュレーター")
st.caption("【エラー修正＆JRAコピペ完全最適化版】スマホからのコピペをミリ単位で解析する決定版")
st.markdown("---")

# ==========================================
# 1. データベース定義
# ==========================================
SIRE_MAP = {
    'ゴールドシップ': 'ステイゴールド系', 'オルフェーヴル': 'ステイゴールド系', 'ステイゴールド': 'ステイゴールド系',
    'エピファネイア': 'ロベルト系', 'モーリス': 'ロベルト系', 'スクリーンヒーロー': 'ロベルト系',
    'キタサンブラック': 'ブラックタイド系', 'ブラックタイド': 'ブラックタイド系',
    'ドゥラメンテ': 'キングカメハメハ系', 'ロードカナロア': 'キングカメハメハ系', 'キングカメハメハ': 'キングカメハメハ系', 'リオンディーズ': 'キングカメハメハ系',
    'キズナ': 'ディープ系', 'ディープインパクト': 'ディープ系', 'コントレイル': 'ディープ系',
    'スワーヴリチャード': 'ハーツクライ系', 'ハーツクライ': 'ハーツクライ系', 'ジャスタウェイ': 'ハーツクライ系',
}

BLOOD_SPEC = {
    'ステイゴールド系': {'泥': 0.95, 'スタミナ': 0.95},
    'ロベルト系': {'泥': 0.85, 'スタミナ': 0.85},
    'ブラックタイド系': {'泥': 0.75, 'スタミナ': 0.90},
    'キングカメハメハ系': {'泥': 0.65, 'スタミナ': 0.75},
    'ディープ系': {'泥': 0.60, 'スタミナ': 0.75},
    'ハーツクライ系': {'泥': 0.65, 'スタミナ': 0.85},
    'その他': {'泥': 0.65, 'スタミナ': 0.70}
}

JOCKEY_MAP = {
    'ルメ': 0.98, 'モレイ': 0.98, '川田': 0.95, '武豊': 0.95, 'レーン': 0.95,
    '戸崎': 0.90, '坂井': 0.90, '横山武': 0.88, '横山和': 0.88, '松山': 0.85,
    '幸': 0.80, 'デム': 0.85, '岩田望': 0.85, '鮫島': 0.85, '西村': 0.85,
}

lap_summary = {
    'ミドルペース（標準・総合力勝負）': {'前半3F': 34.6, '後半3F': 35.5, 'スタミナ重み': 2.0, '騎手重み': 1.5},
    'ハイペース（持久力・タフ決着）': {'前半3F': 33.9, '後半3F': 36.3, 'スタミナ重み': 3.5, '騎手重み': 1.0},
    'スローペース（直線瞬発力・キレ勝負）': {'前半3F': 35.2, '後半3F': 34.4, 'スタミナ重み': 1.0, '騎手重み': 2.5}
}

# ==========================================
# 2. サイドバーUI
# ==========================================
with st.sidebar:
    st.header("📋 JRA公式コピペエリア")
    st.info("💡 スマホでJRAスマホサイト（sp.jra.jp）の出馬表を開き、【全選択】してコピーし、下の枠に貼り付けてください。")
    paste_text = st.text_area("📋 ここに出馬表のテキストを貼り付け", height=200, placeholder="スマートワイス\n父：ロードカナロア\n...")

    st.header("🛠 1. 馬場と展開の設定")
    track_condition = st.select_slider("馬場状態を選択", options=["良馬場", "稍重", "重馬場", "不良馬場"], value="良馬場")
    track_mud_map = {"良馬場": 0.0, "稍重": 3.0, "重馬場": 6.5, "不良馬場": 10.0}
    mud_val = track_mud_map[track_condition]
    
    selected_pace = st.selectbox("想定するレース展開", list(lap_summary.keys()))
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 95.0)

    st.header("📈 2. 独自の重み付け調整")
    history_weight = st.slider("🔥 過去実績（オッズ傾斜）の重要度", 0.0, 5.0, 2.5)
    course_weight = st.slider("血統・コース適性の重要度", 0.0, 5.0, 2.0)
    distance_weight = st.slider("血統・距離実績の重要度", 0.0, 5.0, 2.0)
    jockey_weight = st.slider("騎手手腕の重要度", 0.0, 5.0, 2.0)

# ==========================================
# 3. 超高精度・索敵型コピペ解析エンジン
# ==========================================
def parse_pasted_text(text):
    if not text.strip():
        return None, "📋 左側の入力欄に出馬表のテキストを貼り付けてください。"
        
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    parsed_horses = []
    
    # 「父：」がある行をすべての基準点にする
    father_indices = [i for i, line in enumerate(lines) if "父：" in line or "父:" in line]
    
    if not father_indices:
        return None, "⚠️ 『父：〇〇』という文字が見つかりません。JRA公式の出馬表（馬名やオッズが含まれる部分）を広くコピーしてください。"
        
    for idx in father_indices:
        father = lines[idx].replace("父：", "").replace("父:", "").strip()
        horse_name = "不明"
        jockey = "未定"
        
        # 【上方向へ索敵】馬名と騎手を探す
        for search_up in range(idx - 1, max(-1, idx - 10), -1):
            t = lines[search_up]
            # 純粋なカタカナ2〜9文字（馬名の特徴）
            if re.match(r'^[\u30a0-\u30ff][\u30a0-\u30ff\u30fc・]{1,9}$', t):
                if not any(x in t for x in ["ファーム", "単勝", "人気", "競馬", "クラス", "倍"]):
                    horse_name = t
                    # 馬名が見つかったら、その直後から「父：」の間にある漢字（騎手名）を探す
                    for k in range(search_up + 1, idx):
                        possible_jockey = lines[k].replace(" ", "").replace("　", "")
                        if re.match(r'^[\u4e00-\u9faf]{2,4}$', possible_jockey) and "東" not in possible_jockey and "浦" not in possible_jockey:
                            jockey = possible_jockey[:2] # マッピング用に先頭2文字を抽出
                            break
                    break
        
        # 【下方向へ索敵】オッズを探す
        odds = 10.0
        for search_down in range(idx + 1, min(len(lines), idx + 10)):
            t = lines[search_down]
            if re.match(r'^\d+\.\d+$', t):
                odds = float(t)
                break
                
        if horse_name != "不明":
            syst = 'その他'
            for k in SIRE_MAP.keys():
                if k in father:
                    syst = SIRE_MAP[k]
                    break
            
            # 💡【重要】コピペでは「過去5走データ」が物理的に存在しないため、一律化を防ぐ
            # オッズ（人気順）に比例して、リアルな初期着順の傾きを自動で配分するロジックを追加
            if odds < 3.0: avg_rank = 2.1
            elif odds < 6.0: avg_rank = 3.4
            elif odds < 12.0: avg_rank = 4.8
            elif odds < 30.0: avg_rank = 6.5
            else: avg_rank = 8.8
            
            umaban = len(parsed_horses) + 1
            waku = (umaban - 1) // 2 + 1
            if waku > 8: waku = 8
            
            j_score = 0.75
            for k, v in JOCKEY_MAP.items():
                if k in jockey:
                    j_score = v
                    break
                    
            parsed_horses.append({
                '枠番': waku, '馬番': umaban, '馬名': horse_name,
                '騎手': jockey, '単勝': odds, '騎手実績スコア': j_score,
                '父馬': father, '系統': syst, 
                '泥適性': BLOOD_SPEC.get(syst, {'泥': 0.65, 'スタミナ': 0.70})['泥'],
                'スタミナ': BLOOD_SPEC.get(syst, {'泥': 0.65, 'スタミナ': 0.70})['スタミナ'],
                '過去5走平均着順': avg_rank
            })
            
    if parsed_horses:
        return pd.DataFrame(parsed_horses), f"🟢 JRA公式データから {len(parsed_horses)} 頭を精密に自動抽出しました！"
    return None, "⚠️ データの抽出に失敗しました。出馬表のテキストをもう少し広めにコピーしてみてください。"

# ==========================================
# 4. 計算・シミュレーション出力
# ==========================================
if paste_text:
    df, status = parse_pasted_text(paste_text)
    
    if df is not None:
        st.success(status)
        p_info = lap_summary[selected_pace]
        
        # 基礎実力秒の算出
        df['基礎実力秒'] = base_val + (df['単勝'].apply(lambda x: 0.0 if x < 2.0 else (0.5 if x < 5.0 else (1.5 if x < 10.0 else (3.0 if x < 30.0 else 5.0)))))
        
        # 予測タイム計算数理モデル
        df['予測秒'] = (
            df['基礎実力秒']
            + ((df['過去5走平均着順'] - 7.0) * 0.25 * history_weight)
            + (mud_val * (1.1 - df['泥適性']) * 0.2) 
            - (df['スタミナ'] * p_info['スタミナ重み']) 
            - (df['泥適性'] * course_weight)      
            - (df['スタミナ'] * distance_weight)  
            - (df['騎手実績スコア'] * (p_info['騎手重み'] + jockey_weight) * 0.5)
        )
        
        # 微小なランダム分散で完全同着を防止
        df['予測秒'] += [i * 0.01 for i in range(len(df))]
        
        result = df.sort_values(by='予測秒').reset_index(drop=True)
        result['着順'] = result.index + 1
        result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")
        
        # 能力スコアの可視化調整（50基準）
        result['能力スコア'] = round((result['予測秒'].max() - result['予測秒']) * 10 + 50, 1)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📋 展開ラップ（想定）")
            st.metric(label="前半3F", value=f"{p_info['前半3F']} 秒")
            st.metric(label="後半3F", value=f"{p_info['後半3F']} 秒")
            st.bar_chart(result.set_index('馬名')['能力スコア'])
            
        with col2:
            st.subheader("📊 展開シミュレーション結果")
            st.table(result[['着順', '枠番', '馬番', '馬名', '父馬', '系統', '騎手', '単勝', '予想タイム']])
    else:
        st.warning(status)
else:
    st.info("👈 左側のメニューにある入力欄に、JRA公式の出馬表テキストを貼り付けてください。")
