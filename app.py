import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# 画面全体の基本設定
st.set_page_config(page_title="リアルタイム血統スクレイピング予想", layout="wide")
st.title("🏇 リアルタイム血統スクレイピング × 展開シミュレーター")
st.caption("【完全自律型】ネット競馬からリアルタイム取得し、独自の数式で完結するシステム")
st.markdown("---")

# ==========================================
# 1. データベース定義（血統系統 ＆ 主要騎手スコア）
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
    'ルメール': 0.98, '川田': 0.95, '武豊': 0.95, '戸崎': 0.90, '坂井': 0.90,
    '横山武': 0.88, '松山': 0.85, 'レーン': 0.95, 'モレイラ': 0.98, 'デムーロ': 0.85
}

PLACE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}

lap_summary = {
    'ミドルペース（標準・総合力勝負）': {'前半3F': 34.6, '後半3F': 35.5, 'スタミナ重み': 2.0, '騎手重み': 1.5},
    'ハイペース（持久力・タフ決着）': {'前半3F': 33.9, '後半3F': 36.3, 'スタミナ重み': 3.5, '騎手重み': 1.0},
    'スローペース（直線瞬発力・キレ勝負）': {'前半3F': 35.2, '後半3F': 34.4, 'スタミナ重み': 1.0, '騎手重み': 2.5},
    '道悪タフペース（重馬場の消耗戦）': {'前半3F': 34.5, '後半3F': 36.6, 'スタミナ重み': 4.0, '騎手重み': 1.5}
}

# ==========================================
# 2. スクレイピングエンジン（安全弁を取り付けた防御型）
# ==========================================
def fetch_live_race_data(date_str, place_code, race_num):
    list_url = f"https://race.netkeiba.com/top/race_list.html?kaisaibi={date_str}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        res = requests.get(list_url, headers=headers, timeout=5)
        res.encoding = 'euc-jp'
        soup = BeautifulSoup(res.text, "html.parser")
        
        race_id = None
        links = soup.find_all("a", href=True)
        for link in links:
            href = link['href']
            if "race_id=" in href and (f"03{place_code}" in href or f"2026{place_code}" in href):
                target_id = re.search(r'race_id=(\d+)', href).group(1)
                if int(target_id[-2:]) == int(race_num):
                    race_id = target_id
                    break
        
        if not race_id:
            # 2026年をベースにしたデフォルトIDの生成
            this_year = datetime.now().year
            race_id = f"{this_year}{place_code}0101{int(race_num):02d}"
            
        shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}&mode=blood"
        res_s = requests.get(shutuba_url, headers=headers, timeout=5)
        res_s.encoding = 'euc-jp'
        soup_s = BeautifulSoup(res_s.text, "html.parser")
        
        table = soup_s.find("table", class_="Shutuba_Table")
        if not table:
            return None, "⚠️ まだ出馬表が作成されていないか、レースが存在しません。過去の確定レースの日付（土日）を選ぶか、枠順確定までお待ちください。"
            
        rows = table.find_all("tr", class_="HorseList")
        if not rows:
            return None, "⚠️ 出馬表の枠組みはありますが、まだ出走馬が登録されていません。"
            
        scraped_data = []
        
        for row in rows:
            # 【安全対策1】枠番の取得（なければ1）
            waku_td = row.find("td", class_=re.compile(r'waku\d'))
            waku = 1
            if waku_td and 'class' in waku_td.attrs and waku_td['class']:
                waku_match = re.search(r'waku(\d)', waku_td['class'][0])
                if waku_match:
                    waku = int(waku_match.group(1))
            
            # 【安全対策2】馬番の取得（まだなければ0）
            umaban_td = row.find("td", class_="Umaban")
            umaban = 0
            if umaban_td and umaban_td.text.strip().isdigit():
                umaban = int(umaban_td.text.strip())
            
            # 【安全対策3】馬名の取得（これが取れない行はデータとして成立しないので飛ばす）
            name_span = row.find("span", class_="HorseName")
            if not name_span:
                continue
            name = name_span.text.strip()
            
            # 【安全対策4】騎手名の取得（まだ未定なら「未定」にする）
            jockey_td = row.find("td", class_="Jockey")
            jockey = "未定"
            if jockey_td and jockey_td.text.strip():
                jockey_raw = jockey_td.text.strip()
                jockey = re.sub(r'\d|▲|△|☆|★|◇|◇', '', jockey_raw).strip()
            
            # 【安全対策5】単勝オッズの取得（まだなければ10.0）
            odds_td = row.find("td", class_="Odds")
            odds = 10.0
            if odds_td and odds_td.text.strip():
                odds_text = odds_td.text.strip()
                try:
                    odds = float(odds_text) if "." in odds_text else 10.0
                except:
                    odds = 50.0
                
            # 【安全対策6】父馬の取得
            sire_link = row.find("a", href=re.compile(r'/sire/'))
            sire_name = sire_link.text.strip() if sire_link else "不明"
            
            system_name = SIRE_MAP.get(sire_name, 'その他')
            spec = BLOOD_SPEC[system_name]
            
            j_score = 0.70
            for k, v in JOCKEY_MAP.items():
                if k in jockey:
                    j_score = v
                    break
                    
            scraped_data.append({
                '枠番': waku, '馬番': umaban, '馬名': name, '父馬': sire_name, '系統': system_name,
                '騎手': jockey, '単勝': odds, '泥適性': spec['泥'], 'スタミナ': spec['スタミナ'], '騎手実績スコア': j_score
            })
            
        if not scraped_data:
            return None, "⚠️ 出走馬の情報が正しく読み込めませんでした（枠順確定前の可能性があります）。"
            
        return pd.DataFrame(scraped_data), f"🟢 【成功】全 {len(scraped_data)} 頭のデータをリアルタイム取得しました！"
        
    except Exception as e:
        return None, f"❌ 予期せぬ読み込みエラーが発生しました: {str(e)}"

# ==========================================
# 3. 画面UI（条件指定）
# ==========================================
with st.sidebar:
    st.header("📅 レース条件の指定")
    # テスト時は、すでに結果が確定している過去の「土日の日付」を入力すると100%動きます！
    tgt_date = st.date_input("開催日を選択", datetime(2026, 6, 21))
    tgt_place = st.selectbox("競馬場を選択", list(PLACE_MAP.keys()), index=7)
    tgt_race = st.selectbox("レース番号", [f"{i}R" for i in range(1, 13)], index=10)
    
    st.header("🛠 1. 馬場と展開の設定")
    
    track_condition = st.select_slider(
        "馬場状態を選択",
        options=["良馬場", "稍重", "重馬場", "不良馬場"],
        value="良馬場"
    )
    
    track_mud_map = {"良馬場": 0.0, "稍重": 3.0, "重馬場": 6.5, "不良馬場": 10.0}
    mud_val = track_mud_map[track_condition]
    
    selected_pace = st.selectbox("想定するレース展開", list(lap_summary.keys()))
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 135.0, help="1200mなら72秒、2200mなら135秒付近に調整してください")

    st.header("📈 2. 独自の重み付け調整")
    course_weight = st.slider("競馬場・コース適性の重要度", 0.0, 5.0, 2.0)
    distance_weight = st.slider("距離実績の重要度", 0.0, 5.0, 2.0)
    jockey_weight = st.slider("騎手手腕の重要度", 0.0, 5.0, 2.0)

# ==========================================
# 4. データ取得と計算
# ==========================================
date_query = tgt_date.strftime("%Y%m%d")
place_query = PLACE_MAP[tgt_place]
race_query = tgt_race.replace("R", "")

df_live, status = fetch_live_race_data(date_query, place_query, race_query)

if df_live is not None:
    st.success(status)
    st.info(f"現在の設定 ── 馬場: 【{track_condition}】 | 展開: 【{selected_pace}】")
    
    p_info = lap_summary[selected_pace]
    df = df_live.copy()
    
    # オッズから基礎実力を算出
    df['基礎実力秒'] = base_val + (df['単勝'].apply(lambda x: 0.1 if x < 2.0 else (0.5 if x < 5.0 else (1.5 if x < 15.0 else 3.0))))
    
    # 計算式
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
        st.subheader(f"📊 {tgt_date.year}年 {tgt_place} {tgt_race} 予想ランキング")
        st.table(result[['着順', '枠番', '馬番', '馬名', '父馬', '系統', '騎手', '単勝', '予想タイム']])
else:
    st.warning(status)
