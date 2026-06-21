import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import numpy as np

# 画面全体の基本設定
st.set_page_config(page_title="深層戦績連動 × ガチ指数シミュレーター", layout="wide")
st.title("🏇 深層戦績連動 × ガチ指数シミュレーター")
st.caption("【完全自動認識モデル】URLから今回の条件を自動特定し、過去5走の全戦績とミリ単位でマッチング")
st.markdown("---")

# ==========================================
# 1. データベース・定数定義
# ==========================================
JYO_MAP = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
    '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
}

SIRE_MAP = {
    'ゴールドシップ': 'ステイゴールド系', 'オルフェーヴル': 'ステイゴールド系', 'ステイゴールド': 'ステイゴールド系',
    'エピファネイア': 'ロベルト系', 'モーリス': 'ロベルト系', 'スクリーンヒーロー': 'ロベルト系',
    'キタサンブラック': 'ブラックタイド系', 'ブラックタイド': 'ブラックタイド系',
    'ドゥラメンテ': 'キングカメハメハ系', 'ロードカナロア': 'キングカメハメハ系', 'キングカメハメハ': 'キングカメハメハ系',
    'キズナ': 'ディープ系', 'ディープインパクト': 'ディープ系', 'コントレイル': 'ディープ系',
    'スワーヴリチャード': 'ハーツクライ系', 'ハーツクライ': 'ハーツクライ系', 'ジャスタウェイ': 'ハーツクライ系'
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
    'デム': 0.85, '岩田望': 0.85, '鮫島': 0.85, '西村': 0.85, '菅原明': 0.85,
    '岩田康': 0.83, '津村': 0.83, '田辺': 0.83, '幸': 0.80, '横山典': 0.80
}

lap_summary = {
    'ミドルペース（標準・総合力勝負）': {'スタミナ重み': 2.0, '騎手重み': 1.5},
    'ハイペース（持久力・タフ決着）': {'スタミナ重み': 3.5, '騎手重み': 1.0},
    'スローペース（直線瞬発力・キレ勝負）': {'スタミナ重み': 1.0, '騎手重み': 2.5}
}

# ==========================================
# 2. サイドバーUI
# ==========================================
with st.sidebar:
    st.header("🔗 レースURL")
    race_url = st.text_input(
        "ネット競馬の「出馬表」URL",
        value="https://race.netkeiba.com/race/shutuba.html?race_id=202605030211"
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
    base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 100.0)

    st.header("📈 2. 実績データの重要度（重み付け）")
    history_weight = st.slider("🔥 過去5走・全体実績の重み", 0.0, 5.0, 2.5)
    course_weight = st.slider("🗺 今回の競馬場・適性の重み", 0.0, 5.0, 3.0)
    distance_weight = st.slider("📏 今回の距離・適性の重み", 0.0, 5.0, 3.0)
    baba_weight = st.slider("☔ 今回の馬場状態・適性の重み", 0.0, 5.0, 2.5)
    jockey_weight = st.slider("🏇 騎手手腕の重み", 0.0, 5.0, 2.0)

# ==========================================
# 3. オッズ取得用補助関数
# ==========================================
def fetch_real_odds(race_id):
    odds_url = f"https://race.netkeiba.com/race/odds.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    odds_map = {}
    try:
        res = requests.get(odds_url, headers=headers, timeout=5)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        for row in soup.find_all("tr"):
            umaban_td = row.find("td", class_=re.compile(r'(Umaban|umaban|Bidx)'))
            odds_td = row.find("td", class_=re.compile(r'(Odds|odds|Tansho)'))
            if umaban_td and odds_td:
                uma_txt = umaban_td.text.strip()
                odds_txt = odds_td.text.strip()
                if uma_txt.isdigit():
                    num_match = re.search(r'\d+\.\d+', odds_txt)
                    if num_match: odds_map[int(uma_txt)] = float(num_match.group(0))
    except: pass
    return odds_map

# ==========================================
# 4. 核心解析エンジン（深層マッチング版）
# ==========================================
def fetch_deep_race_analysis(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    race_id_match = re.search(r'race_id=(\d{12})', url)
    if not race_id_match:
        return None, None, "⚠️ URLから12桁のレースIDが見つかりません。"
    
    race_id = race_id_match.group(1)
    
    # 🔥 【進化】URLから今回のレース環境を自動特定
    jyo_code = race_id[4:6]
    target_jyo = JYO_MAP.get(jyo_code, "不明")
    
    shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    try:
        res = requests.get(shutuba_url, headers=headers, timeout=5)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        
        # タイトルとコース情報の自動解析
        race_title = soup.title.text.split("|")[0].strip() if soup.title else "ターゲットレース"
        
        target_track = "芝"
        target_dist = 1600
        race_data_div = soup.find("div", class_=re.compile(r'(RaceData01|RaceList_ItemCard)'))
        if race_data_div:
            txt = race_data_div.text
            if "ダ" in txt: target_track = "ダ"
            dist_match = re.search(r'(\d+)m', txt)
            if dist_match: target_dist = int(dist_match.group(1))
            
        current_race_info = {"競馬場": target_jyo, "トラック": target_track, "距離": target_dist}
        
        table = soup.find("table", class_=re.compile(r'Shutuba_Table'))
        if not table: return None, None, "⚠️ 出馬表のテーブルが見つかりません。"
            
        rows = table.find_all("tr", class_="HorseList")
        scraped_data = []
        odds_map = fetch_real_odds(race_id)
        
        for row in rows:
            # 枠・馬番・馬名
            waku = 1
            waku_td = row.find("td", class_=re.compile(r'(waku|Waku)\d'))
            if waku_td:
                waku_match = re.search(r'(\d)', "".join(waku_td.get('class', [])) + waku_td.text)
                if waku_match: waku = int(waku_match.group(1))
                
            umaban = 0
            umaban_td = row.find("td", class_=re.compile(r'(Umaban|umaban)'))
            if umaban_td and umaban_td.text.strip().isdigit(): umaban = int(umaban_td.text.strip())
            
            name_span = row.find("span", class_=re.compile(r'(HorseName|horsename)'))
            if not name_span: continue
            name = name_span.text.strip()
            
            # 馬ID
            horse_id = ""
            id_candidates = re.findall(r'(?:id=|horse/|/horse/)(\d{10})', str(row))
            if id_candidates: horse_id = id_candidates[0]
            
            # 騎手
            jockey_td = row.find("td", class_=re.compile(r'(Jockey|jockey)'))
            jockey = "未定"
            if jockey_td: jockey = re.sub(r'[\d▲△☆★◇◇\s\n\r]', '', jockey_td.text.strip())
            
            odds = odds_map.get(umaban, 10.0)
            j_score = 0.75
            for k, v in JOCKEY_MAP.items():
                if k in jockey:
                    j_score = v
                    break
                    
            scraped_data.append({
                '枠番': waku, '馬番': umaban, '馬名': name, '馬ID': horse_id, 
                '騎手': jockey, '単勝': odds, '騎手実績スコア': j_score,
                '父馬': '不明', '系統': 'その他', '泥適性': 0.65, 'スタミナ': 0.70
            })
            
        # 次のステップ：各馬の詳細詳細ページ（db.netkeiba）を巡回
        st.markdown(f"### 🎯 今回の条件を検出: **{target_jyo} / {target_track}{target_dist}m**")
        st.markdown("### ⏳ 各馬の「過去5走の全戦績」を1マスずつ精査・完全同期中...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        final_data = []
        for idx, horse in enumerate(scraped_data):
            status_text.text(f"🏇 {idx+1}/{len(scraped_data)}頭目: 【{horse['馬名']}】の全過去データをマッチング中...")
            
            # デフォルト値（過去データがない新馬などの基準値）
            avg_rank = 7.0
            course_rank = 7.0
            dist_rank = 7.0
            baba_rank = 7.0
            
            if horse['馬ID']:
                try:
                    db_url = f"https://db.netkeiba.com/horse/{horse['馬ID']}/"
                    db_res = requests.get(db_url, headers=headers, timeout=5)
                    db_res.encoding = 'euc-jp'
                    db_soup = BeautifulSoup(db_res.text, "html.parser")
                    
                    # 1. 血統のパース
                    blood_table = db_soup.find("table", class_="blood_table")
                    if blood_table and blood_table.find("a"):
                        horse['父馬'] = blood_table.find("a").text.strip()
                        horse['系統'] = SIRE_MAP.get(horse['父馬'], 'その他')
                        horse['泥適性'] = BLOOD_SPEC[horse['系統']]['泥']
                        horse['スタミナ'] = BLOOD_SPEC[horse['系統']]['スタミナ']
                    
                    # 2. 【核心進化】戦績テーブルから条件別実績を全抽出
                    history_table = db_soup.find("table", class_="db_main_table")
                    if history_table:
                        headers_th = history_table.find("tr").find_all(["th", "td"])
                        col_indices = {'着順': 11, '開催': 1, '距離': 14, '馬場': 15}
                        for i, th in enumerate(headers_th):
                            t_txt = th.text.strip()
                            if "着順" in t_txt: col_indices['着順'] = i
                            elif "開催" in t_txt: col_indices['開催'] = i
                            elif "距離" in t_txt: col_indices['距離'] = i
                            elif "馬場" in t_txt: col_indices['馬場'] = i
                                
                        rows = history_table.find_all("tr")[1:]
                        
                        all_ranks = []    # 全体着順
                        c_ranks = []      # 同一競馬場着順
                        d_ranks = []      # 同一距離（±200m）かつ同トラック着順
                        b_ranks = []      # 同等馬場状態着順
                        
                        for r in rows[:5]:
                            tds = r.find_all("td")
                            if len(tds) > max(col_indices.values()):
                                r_txt = tds[col_indices['着順']].text.strip()
                                if not r_txt.isdigit(): continue
                                rank = int(r_txt)
                                all_ranks.append(rank)
                                
                                # 競馬場の判定
                                h_jyo = tds[col_indices['開催']].text.strip()
                                if target_jyo in h_jyo:
                                    c_ranks.append(rank)
                                    
                                # 距離・トラックの判定
                                h_dist_txt = tds[col_indices['距離']].text.strip()
                                h_track = "ダ" if "ダ" in h_dist_txt else "芝"
                                d_match = re.search(r'(\d+)', h_dist_txt)
                                if d_match:
                                    h_dist = int(d_match.group(1))
                                    if h_track == target_track and abs(h_dist - target_dist) <= 200:
                                        d_ranks.append(rank)
                                        
                                # 馬場の判定（重・不良適性か、良・稍重適性か）
                                h_baba = tds[col_indices['馬場']].text.strip()
                                if "重" in track_condition or "不良" in track_condition:
                                    if h_baba in ["重", "不"]: b_ranks.append(rank)
                                else:
                                    if h_baba in ["良", "稍"]: b_ranks.append(rank)
                                    
                        if all_ranks: avg_rank = sum(all_ranks) / len(all_ranks)
                        if c_ranks: course_rank = sum(c_ranks) / len(c_ranks)
                        if d_ranks: dist_rank = sum(d_ranks) / len(d_ranks)
                        if b_ranks: baba_rank = sum(b_ranks) / len(b_ranks)
                except: pass
                
            horse['過去5走平均着順'] = round(avg_rank, 1)
            horse['同コース平均着順'] = round(course_rank, 1)
            horse['同距離平均着順'] = round(dist_rank, 1)
            horse['同馬場平均着順'] = round(baba_rank, 1)
            
            final_data.append(horse)
            time.sleep(0.1) # 高速巡回
            progress_bar.progress((idx + 1) / len(scraped_data))
            
        status_text.empty()
        progress_bar.empty()
        return pd.DataFrame(final_data), current_race_info, f"🟢 「{race_title}」の全ディープ実績データを完全同期・指数化しました！"
    except Exception as e:
        return None, None, f"❌ システムエラーが発生しました: {str(e)}"

# ==========================================
# 5. 指数計算・メイン表示
# ==========================================
if race_url:
    df_live, r_info, status = fetch_deep_race_analysis(race_url)
    
    if df_live is not None:
        st.success(status)
        p_info = lap_summary[selected_pace]
        df = df_live.copy()
        
        # 1. 基礎実力秒（リアルタイムオッズから基礎タイムをマッピング）
        df['基礎実力秒'] = base_val + (df['単勝'].apply(lambda x: 0.0 if x < 2.0 else (0.4 if x < 5.0 else (1.2 if x < 10.0 else (2.5 if x < 30.0 else 4.0)))))
        
        # 2. 🔥 【核心進化】取得した「生の実績データ」を元にした、数理指数シミュレーション式
        # 着順は「7.0」を基準値(平均)とし、それより小さければ（1位に近ければ）タイムをマイナス（短縮）する。
        df['予測秒'] = (
            df['基礎実力秒']
            + ((df['過去5走平均着順'] - 7.0) * 0.15 * history_weight)   # 1. 全体実績
            + ((df['同コース平均着順'] - 7.0) * 0.20 * course_weight)    # 2. 競馬場適性
            + ((df['同距離平均着順'] - 7.0) * 0.25 * distance_weight)   # 3. 距離実績
            + ((df['同馬場平均着順'] - 7.0) * 0.15 * baba_weight)       # 4. 馬場適性
            + (mud_val * (1.1 - df['泥適性']) * 0.1)                      # 血統裏付け
            - (df['スタミナ'] * p_info['スタミナ重み'] * 0.5)               # 展開裏付け
            - (df['騎手実績スコア'] * (p_info['騎重み'] if '騎重み' in p_info else 1.5 + jockey_weight) * 0.5) # 5. 騎手手腕
        )
        
        # 同着防止微分散
        df['予測秒'] += [i * 0.005 for i in range(len(df))]
        
        result = df.sort_values(by='予測秒').reset_index(drop=True)
        result['着順'] = result.index + 1
        result['予想タイム'] = result['予測秒'].apply(lambda x: f"{int(x//60)}:{x%60:.2f}")
        
        # 画面表示用にスコアを反転整形
        result['ガチ適性指数'] = round((result['予測秒'].max() - result['予測秒']) * 20 + 50, 1)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📊 馬ごとのガチ適性指数")
            st.bar_chart(result.set_index('馬名')['ガチ適性指数'])
            
            st.markdown("""
            **💡 指数の見方**
            過去5走から「今回の競馬場」「今回の距離」「今回の馬場状態」と一致するレースだけを抽出し、その着順の良さを計算しています。過去に同じ条件で好走している馬ほど指数が高くなります。
            """)
            
        with col2:
            st.subheader("🏆 展開・適性シミュレーション最終予測")
            st.table(result[[
                '着順', '枠番', '馬番', '馬名', 'ガチ適性指数', 
                '過去5走平均着順', '同コース平均着順', '同距離平均着順', '同馬場平均着順', 
                '騎手', '単勝', '予想タイム'
            ]])
    else:
        st.warning(status)
