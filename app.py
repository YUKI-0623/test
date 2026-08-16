import json
import re
from google import genai
from google.genai import types
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(
    page_title="スマホ完全対応 🏇 競馬展開シミュレーター",
    layout="wide",
)
st.title("🏇 競馬展開シミュレーター")
st.caption(
    "📱 スマホ専用一括取得エンジン：URL入力のみで【単勝オッズ・父馬・過去5走・全騎手】を即時反映"
)
st.markdown("---")

# 1. データベース・定数定義
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)"
        " AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4"
        " Mobile/15E148 Safari/604.1"
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
    "池添": 0.84,
    "佐々木": 0.83,
    "幸": 0.80,
    "横山典": 0.80,
    "津村": 0.82,
    "田辺": 0.82,
    "丹内": 0.80,
    "和田竜": 0.80,
    "吉田": 0.78,
    "三浦": 0.78,
    "石橋": 0.77,
    "横山琉": 0.77,
    "黛": 0.75,
}

# 2. サイドバーUI
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
      "Gemini API Key", value=default_api_key, type="password"
  )

  st.header("🛠 1. 馬場と展開の設定")
  track_condition = st.select_slider(
      "馬場状態", options=["良馬場", "稍重", "重馬場", "不良馬場"], value="良馬場"
  )
  track_mud_map = {"良馬場": 0.0, "稍重": 3.0, "重馬場": 6.5, "不良馬場": 10.0}
  mud_val = track_mud_map[track_condition]

  selected_pace = st.selectbox(
      "想定展開",
      [
          "ミドルペース（標準・総合力勝負）",
          "ハイペース（持久力・タフ決着）",
          "スローペース（直線瞬発力・キレ勝負）",
      ],
  )
  base_val = st.slider("ベースタイム（秒）", 70.0, 160.0, 95.0)

  st.header("📈 2. パラメーター重み付け")
  history_weight = st.slider("🔥 過去実績の重み", 0.0, 5.0, 2.5)
  odds_weight = st.slider("💰 オッズの重み", 0.0, 5.0, 2.0)
  course_weight = st.slider("☔ 馬場・血統適性の重み", 0.0, 5.0, 2.0)
  jockey_weight = st.slider("🏇 騎手手腕の重み", 0.0, 5.0, 2.0)


# 3. スマホ版一括解析エンジン
def fetch_sp_data(url):
  match = re.search(r"(\d{12})", url)
  if not match:
    return None, "⚠️ URLに12桁のレースIDが含まれていません。"

  race_id = match.group(1)
  sp_shutuba_url = (
      f"https://sp.netkeiba.com/race/shutuba.html?race_id={race_id}"
  )

  status_box = st.status(
      "📱 スマホ版ページから一括高速ロード中...", expanded=True
  )

  try:
    res = requests.get(sp_shutuba_url, headers=HEADERS, timeout=8)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    # オッズAPIの並行取得
    odds_dict = {}
    try:
      odds_api = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1"
      res_o = requests.get(
          odds_api,
          headers={"Referer": sp_shutuba_url, **HEADERS},
          timeout=3,
      )
      if res_o.status_code == 200:
        odds_dict = res_o.json().get("data", {}).get("odds", {}).get("1", {})
    except Exception:
      pass

    rows = soup.select(
        "ul.HorseList > li, tr.HorseList, div.HorseList, table.ShutubaTable tr"
    )
    if not rows:
      rows = soup.find_all("tr", class_=re.compile(r"HorseList|Shutuba"))

    horses = []
    for idx, row in enumerate(rows):
      text_block = row.text.strip()
      if not text_block:
        continue

      # 馬名取得と不要テキスト除去
      a_horse = row.find("a", href=re.compile(r"/horse/"))
      if not a_horse:
        continue

      raw_name = a_horse.text.strip()
      name = re.sub(
          r"の(データベース|掲示板|競走成績).*$", "", raw_name
      ).strip()
      if not name or name == "馬名":
        continue

      # 馬番・枠番
      u_match = re.search(r"\b(\d{1,2})\b", text_block)
      umaban = len(horses) + 1
      u_elem = row.find(class_=re.compile(r"Umaban|num"))
      if u_elem and u_elem.text.strip().isdigit():
        umaban = int(u_elem.text.strip())
      waku = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

      # 騎手名
      j_elem = row.find(a=re.compile(r"/jockey/")) or row.find(
          class_=re.compile(r"Jockey|jockey")
      )
      jockey = (
          re.sub(r"[\d▲△☆★◇◇\s\n\r]", "", j_elem.text.strip())
          if j_elem
          else "未定"
      )
      j_score = 0.75
      for k, v in JOCKEY_MAP.items():
        if k in jockey:
          j_score = v
          break

      # オッズ取得（API優先 -> 画面抽出）
      odds = 99.0
      u_key = str(umaban).zfill(2)
      if u_key in odds_dict and odds_dict[u_key][0] != "---.-":
        try:
          odds = float(odds_dict[u_key][0])
        except ValueError:
          pass

      if odds == 99.0:
        o_match = re.search(r"(\d+\.\d+)\s*倍", text_block) or re.search(
            r"\b(\d+\.\d+)\b", text_block
        )
        if o_match:
          odds = float(o_match.group(1))

      # 父馬抽出
      father = "その他"
      father_match = re.search(r"父[:：]?\s*([一-龠ぁ-んァ-ヶa-zA-Z0-9]+)", text_block)
      if father_match:
        father = father_match.group(1)

      syst = "その他"
      for k, v in SIRE_MAP.items():
        if k in father or k in text_block:
          syst = v
          father = k
          break
      spec = BLOOD_SPEC.get(syst, BLOOD_SPEC["その他"])

      # 過去5走着順（テキスト内の数字リストを全自動解析）
      ranks = []
      r_matches = re.findall(r"着順[:：]?\s*(\d{1,2})", text_block)
      if r_matches:
        ranks = [int(r) for r in r_matches[:5]]
      else:
        # 簡易フォールバック（前走の数字等）
        nums = re.findall(r"\b([1-9]|1[0-8])\b", text_block)
        if len(nums) > 3:
          ranks = [int(n) for n in nums[3:8]]

      horses.append({
          "枠番": waku,
          "馬番": umaban,
          "馬名": name,
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
      return None, "出走馬データを抽出できませんでした。"

    status_box.update(
        label=f"🎉 全{len(horses)}頭のデータ一括ロード完了！", state="complete"
    )
    return pd.DataFrame(horses), "🟢 成功"

  except Exception as e:
    status_box.update(label=f"❌ データ読み込みエラー: {e}", state="error")
    return None, str(e)


# 4. メイン画面制御
if race_url:
  df, msg = fetch_sp_data(race_url)
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

  else:
    st.error(msg)
else:
  st.info(
      "👈 左側のサイドバー（スマホは画面左上の『＞』ボタン）から出馬表URLを入力してください。"
  )
