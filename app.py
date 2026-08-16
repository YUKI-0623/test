import json
import re
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
    "📱 スマホ対応：URLを入れるだけで【単勝オッズ・父馬・過去5走着順・騎手】を一発自動取得"
)
st.markdown("---")

# ==========================================
# 1. データベース・定数定義
# ==========================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)"
        " AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6"
        " Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
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
# 3. 超高速一発解析 データ取得エンジン
# ==========================================
def fetch_data_direct(url):
  match = re.search(r"(\d{12})", url)
  if not match:
    return None, "⚠️ URLに12桁のレースIDが含まれていません。"

  race_id = match.group(1)
  shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"

  status_box = st.status(
      "⚡ ネット競馬から出馬表を一括高速解析中...", expanded=True
  )

  try:
    res = requests.get(shutuba_url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.find_all("tr", class_=re.compile(r"HorseList"))
    if not rows:
      rows = soup.select("table.Shutuba_Table tr, table.RaceTable tr")

    horses = []
    for idx, row in enumerate(rows):
      # 馬名と馬ID
      a_horse = row.find("a", href=re.compile(r"/horse/(\d{10})"))
      if not a_horse:
        continue

      name = a_horse.text.strip()
      m_hid = re.search(r"/horse/(\d{10})", a_horse["href"])
      h_id = m_hid.group(1) if m_hid else ""

      # 枠番
      waku_td = row.find("td", class_=re.compile(r"Waku"))
      waku = 1
      if waku_td:
        m_waku = re.search(r"waku(\d)", str(waku_td), re.IGNORECASE)
        if m_waku:
          waku = int(m_waku.group(1))

      # 馬番
      u_td = row.find("td", class_=re.compile(r"Umaban"))
      umaban = (
          int(u_td.text.strip())
          if u_td and u_td.text.strip().isdigit()
          else len(horses) + 1
      )
      if not waku_td:
        waku = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

      # 騎手
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

      # 単勝オッズ
      odds = 99.0
      o_td = row.find("td", class_=re.compile(r"Popular|Odds"))
      if o_td:
        o_txt = o_td.text.strip()
        m_odds = re.search(r"(\d+\.\d+)", o_txt)
        if m_odds:
          odds = float(m_odds.group(1))

      # 父馬（出馬表の馬詳細・血統欄から一発解析）
      father = "不明"
      sire_td = row.find("td", class_=re.compile(r"Blood|Ped"))
      if sire_td:
        father = sire_td.text.strip().split("\n")[0]
      else:
        # 詳細枠内の血統文字検索
        detail_div = row.find("div", class_=re.compile(r"Horse_Info|Detail"))
        if detail_div:
          lines = [
              line.strip()
              for line in detail_div.text.split("\n")
              if line.strip()
          ]
          if len(lines) > 1:
            father = lines[1]

      syst = "その他"
      for k, v in SIRE_MAP.items():
        if k in father:
          syst = v
          break
      spec = BLOOD_SPEC.get(syst, BLOOD_SPEC["その他"])

      # 過去5走着順（出馬表のPast枠から数字のみを直接高速抽出）
      ranks = []
      past_tds = row.find_all("td", class_=re.compile(r"Past|Result"))
      for ptd in past_tds:
        # 着順を示す数字（例: "1", "3", "12"）を検出
        rank_span = ptd.find(class_=re.compile(r"Rank|Num"))
        if rank_span:
          m_r = re.search(r"^(\d+)", rank_span.text.strip())
          if m_r:
            ranks.append(int(m_r.group(1)))
        else:
          m_r = re.search(r"\b(\d{1,2})\b", ptd.text.strip())
          if m_r and int(m_r.group(1)) <= 18:
            ranks.append(int(m_r.group(1)))
        if len(ranks) >= 5:
          break

      horses.append({
          "枠番": waku,
          "馬番": umaban,
          "馬名": name,
          "馬ID": h_id,
          "騎手": jockey,
          "騎手実績スコア": j_score,
          "単勝オッズ": odds,
          "過去5走": ranks,
          "父馬": father,
          "泥適性": spec["泥適性"],
          "スタミナ": spec["スタミナ"],
          "瞬発力": spec["瞬発力"],
      })

    if not horses:
      status_box.update(
          label="❌ 出走馬データの解析に失敗しました。", state="error"
      )
      return None, "出走馬リストを取得できませんでした。"

    # オッズ補完API（画面オッズが取れていなかった場合のみ通信）
    try:
      odds_api_url = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1"
      odds_res = requests.get(
          odds_api_url,
          headers={"Referer": shutuba_url, **HEADERS},
          timeout=3,
      )
      if odds_res.status_code == 200:
        odds_data = (
            odds_res.json().get("data", {}).get("odds", {}).get("1", {})
        )
        for h in horses:
          if h["単勝オッズ"] == 99.0:
            u_key = str(h["馬番"]).zfill(2)
            if u_key in odds_data:
              val = odds_data[u_key][0]
              if val and val != "---.-":
                h["単勝オッズ"] = float(val)
    except Exception:
      pass

    status_box.update(
        label=f"🎉 全{len(horses)}頭のデータ（オッズ・父馬・過去5走）を高速取得しました！",
        state="complete",
    )
    return pd.DataFrame(horses), "🟢 成功"

  except Exception as e:
    status_box.update(label=f"❌ 取得エラー: {e}", state="error")
    return None, str(e)


# ==========================================
# 4. Gemini API による多角分析 ＆ 可視化関数
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
提供されたデータから、以下の【多角的評価ステップ】に従って各馬を精密に分析し、指定のJSON形式で出力してください。

【レース条件】
・馬場状態: {track_cond}
・想定ペース: {pace_cond}

【出走馬データ】
{json.dumps(race_data, ensure_ascii=False)}

【多角的評価ステップ】
1. **基礎能力 ＆ 適性評価**: 過去5走着順、騎手手腕、馬場（{track_cond}）・ペース（{pace_cond}）の血統適性を評価。
2. **期待値（オッズギャップ）評価**:
   - 算出された勝率に対して、現在の単勝オッズが過小評価（美味しい）されている馬を「穴馬（妙味あり）」として高く評価。
3. **⚠️ 危険な人気馬（飛ぶリスク）の判定**:
   - 単勝オッズ上位（1〜3番人気または単勝5.0倍以下）の馬の中で、以下の「飛ぶ要素」が2つ以上該当する場合は、過剰人気として【危険な人気馬】と認定し、AI指数・複勝率を大幅に割り引いてください。
     ・想定ペース（{pace_cond}）や枠順と脚質が致命的に不一致
     ・馬場状態（{track_cond}）に対して泥・血統適性が乏しい
     ・前走が展開恵まれ（フロック）による着順で実力以上に過大評価されている

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
      "risk_reason": "スローペース想定で展開不向き。重馬場血統適性も低いため飛ばす危険性大。"
    }}
  ],
  "pacing_analysis": "レース展開と展開利を得る馬・不利を受ける人気の短評（50文字程度）",
  "betting_recommendation": {{
    "honmei": "馬番 馬名",
    "ana_horse": "馬番 馬名（オッズ妙味のある穴馬）",
    "danger_horse": "馬番 馬名（消し推奨の危険人気馬）",
    "ticket_type": "3連複 軸1頭流し / 馬連",
    "combinations": "① - ②, ③, ④, ⑤"
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
      st.error("⚠️ **【AI警告】飛ぶ可能性が高い「危険な人気馬」を検知しました**")
      for d in danger_list:
        st.markdown(
            f"・**{d.get('umaban')}番 {d.get('name')}**（単勝"
            f" {d.get('odds')}倍）: {d.get('risk_reason')}"
        )

    bet_info = data.get("betting_recommendation", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
      st.metric(label="🎯 AI本命馬（◎）", value=bet_info.get("honmei", "なし"))
    with col2:
      st.metric(
          label="⭐ 期待の穴馬", value=bet_info.get("ana_horse", "なし")
      )
    with col3:
      st.metric(
          label="⚠️ 危険な人気馬", value=bet_info.get("danger_horse", "なし")
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

      c_graph, c_table = st.columns([1, 1.3])
      with c_graph:
        st.markdown("##### 📈 馬別 AI適性指数")
        st.bar_chart(rank_df.set_index("馬名")["AI指数"], color="#FF4B4B")

      with c_table:
        st.markdown("##### 🏆 AI多角分析データテーブル")
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
            column_config={
                "AI指数": st.column_config.ProgressColumn(
                    "AI指数",
                    help="100点満点評価",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                ),
                "推定制勝率(%)": st.column_config.NumberColumn(
                    "複勝率", format="%.0f%%"
                ),
            },
            hide_index=True,
            use_container_width=True,
        )

  except Exception as e:
    st.error(f"AI分析中にエラーが発生しました: {e}")


# ==========================================
# 5. メインシミュレーション計算＆画面表示
# ==========================================
if race_url:
  df, msg = fetch_data_direct(race_url)
  if df is not None:
    p_info = {
        "ミドルペース（標準・総合力勝負）": {"スタミナ": 1.0, "瞬発力": 1.0},
        "ハイペース（持久力・タフ決着）": {"スタミナ": 2.2, "瞬発力": 0.5},
        "スローペース（直線瞬発力・キレ勝負）": {"スタミナ": 0.5, "瞬発力": 2.2},
    }[selected_pace]

    # 平均着順（内部計算用）
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
              "過去5走着順",
              "父馬",
              "騎手",
              "予想タイム",
          ]]
      )

    st.markdown("---")
    st.subheader("🤖 AI多角分析 ＆ 危険な人気馬判定")

    if not gemini_api_key:
      st.info(
          "💡 サイドバーの「Gemini API"
          " Key」を入力すると、AI多角分析と危険な人気馬の判定が有効になります。"
      )
    else:
      if st.button("🔥 Gemini AIで多角分析・危険な人気馬を判定する"):
        with st.spinner("AIが展開・期待値・危険な人気馬を分析中..."):
          run_ai_prediction_and_display(
              gemini_api_key, result, track_condition, selected_pace
          )

  else:
    st.error(msg)
else:
  st.info(
      "👈 左側のサイドバーにネット競馬の出馬表URLをペーストすると、自動でデータ解析が始まります！"
  )
