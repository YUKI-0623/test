import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re

# 画面全体の基本設定
st.set_page_config(page_title="穴の菊沢で夢のマイホーム × 展開シミュレーター", layout="wide")
st.title("🏇 穴の菊沢で夢のマイホーム × 展開シミュレーター")
st.caption("【URLペタッと貼るだけ型】ネット競馬からリアルタイム取得し、独自の数式で完結するシステム")
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
    'アルアイン': 'ディープ系（タフ型）', 'リアルスティール': 'ディープ系（タフ型）',
    'Siyouni': '欧州系', 'New Approach': '欧州系', 'Frankel': '欧州系',
}

BLOOD_SPEC = {
    'ステイゴールド系': {'泥': 0.95, 'スタミナ': 0.95},
    '欧州系': {'泥': 0.90, 'スタミナ': 0.90},
    'ロベルト系': {'泥': 0.85, 'スタミナ': 0.85},
    'ディープ系（タフ型）': {'泥': 0.80, 'スタミナ': 0.80},
    'ブラックタイド系': {'泥': 0.75, 'スタミナ': 0.90},
    'キングカメハメハ系': {'泥': 0.65, 'スタミナ': 0.75},
    'ディープ系': {'泥': 0.60, 'スタミナ': 0.75},
    'ハーツクライ系': {'泥': 0.65, 'スタミナ': 0.85},
    'その他': {'泥': 0.65, 'スタミナ': 0.70}
}

JOCKEY_MAP = {
    'ルメ': 0.98, 'モレイ': 0.98, '川田': 0.95, '武豊': 0.95, 'レーン': 0.95,
    '戸崎': 0.90, '坂井': 0.90, '横山武': 0.88, '横山和': 0.88, 'キング': 0.90, 'マーカ': 0.90,
    '松山': 0.85, 'デム': 0.85, '岩田望': 0.85, '鮫島': 0.85, '西村': 0.85, '菅原明': 0.85, 'ドイル': 0.85,
    '岩田康': 0.83, '津村': 0.83, '田辺': 0.83, '団野': 0.83, '北村友': 0.83, '藤岡佑': 0.83, '荻野極': 0.82,
    '三浦': 0.80, '北村宏': 0.80, '幸': 0.80, '和田': 0.80, '丹内': 0.80, '大野': 0.80, '横山典': 0.80, '武藤': 0.80,
    '菊沢': 0.85 # 夢のマイホーム補正（少し高めに設定！）
}

lap_summary = {
    'ミドルペース（標準・総合力勝負）': {'前半3F': 34.6, '後半3F': 35.5, 'スタミナ重み': 2.0, '騎手重み': 1.5},
    'ハイペース（持久力・タフ決着）': {'前半3F': 33.9, '後半3F': 36.3, 'スタミナ重み': 3.5, '騎重み': 1.0},
    'スローペース（直線瞬発力・キレ勝負）': {'前半3F': 35.2, '後半3F': 34.4, 'スタミナ重み': 1.0, '騎手重み': 2.5},
    '道悪タフペース（重馬場の消耗戦）': {'前半3F': 34.5, '後半3F': 36.6, 'スタミナ重み': 4.0, '騎手重み': 1.5}
}

# ==========================================
# 2. サイドバーUI（劇的にシンプル化）
# ==========================================
with st.sidebar:
    st.header("🔗 レースURLの入力")
    race_url = st.text_input(
        "ネット競馬の「出馬表」URLを貼り付けてください",
        value="https://race.netkeiba.com/race/shutuba.html?race_id=202605030211",
        help="例：https://race.netkeiba.com/race/shutuba.html?race_id=..."
    )
    
    st.header("🛠 1. 馬場と展開の設定")
    track_condition = st.select_slider(
        "馬場状態を選択",
        options=["良馬場", "稍重", "重馬場", "不良馬場"],
        value="良馬場"
    )
    
    track_mud_map = {"良馬場": 0.0, "稍重": 3.0, "重馬場": 6.5, "不良馬場": 10.0}
    mud_val = track_mud_map[track_condition]
    
    selected_pace = st.selectbox("想定するレース展開", list(lap_summary.keys()))
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 135.0)

    st.header("📈 2. 独自の重み付け調整")
    course_weight = st.slider("競馬場・コース適性の重要度", 0.0, 5.0, 2.0)
    distance_weight = st.slider("距離実績の重要度", 0.0, 5.0, 2.0)
    jockey_weight = st.slider("騎手手腕の重要度", 0.0, 5.0, 2.0)

# ==========================================
# 3. 超強力・URLダイレクト解析エンジン
# ==========================================
def fetch_race_data_by_url(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # URLから12桁のレースIDをぶち抜く
    race_id_match = re.search(r'race_id=(\d{12})', url)
    if not race_id_match:
        return None, "⚠️ URLの形式が正しくありません。ネット競馬の出馬表URLをそのまま貼り付けてください。"
    
    race_id = race_id_match.group(1)
    # 血統モードを強制指定してダイレクトにアクセス
    shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}&mode=blood"
    
    try:
        res = requests.get(shutuba_url, headers=headers, timeout=5)
        res.encoding = 'EUC-JP'  # ★文字化けを根絶する絶対的エンコード固定
        soup = BeautifulSoup(res.text, "html.parser")
        
        # レース名をタイトルから自動取得
        page_title = soup.title.text if soup.title else ""
        race_title = page_title.split("|")[0].strip() if "|" in page_title else "ターゲットレース"
        
        table = soup.find("table", class_="Shutuba_Table")
        if not table:
            return None, "⚠️ 出馬表のテーブルが見つかりません。枠順がまだ未発表の可能性があります。"
            
        rows = table.find_all("tr", class_="HorseList")
        scraped_data = []
        
        for row in rows:
            waku_td = row.find("td", class_=re.compile(r'waku\d'))
            waku = 1
            if waku_td and 'class' in waku_td.attrs and waku_td['class']:
                waku_match = re.search(r'waku(\d)', waku_td['class'][0])
                if waku_match:
                    waku = int(waku_match.group(1))
            
            umaban_td = row.find("td", class_="Umaban")
            umaban = 0
            if umaban_td and umaban_td.text.strip().isdigit():
                umaban = int(umaban_td.text.strip())
            
            name_span = row.find("span", class_="HorseName")
            if not name_span:
                continue
            name = name_span.text.strip()
            
            jockey_td = row.find("td", class_="Jockey")
            jockey = "未定"
            if jockey_td and jockey_td.text.strip():
                jockey_raw = jockey_td.text.strip()
                jockey = re.sub(r'\d|▲|△|☆|★|◇|◇', '', jockey_raw).strip()
            
            odds_td = row.find("td", class_="Odds")
            odds = 10.0
            if odds_td and odds_td.text.strip():
                odds_text = odds_td.text.strip()
                try:
                    odds = float(odds_text) if "." in odds_text else 10.0
                except:
                    odds = 50.0
                
            sire_link = row.find("a", href=re.compile(r'/sire/'))
            sire_name = sire_link.text.strip() if sire_link else "不明"
            
            system_name = SIRE_MAP.get(sire_name, 'その他')
            spec = BLOOD_SPEC[system_name]
            
            j_score = 0.75
            for k, v in JOCKEY_MAP.items():
                if k in jockey:
                    j_score = v
                    break
                    
            scraped_data.append({
                '枠番': waku, '馬番': umaban, '馬名': name, '父馬': sire_name, '系統': system_name,
                '騎手': jockey, '単勝': odds, '泥適性': spec['泥'], 'スタミナ': spec['スタミナ'], '騎手実績スコア': j_score
            })
            
        if not scraped_data:
            return None, "⚠️ 出走馬の情報を読み込めませんでした。"
            
        return pd.DataFrame(scraped_data), f"🟢 【成功】「{race_title}」のデータを100%綺麗に解析しました！"
        
    except Exception as e:
        return None, f"❌ エラー: {str(e)}"

# ==========================================
# 4. 計算とシミュレーション実行
# ==========================================
if race_url:
    df_live, status = fetch_race_data_by_url(race_url)
    
    if df_live is not None:
        st.success(status)
        st.info(f"現在の設定 ── 馬場: 【{track_condition}】 | 展開: 【{selected_pace}】")
        
        p_info = lap_summary[selected_pace]
        df = df_live.copy()
        
        df['基礎実力秒'] = base_val + (df['単勝'].apply(lambda x: 0.1 if x < 2.0 else (0.5 if x < 5.0 else (1.5 if x < 15.0 else 3.0))))
        
        df['予測秒'] = (
            df['基礎実力秒']
            + (mud_val * (1.1 - df['泥適性'])) 
            - (df['スタミナ'] * p_info['スタミナ重み']) 
            - (df['泥適性'] * course_weight)      
            - (df['スタミナ'] * distance_weight)  
            - (df['騎手実績スコア'] * (p_info['騎手重み'] + jockey_weight))
        )
        
        result = df.sort_values(by='予測秒').reset_index(drop=True)
        result['着順'] = result.index + 1
        result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📋 展開ラップ（参考）")
            st.metric(label="前半3F", value=f"{p_info['前半3F']} 秒")
            st.metric(label="後半3F", value=f"{p_info['後半3F']} 秒")
            
            result['能力スコア'] = result['予測秒'].max() - result['予測秒']
            st.bar_chart(result.set_index('馬名')['能力スコア'])
            
        with col2:
            st.subheader("📊 展開シミュレーションランキング")
            st.table(result[['着順', '枠番', '馬番', '馬名', '父馬', '系統', '騎手', '単勝', '予想タイム']])
    else:
        st.warning(status)
