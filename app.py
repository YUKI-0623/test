import io
import re
import time
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

# 画面全体の基本設定
st.set_page_config(
    page_title="条件ダイナミック連動 🏇 ガチ展開シミュレーター",
    layout="wide",
)
st.title("🏇 順序指定・実戦データ解析 × 展開シミュレーター")
st.caption(
    "指定順序（①出走馬 ➔ ②騎手 ➔ ③オッズ ➔ ④過去レース結果）で本物のデータを1頭ずつ精密取得"
)
st.markdown("---")

# ==========================================
# 1. データベース・定数定義
# ==========================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

SIRE_MAP = {
    "ゴールドシップ": "ステイゴールド系",
    "オルフェーヴル": "ステイゴールド系",
    "ステイゴールド": "ステイゴールド系",
    "エピファネイア": "ロベルト系",
    "モーリス": "ロベルト系",
    "スクリーンヒーロー": "ロベルト系",
    "キタサンブラック": "ブラックタイド系",
    "ブラックタイド": "ブラックタイド系",
    "ドゥラメンテ": "キングカメハメハ系",
    "ロードカナロア": "キングカメハメハ系",
    "ルーラーシップ": "キングカメハメハ系",
    "キズナ": "ディープ系",
    "ディープインパクト": "ディープ系",
    "コントレイル": "ディープ系",
    "スワーヴリチャード": "ハーツクライ系",
    "ハーツクライ": "ハーツクライ系",
}

BLOOD_SPEC = {
    "ステイゴールド系": {"泥適性": 0.90, "スタミナ": 0.90, "瞬発力": 0.60},
    "ロベルト系": {"泥適性": 0.85, "スタミナ": 0.85, "瞬発力": 0.65},
    "ブラックタイド系": {"泥適性": 0.75, "スタミナ": 0.85, "瞬発力": 0.75},
    "キングカメハメハ系": {"泥適性": 0.70, "スタミナ": 0.75, "瞬発力": 0.80},
    "ディープ系": {"泥適性": 0.55, "スタミナ": 0.70, "瞬発力": 0.95},
    "ハーツクライ系": {"泥適性": 0.65, "スタミナ": 0.85, "瞬発力": 0.80},
    "その他": {"泥適性": 0.65, "スタミナ": 0.70, "瞬発力": 0.70},
}

JOCKEY_MAP = {
    "ルメ": 0.98,
    "モレイ": 0.98,
    "川田": 0.95,
    "武豊": 0.95,
    "レーン": 0.95,
    "戸崎": 0.90,
    "坂井": 0.90,
    "横山武": 0.88,
    "横山和": 0.88,
    "松山": 0.85,
    "デム": 0.85,
    "岩田望": 0.85,
    "鮫島": 0.85,
    "西村": 0.85,
    "菅原明": 0.85,
    "幸": 0.80,
    "横山典": 0.80,
    "津村": 0.82,
    "田辺": 0.82,
    "丹内": 0.80,
}

# ==========================================
# 2. サイドバーUI
# ==========================================
with st.sidebar:
  st.header("🔗 レースURL入力")
  race_url = st.text_input(
      "ネット競馬の出馬表URL",
      value="https://race.netkeiba.com/race/shutuba.html?race_id=202605030211",
  )

  st.header("🛠 1. 馬場と展開の設定")
  track_condition = st.select_slider(
      "馬場状態を選択",
      options=["良馬場", "稍重", "重馬場", "不良馬場"],
      value="良馬場",
  )
  track_mud_map = {"良馬場": 0.0, "稍重": 3.0, "重馬場": 6.5, "不良馬場": 10.0}
  mud_val = track_mud_map[track_condition]

  selected_pace = st.selectbox(
      "想定するレース展開",
      [
          "ミドルペース（標準・総合力勝負）",
          "ハイペース（持久力・タフ決着）",
          "スローペース（直線瞬発力・キレ勝負）",
      ],
  )
  base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 95.0)

  st.header("📈 2. パラメーター重み付け")
  history_weight = st.slider("🔥 過去実績（前走着順）の重み", 0.0, 5.0, 2.5)
  odds_weight = st.slider("💰 オッズ（支持率）の重み", 0.0, 5.0, 2.0)
  course_weight = st.slider("☔ 馬場・血統適性の重み", 0.0, 5.0, 2.0)
  jockey_weight = st.slider("🏇 騎手手腕の重み", 0.0, 5.0, 2.0)


# ==========================================
# 3. データ取得エンジン
# ==========================================
def fetch_data(url):
  match = re.search(r"race_id=(\d{12})", url)
  if not match:
    return None, "⚠️ URLに12桁のレースIDが含まれていません。"

  race_id = match.group(1)
  status_box = st.status(
      "🔍 データを順序指定で取得中...", expanded=True
  )

  # ①・② 出走馬と騎手の取得
  status_box.write("📌 **【①・②】出走馬リストと騎手データを取得中...**")
  shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
  try:
    res = requests.get(shutuba_url, headers=HEADERS, timeout=8)
    res.encoding = "euc-jp"
    soup = BeautifulSoup(res.text, "html.parser")
    rows = soup.find_all("tr", class_="HorseList")

    if not rows:
      status_box.update(
          label="❌ 出馬表が見つかりませんでした。", state="error"
      )
      return None, "出馬表が見つかりませんでした。"

    horses = []
    for idx, row in enumerate(rows):
      u_td = row.find("td", class_=re.compile(r"Umaban"))
      umaban = int(u_td.text.strip()) if u_td and u_td.text.strip().isdigit() else idx + 1
      waku = (umaban - 1) // 2 + 1

      h_span = row.find("span", class_=re.compile(r"HorseName"))
      if not h_span:
        continue
      name = h_span.text.strip()

      h_id = ""
      a_tag = h_span.find("a")
      if a_tag and "href" in a_tag.attrs:
        m = re.search(r"\d{10}", a_tag["href"])
        if m:
          h_id = m.group(0)

      j_td = row.find("td", class_=re.compile(r"Jockey"))
      jockey = (
          re.sub(r"[\d▲△☆★◇◇\s\n\r]", "", j_td.text.strip())
          if j_td
          else "未定"
      )
      j_score = 0.75
      for k, v in JOCKEY_MAP.items():
        if k in jockey:
          j_score = v
          break

      horses.append({
          "枠番": waku,
          "馬番": umaban,
          "馬名": name,
          "馬ID": h_id,
          "騎手": jockey,
          "騎手実績スコア": j_score,
          "単勝オッズ": 99.0,
          "過去5走": [],
          "過去5走平均着順": 8.0,
          "父馬": "不明",
          "泥適性": 0.65,
          "スタミナ": 0.70,
          "瞬発力": 0.70,
      })

    status_box.write(f"✅ {len(horses)}頭の基本情報を抽出しました。")
  except Exception as e:
    status_box.update(label=f"❌ ①・②でエラー: {e}", state="error")
    return None, str(e)

  # ③ 単勝オッズの取得 (API経由)
  status_box.write("📌 **【③】単勝オッズ（実値）を取得中...**")
  try:
    odds_api_url = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1"
    odds_res = requests.get(odds_api_url, headers=HEADERS, timeout=6)
    if odds_res.status_code == 200:
      odds_data = (
          odds_res.json().get("data", {}).get("odds", {}).get("1", {})
      )
      for h in horses:
        u_key = str(h["馬番"]).zfill(2)
        if u_key in odds_data:
          val = odds_data[u_key][0]
          if val and val != "---.-":
            h["単勝オッズ"] = float(val)
    status_box.write("✅ オッズの確定値読み込み完了。")
  except Exception as e:
    status_box.write(f"⚠️ オッズAPIフォールバック: {e}")

  # ④ 各馬の過去成績・血統を取得
  status_box.write("📌 **【④】各馬の過去成績・血統を1頭ずつ抽出中...**")
  p_bar = st.progress(0)

  for i, h in enumerate(horses):
    if h["馬ID"]:
      try:
        h_url = f"https://db.netkeiba.com/horse/{h['馬ID']}/"
        h_res = requests.get(h_url, headers=HEADERS, timeout=5)
        h_res.encoding = "euc-jp"

        soup_h = BeautifulSoup(h_res.text, "html.parser")
        sire_a = soup_h.find("a", href=re.compile(r"/sire/"))
        if sire_a:
          father = sire_a.text.strip()
          h["父馬"] = father
          syst = "その他"
          for k, v in SIRE_MAP.items():
            if k in father:
              syst = v
              break
          spec = BLOOD_SPEC.get(syst, BLOOD_SPEC["その他"])
          h["泥適性"] = spec["泥適性"]
          h["スタミナ"] = spec["スタミナ"]
          h["瞬発力"] = spec["瞬発力"]

        # 成績テーブル解析
        try:
          dfs = pd.read_html(io.StringIO(h_res.text))
          for d in dfs:
            cols = "".join([str(c) for c in d.columns])
            if "着順" in cols or "着 順" in cols:
              ranks = []
              for r in d["着順"].head(5):
                r_str = str(r).strip()
                if r_str.isdigit():
                  ranks.append(int(r_str))
              if ranks:
                h["過去5走"] = ranks
                h["過去5走平均着順"] = round(sum(ranks) / len(ranks), 1)
              break
        except Exception:
          pass

      except Exception:
        pass
    time.sleep(0.1)
    p_bar.progress((i + 1) / len(horses))

  p_bar.empty()
  status_box.update(
      label="🎉 すべてのデータの取得が完了しました！", state="complete"
  )
  return pd.DataFrame(horses), "🟢 成功"


# ==========================================
# 4. シミュレーション計算＆表示
# ==========================================
if race_url:
  df, msg = fetch_data(race_url)
  if df is not None:
    p_info = {
        "ミドルペース（標準・総合力勝負）": {"スタミナ": 1.0, "瞬発力": 1.0},
        "ハイペース（持久力・タフ決着）": {"スタミナ": 2.2, "瞬発力": 0.5},
        "スローペース（直線瞬発力・キレ勝負）": {"スタミナ": 0.5, "瞬発力": 2.2},
    }[selected_pace]

    df["実績影響秒"] = (df["過去5走平均着順"] - 4.5) * 0.22 * history_weight
    df["オッズ影響秒"] = np.log1p(df["単勝オッズ"]) * 0.35 * odds_weight
    df["馬場適性秒"] = mud_val * (1.0 - df["泥適性"]) * 0.20 * course_weight
    df["展開適性秒"] = -(
        (df["スタミナ"] * p_info["スタミナ"] + df["瞬発力"] * p_info["瞬発力"])
        * 0.3
    )
    df["騎手補正秒"] = -(df["騎手実績スコア"] * 0.5 * jockey_weight)

    df["予測秒"] = (
        base_val
        + df["実績影響秒"]
        + df["オッズ影響秒"]
        + df["馬場適性秒"]
        + df["展開適性秒"]
        + df["騎手補正秒"]
    )

    result = df.sort_values(by="予測秒").reset_index(drop=True)
    result["着順"] = result.index + 1
    result["予想タイム"] = result["予測秒"].apply(
        lambda x: f"{int(x//60)}:{x%60:.2f}"
    )

    max_s = result["予測秒"].max()
    min_s = result["予測秒"].min()
    diff_s = max(0.1, max_s - min_s)
    result["ガチ適性指数"] = round(
        50 + (max_s - result["予測秒"]) / diff_s * 45, 1
    )
    result["過去5走着順"] = result["過去5走"].apply(
        lambda x: " - ".join(map(str, x)) if x else "データなし"
    )

    col1, col2 = st.columns([1, 2])
    with col1:
      st.subheader("📊 馬ごとのガチ適性指数")
      st.bar_chart(result.set_index("馬名")["ガチ適性指数"])

    with col2:
      st.subheader("🏆 シミュレーション最終予測")
      st.table(
          result[[
              "着順",
              "枠番",
              "馬番",
              "馬名",
              "ガチ適性指数",
              "単勝オッズ",
              "過去5走平均着順",
              "過去5走着順",
              "父馬",
              "騎手",
              "予想タイム",
          ]]
      )
  else:
    st.error(msg)
