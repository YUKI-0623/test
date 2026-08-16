import json
import re
import time
from google import genai
from google.genai import types
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

# 画面全体の基本設定
st.set_page_config(
    page_title="スマホ最適化 🏇 競馬展開シミュレーター",
    layout="wide",
)
st.title("🏇 競馬展開シミュレーター")
st.caption(
    "📱 スマホ完全対応：URL入力のみで【単勝オッズ・父馬・過去5走着順・騎手】を精密自動取得"
)
st.markdown("---")

# ==========================================
# 1. データベース・定数定義
# ==========================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
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
    "ルメール": 0.98,
    "モレイラ": 0.98,
    "川田": 0.95,
    "武豊": 0.95,
    "レーン": 0.95,
    "戸崎": 0.90,
    "坂井": 0.90,
    "横山武": 0.88,
    "横山和": 0.88,
    "松山": 0.85,
    "デムーロ": 0.85,
    "岩田望": 0.85,
    "鮫島克": 0.85,
    "西村淳": 0.85,
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
      value="",
      placeholder="https://race.netkeiba.com/race/shutuba.html?race_id=...",
  )

  st.header("🔑 AI設定")
  default_api_key = st.secrets.get("GEMINI_API_KEY", "")
  gemini_api_key = st.text_input(
      "Gemini API Key",
      value=default_api_key,
      type="password",
      help="Google AI Studioで取得したAPIキーを入力してください",
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
# 3. 超精密データ解析エンジン
# ==========================================
def fetch_data_accurate(url):
  match = re.search(r"(\d{12})", url)
  if not match:
    return None, "⚠️ URLに12桁のレースIDが含まれていません。"

  race_id = match.group(1)
  shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"

  status_box = st.status(
      "🔍 データを解析中...（全項目を精密抽出）", expanded=True
  )

  session = requests.Session()
  session.headers.update(HEADERS)

  # STEP 1: 出馬表から基本データ取得
  status_box.write("📌 **【ステップ1】出走馬リスト・枠順・オッズ・騎手を取得中...**")
  horses = []
  try:
    res = session.get(shutuba_url, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.find_all("tr", class_=re.compile(r"HorseList"))

    for idx, row in enumerate(rows):
      a_horse = row.find("a", href=re.compile(r"/horse/(\d{10})"))
      if not a_horse:
        continue

      # 馬名のクレンジング（「のデータベース」等の不要テキストを除去）
      raw_name = a_horse.text.strip()
      clean_name = re.sub(
          r"の(データベース|掲示板|競走成績).*$", "", raw_name
      ).strip()

      m_hid = re.search(r"/horse/(\d{10})", a_horse["href"])
      h_id = m_hid.group(1) if m_hid else ""

      u_td = row.find("td", class_=re.compile(r"Umaban"))
      umaban = (
          int(u_td.text.strip())
          if u_td and u_td.text.strip().isdigit()
          else len(horses) + 1
      )
      waku = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

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

      odds = 99.0
      o_td = row.find("td", class_=re.compile(r"Popular|Odds"))
      if o_td:
        m_odds = re.search(r"(\d+\.\d+)", o_td.text.strip())
        if m_odds:
          odds = float(m_odds.group(1))

      horses.append({
          "枠番": waku,
          "馬番": umaban,
          "馬名": clean_name,
          "馬ID": h_id,
          "騎手": jockey,
          "騎手実績スコア": j_score,
          "単勝オッズ": odds,
          "過去5走": [],
          "父馬": "不明",
          "泥適性": 0.65,
          "スタミナ": 0.70,
          "瞬発力": 0.70,
      })

    if not horses:
      status_box.update(
          label="❌ 出走馬データの取得に失敗しました。", state="error"
      )
      return None, "出走馬リストを取得できませんでした。"

  except Exception as e:
    status_box.update(label=f"❌ ステップ1エラー: {e}", state="error")
    return None, str(e)

  # オッズAPIでバックアップ更新
  try:
    odds_api = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1"
    res_o = session.get(
        odds_api,
        headers={"Referer": shutuba_url, "X-Requested-With": "XMLHttpRequest"},
        timeout=5,
    )
    if res_o.status_code == 200:
      odds_dict = res_o.json().get("data", {}).get("odds", {}).get("1", {})
      for h in horses:
        u_key = str(h["馬番"]).zfill(2)
        if u_key in odds_dict:
          val = odds_dict[u_key][0]
          if val and val != "---.-":
            h["単勝オッズ"] = float(val)
  except Exception:
    pass

  # STEP 2: 各馬の個別ページから【父馬】と【過去5走着順】を取得
  status_box.write(
      "📌 **【ステップ2】個別ページから全頭の【父馬】と【過去5走着順】を巡回取得中...**"
  )
  p_bar = st.progress(0)

  for i, h in enumerate(horses):
    if h["馬ID"]:
      h_url = f"https://db.netkeiba.com/horse/{h['馬ID']}/"
      try:
        session.headers.update({"Referer": "https://db.netkeiba.com/"})
        h_res = session.get(h_url, timeout=5)

        if h_res.status_code == 200:
          h_res.encoding = "euc-jp"
          soup_h = BeautifulSoup(h_res.text, "html.parser")

          # 父馬抽出
          blood_tbl = soup_h.find("table", class_=re.compile(r"blood_table"))
          if blood_tbl:
            for a in blood_tbl.find_all("a"):
              t = a.text.strip()
              href = a.get("href", "")
              if t and t != "血統" and ("/horse/" in href or "/ped/" in href):
                h["父馬"] = t
                break

          if h["父馬"] != "不明":
            syst = "その他"
            for k, v in SIRE_MAP.items():
              if k in h["父馬"]:
                syst = v
                break
            spec = BLOOD_SPEC.get(syst, BLOOD_SPEC["その他"])
            h["泥適性"] = spec["泥適性"]
            h["スタミナ"] = spec["スタミナ"]
            h["瞬発力"] = spec["瞬発力"]

          # 過去5走着順抽出
          hist_table = soup_h.find(
              "table", class_=re.compile(r"db_main_table")
          )
          if hist_table:
            tr_list = hist_table.find_all("tr")[1:]
            ranks = []
            for tr in tr_list:
              tds = tr.find_all("td")
              if len(tds) > 11:
                rank_str = tds[11].text.strip()
                m_rank = re.search(r"^(\d+)", rank_str)
                if m_rank:
                  ranks.append(int(m_rank.group(1)))
                if len(ranks) >= 5:
                  break
            h["過去5走"] = ranks

      except Exception:
        pass

    time.sleep(0.05)
    p_bar.progress((i + 1) / len(horses))

  p_bar.empty()
  status_box.update(
      label="🎉 全頭の全項目データを正常にロードしました！", state="complete"
  )

  return pd.DataFrame(horses), "🟢 成功"


# ==========================================
# 4. Gemini API 多角分析
# ==========================================
def run_ai_prediction_and_display(api_key, df_data, track_cond, pace_cond):
  client = genai.Client(api_key=api_key)

  race_data = df_data[[
      "枠番",
      "馬番",
      "馬名",
      "単勝オッズ",
      "過去5走着順",
      "父馬",
      "騎手",
  ]].to_dict(orient="records")

  prompt = f"""
あなたは競馬の回収率（期待値）向上を追求するプロのデータサイエンティストです。
提供されたデータから、各馬を精密に分析し指定のJSON形式で出力してください。

【レース条件】
・馬場状態: {track_cond}
・想定ペース: {pace_cond}

【出走馬データ】
{json.dumps(race_data, ensure_ascii=False)}

【出力フォーマット（JSON形式のみ）】
{{
  "rankings": [
    {{
      "umaban": 1,
      "name": "馬名",
      "ai_score": 85.0,
      "fukushou_rate": 60,
      "mark": "◎",
      "expected_value_type": "本命 / 妙味(穴) / 危険な人気馬 / 静観",
      "reason": "15文字以内の簡潔な評価"
    }}
  ],
  "dangerous_popular_horses": [
    {{
      "umaban": 3,
      "name": "人気馬名",
      "odds": 2.8,
      "risk_reason": "展開不向きおよび血統適性不足による敗戦リスク大。"
    }}
  ],
  "pacing_analysis": "展開に関する短評（50文字程度）",
  "betting_recommendation": {{
    "honmei": "馬番 馬名",
    "ana_horse": "馬番 馬名",
    "danger_horse": "馬番 馬名",
    "ticket_type": "3連複 / 馬連",
    "combinations": "① - ②, ③, ④"
  }}
}}
"""

  try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.2
        ),
    )

    data = json.loads(response.text)

    danger_list = data.get("dangerous_popular_horses", [])
    if danger_list:
      st.error("⚠️ **【AI警告】危険な人気馬を検知しました**")
      for d in danger_list:
        st.markdown(
            f"・**{d.get('umaban')}番 {d.get('name')}**（単勝"
            f" {d.get('odds')}倍）: {d.get('risk_reason')}"
        )

    bet_info = data.get("betting_recommendation", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
      st.metric(label="🎯 本命馬（◎）", value=bet_info.get("honmei", "なし"))
    with col2:
      st.metric(
          label="⭐ 期待の穴馬", value=bet_info.get("ana_horse", "なし")
      )
    with col3:
      st.metric(
          label="⚠️ 危険人気馬", value=bet_info.get("danger_horse", "なし")
      )
    with col4:
      st.metric(label="🎫 推奨券種", value=bet_info.get("ticket_type", "なし"))

    st.info(f"💡 **AI展開診断**: {data.get('pacing_analysis', '')}")

    rank_df = pd.DataFrame(data.get("rankings", []))
    if not rank_df.empty:
      rank_df = rank_df.rename(
          columns={
              "mark": "印",
              "umaban": "馬番",
              "name": "馬名",
              "ai_score": "AI指数",
              "fukushou_rate": "推定制勝率(%)",
              "expected_value_type": "タイプ",
              "reason": "AI評価ポイント",
          }
      )

      st.dataframe(
          rank_df[[
              "印",
              "馬番",
              "馬名",
              "AI指数",
              "推定制勝率(%)",
              "タイプ",
              "AI評価ポイント",
          ]],
          hide_index=True,
          use_container_width=True,
      )

  except Exception as e:
    st.error(f"AI分析エラー: {e}")


# ==========================================
# 5. メイン画面制御
# ==========================================
if race_url:
  df, msg = fetch_data_accurate(race_url)
  if df is not None:
    p_info = {
        "ミドルペース（標準・総合力勝負）": {"スタミナ": 1.0, "瞬発力": 1.0},
        "ハイペース（持久力・タフ決着）": {"スタミナ": 2.2, "瞬発力": 0.5},
        "スローペース（直線瞬発力・キレ勝負）": {"スタミナ": 0.5, "瞬発力": 2.2},
    }[selected_pace]

    df["内部_平均着順"] = df["過去5走"].apply(
        lambda x: sum(x) / len(x) if x else 8.0
    )

    df["実績影響秒"] = (df["内部_平均着順"] - 4.5) * 0.22 * history_weight
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

    st.subheader("📊 馬ごとのガチ適性指数")
    st.bar_chart(result.set_index("馬名")["ガチ適性指数"])

    st.subheader("🏆 シミュレーション最終予測")
    st.dataframe(
        result[[
            "着順",
            "枠番",
            "馬番",
            "馬名",
            "ガチ適性指数",
            "単勝オッズ",
            "過去5走着順",
            "父馬",
            "騎手",
            "予想タイム",
        ]],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("🤖 AI多角分析 ＆ 危険な人気馬判定")

    if gemini_api_key:
      if st.button("🔥 Gemini AIで多角分析・危険な人気馬を判定する"):
        with st.spinner("AIが分析中..."):
          run_ai_prediction_and_display(
              gemini_api_key, result, track_condition, selected_pace
          )

  else:
    st.error(msg)
else:
  st.info(
      "👈 左側のサイドバー（スマホは左上の『＞』ボタン）からネット競馬の出馬表URLを入力してください。"
  )
