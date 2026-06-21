import streamlit as st
import pandas as pd
import re
import numpy as np

# 画面全体の基本設定
st.set_page_config(page_title="JRA公式連動 × 精密展開シミュレーター", layout="wide")
st.title("🏇 JRA公式連動 × 精密展開シミュレーター")
st.caption("【JRA公式スマホサイト専用】どんなコピペのズレも自動修正する超頑丈スキャンモデル")
st.markdown("---")

# ==========================================
# 1. 血統（父馬）からの系統判別・能力傾斜
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
    st.info("JRAスマホサイト（sp.jra.jp）の出馬表画面を、文字長押しで『丸ごと全選択コピー』して右側の枠に貼り付けてください。")
    
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
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 115.0)

    st.header("📈 2. 独自の重み付け調整")
    odds_weight = st.slider("🔥 JRAリアルタイムオッズの重要度", 0.5, 5.0, 2.5)

# ==========================================
# 3. 超頑丈型・テキスト解析エンジン
# ==========================================
def parse_jra_text(text):
    if not text.strip():
        return None, "📋 上の窓にJRA公式スマホサイトのコピペテキストを貼り付けてください。"
        
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    horse_dict = {}
    ordered_keys = []
    
    current_waku = 1
    current_umaban = 1
    current_name = None
    current_jockey = "JRA騎手"
    
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        
        # 1. 馬番・枠番の自動追跡（数字が連続したら 枠番->馬番）
        if line.isdigit():
            num = int(line)
            if 1 <= num <= 18:
                if idx > 0 and lines[idx-1].isdigit():
                    current_waku = int(lines[idx-1])
                    current_umaban = num
                else:
                    current_umaban = num
                    
        # 2. 馬名の自動追跡（純粋なカタカナ行を記憶）
        elif re.match(r'^[\u30a0-\u30ff]{2,9}$', line):
            if not any(x in line for x in ["ファーム", "外車", "クラブ", "牧場", "栗東", "美浦", "単勝", "人気", "競馬", "JRA"]):
                if not any(j in line for j in ["ルメール", "モレイラ", "レーン", "デムーロ", "戸崎", "川田", "武豊"]):
                    current_name = line
                    
        # 3. 騎手の自動追跡
        elif any(x in line for x in ["（栗東）", "（美浦）", "(栗東)", "(美浦)"]):
            current_jockey = line.split("（")[0].split("(")[0].strip()
            
        # 4. 「父：」を見つけた瞬間にその馬のセットを確定ホールド
        elif "父：" in line or "父:" in line:
            father = line.replace("父：", "").replace("父:", "").strip()
            if current_name:
                key = current_name
                if key not in horse_dict:
                    horse_dict[key] = {
                        '枠番': current_waku,
                        '馬番': current_umaban,
                        '馬名': current_name,
                        '騎手': current_jockey,
                        '父馬': father,
                        '単勝': 10.0  # オッズの初期値
                    }
                    ordered_keys.append(key)
                    
        # 5. 「単勝」の文字のすぐ下にある数値をリアルタイムオッズとして正確に回収
        elif "単勝" in line:
            for k in range(idx+1, min(len(lines), idx+5)):
                if re.match(r'^\d+\.\d+$', lines[k]):
                    val = float(lines[k])
                    if ordered_keys:
                        last_key = ordered_keys[-1]
                        horse_dict[last_key]['単勝'] = val
                    break
                    
        idx += 1
        
    if ordered_keys:
        horses = [horse_dict[k] for k in ordered_keys]
        df = pd.DataFrame(horses).sort_values(by='馬番').reset_index(drop=True)
        return df, f"🟢 JRA公式から {len(df)} 頭の『リアルタイムオッズ×正確血統』を完全に仕分けました！"
        
    return None, "⚠️ 出馬表の構造が見つかりません。スマートワイスや父：ロードカナロア、単勝オッズなどが含まれるように広くコピーしてください。"

# ==========================================
# 4. メイン画面の入力フォーム
# ==========================================
st.markdown("### 📋 JRA公式スマホ画面（sp.jra.jp）のテキスト貼り付け窓")
paste_text = st.text_area(
    "JRAスマホサイトの出馬表ページを、文字長押しで『ページ全体丸ごと全選択コピー』してここに貼り付けてください。",
    height=250,
    placeholder="スマートワイス\n父：ロードカナロア\n単勝\n19.5\nのような形式のテキストが、ズレに関係なく100%正確に自動解析されます！"
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
        
        # リアルタイムオッズから基礎実力を対数計算（オッズ順に美しくタイムがバラけます）
        df['基礎実力秒'] = base_val + (np.log1p(df['単勝']) * 1.6 * odds_weight)
        
        # 予測タイムの計算シミュレーション
        df['予測秒'] = (
            df['基礎実力秒']
            + (mud_val * (1.0 - df['泥適性'])) 
            - (df['スタミナ'] * p_info['スタミナ重み']) 
        )
        
        # 同着防止用の微小分散
        df['予測秒'] += [i * 0.01 for i in range(len(df))]
        
        result = df.sort_values(by='予測秒').reset_index(drop=True)
        result['着順'] = result.index + 1
        result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📋 展開ラップ（想定）")
            st.metric(label="前半3F", value=f"{p_info['前半3F']} 秒")
            st.metric(label="後半3F", value=f"{p_info['後半3F']} 秒")
            
            # 能力スコアの可視化
            result['能力スコア'] = round((result['予測秒'].max() - result['予測秒']) * 10, 1)
            st.bar_chart(result.set_index('馬名')['能力スコア'])
            
        with col2:
            st.subheader("📊 展開シミュレーション結果")
            st.table(result[['着順', '枠番', '馬番', '馬名', '父馬', '系統', '単勝', '予想タイム']])
    else:
        st.warning(status)
else:
    st.info("💡 スマホでJRA公式（sp.jra.jp）の出馬表を開き、テキストを丸ごとコピーして上に貼り付けてみてください！")
