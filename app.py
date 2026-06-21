import streamlit as st
import pandas as pd
import re
import numpy as np

# 画面全体の基本設定
st.set_page_config(page_title="JRA公式テキスト連動型 展開シミュレーター", layout="wide")
st.title("🏇 JRA公式テキスト連動型 展開シミュレーター")
st.caption("【JRA公式スマホサイト対応】ブロック・文字化けを完全に回避するコピペ特化型モデル")
st.markdown("---")

# ==========================================
# 1. 血統（父馬）からの系統判別ロジック
# ==========================================
def predict_system_from_father(father_name):
    fn = father_name.strip()
    if any(x in fn for x in ['ディープ', 'ハーツ', 'キタサン', 'ブラックタイド', 'オルフェ', 'ゴールドシップ', 'ステイゴールド', 'ダイワメジャー', 'スワーヴ', 'ジャスタウェイ']):
        return 'サンデーサイレンス系', 0.65, 0.90  # (泥適性, スタミナ)
    if any(x in fn for x in ['キングカメハメハ', 'カナロア', 'ドゥラメンテ', 'レイデオロ', 'ルーラーシップ', 'ロードカナロア']):
        return 'キングカメハメハ系', 0.75, 0.80
    if any(x in fn for x in ['エピファネイア', 'モーリス', 'スクリーンヒーロー', 'シンボリクリスエス', 'ロベルト']):
        return 'ロベルト系（タフ）', 0.90, 0.85
    if any(x in fn for x in ['ハービンジャー', 'バゴ', 'クロフネ', 'フレンチ', 'キズナ']):
        return '欧州・ノーザンダンサー系', 0.85, 0.85
    return 'その他系統', 0.70, 0.75

# ==========================================
# 2. サイドバーUI
# ==========================================
with st.sidebar:
    st.header("📱 JRA公式コピペエリア")
    st.info("JRAスマホサイト（sp.jra.jp）の出馬表画面を、文字長押しで『丸ごと全選択コピー』して右側の枠に貼り付けてください！")
    
    st.header("🛠 1. 馬場と展開の設定")
    track_condition = st.select_slider("馬場状態を選択", options=["良馬場", "稍重", "重馬場", "不良馬場"], value="良馬場")
    track_mud_map = {"良馬場": 0.0, "稍重": 2.0, "重馬場": 5.0, "不良馬場": 8.0}
    mud_val = track_mud_map[track_condition]
    
    lap_summary = {
        'ミドルペース（標準・総合力勝負）': {'前半3F': 34.6, '後半3F': 35.5, 'スタミナ重み': 2.0},
        'ハイペース（持久力・タフ決着）': {'前半3F': 33.9, '後半3F': 36.3, 'スタミナ重み': 3.5},
        'スローペース（直線瞬発力・キレ勝負）': {'前半3F': 35.2, '後半3F': 34.4, 'スタミナ重み': 1.0}
    }
    selected_pace = st.selectbox("想定するレース展開", list(lap_summary.keys()))
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 95.0)

    st.header("📈 2. 独自の重み付け調整")
    odds_weight = st.slider("🔥 JRAリアルタイムオッズの重要度", 0.5, 5.0, 2.5)

# ==========================================
# 3. JRAスマホ特化型・テキスト解析エンジン
# ==========================================
def parse_jra_text(text):
    if not text.strip():
        return None, "📋 上の窓にJRA公式スマホサイトのテキストを貼り付けてください。"
        
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    horses = []
    
    for idx, line in enumerate(lines):
        if "父：" in line or "父:" in line:
            father = line.replace("父：", "").replace("父:", "").strip()
            
            name = "不明"
            for j in range(idx-1, max(-1, idx-7), -1):
                if re.match(r'^[\u30a0-\u30ff]{2,9}$', lines[j]):
                    if not any(x in lines[j] for x in ["ファーム", "組合", "会社", "牧場", "栗東", "美浦", "単勝", "人気"]):
                        name = lines[j]
                        break
            
            if name == "不明":
                continue
                
            umaban = len(horses) + 1
            for j in range(idx-8, idx):
                if j >= 0 and lines[j].isdigit():
                    u_num = int(lines[j])
                    if 1 <= u_num <= 18:
                        umaban = u_num

            jockey = "JRA騎手"
            for j in range(idx-3, idx+3):
                if j >= 0 and j < len(lines) and ("（栗東）" in lines[j] or "（美浦）" in lines[j] or "(栗東)" in lines[j] or "(美浦)" in lines[j]):
                    jockey = lines[j].split("（")[0].split("(")[0].strip()
            
            odds = 10.0
            for k in range(idx+1, min(len(lines), idx+8)):
                if re.match(r'^\d+\.\d+$', lines[k]):
                    val = float(lines[k])
                    if val > 1.0 and (val < 50.0 or val > 60.0):
                        odds = val
                        break
            
            if name not in [h['馬名'] for h in horses]:
                syst, mud_suit, stamina_suit = predict_system_from_father(father)
                horses.append({
                    '馬番': umaban,
                    '馬名': name,
                    '父馬': father,
                    '系統': syst,
                    '騎手': jockey,
                    '単勝': odds,
                    '泥適性': mud_suit,
                    'スタミナ': stamina_suit
                })
                
    if horses:
        df = pd.DataFrame(horses).sort_values(by='馬番').reset_index(drop=True)
        def assign_waku(uma, total):
            if total <= 8: return uma
            if uma <= 2: return 1
            if uma <= 4: return 2
            if uma <= 6: return 3
            if uma <= 8: return 4
            if uma <= 10: return 5
            if uma <= 12: return 6
            if uma <= 14: return 7
            return 8
        df['枠番'] = df['馬番'].apply(lambda x: assign_waku(x, len(df)))
        return df, f"🟢 JRA公式から {len(df)} 頭の『リアルタイムオッズ×血統データ』の抽出に成功しました！"
        
    return None, "⚠️ JRA公式のテキスト構造が見つかりません。画面を広く全選択コピーして貼り付けてください。"

# ==========================================
# 4. メメイン画面の入力フォーム
# ==========================================
st.markdown("### 📋 JRA公式スマホ画面（sp.jra.jp）のテキスト貼り付け窓")
paste_text = st.text_area(
    "JRAスマホサイトの出馬表（スクショ12枚目の画面など）で、ページ全体を丸ごとコピーしてここに貼り付けてください",
    height=250,
    placeholder="スマートワイス\n父：ロードカナロア\n19.5\nのような形式のテキストが自動解析されます！"
)

# ==========================================
# 5. 計算とシミュレーション実行
# ==========================================
if paste_text:
    df_live, status = parse_jra_text(paste_text)
    
    if df_live is not None:
        st.success(status)
        p_info = lap_summary[selected_pace]
        df = df_live.copy()
        
        df['基礎実力秒'] = base_val + (np.log1p(df['単勝']) * 1.6 * odds_weight)
        
        df['予測秒'] = (
            df['基礎実力秒']
            + (mud_val * (1.0 - df['泥適性'])) 
            - (df['スタミナ'] * p_info['スタミナ重み']) 
        )
        
        df['予測秒'] += [i * 0.01 for i in range(len(df))]
        
        result = df.sort_values(by='予測秒').reset_index(drop=True)
        result['着順'] = result.index + 1
        result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📋 展開ラップ（想定）")
            st.metric(label="前半3F", value=f"{p_info['前半3F']} 秒")
            st.metric(label="後半3F", value=f"{p_info['後半3F']} 秒")
            
            result['能力スコア'] = round((result['予測秒'].max() - result['予測秒']) * 10, 1)
            st.bar_chart(result.set_index('馬名')['能力スコア'])
            
        with col2:
            st.subheader("📊 展開シミュレーション結果")
            st.table(result[['着順', '枠番', '馬番', '馬名', '父馬', '系統', '単勝', '予想タイム']])
    else:
        st.warning(status)
else:
    st.info("💡 スマホでJRA公式（sp.jra.jp）の出馬表を開き、テキストを丸ごとコピーして上に貼り付けてみてください！")
