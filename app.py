import io
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ブラウザからのアクセスに見せかけるためのヘッダー（必須）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_race_and_horse_data(race_id: str):
  """netkeibaから出走表、単勝オッズ、各馬の過去成績を取得する

  Parameters:
      race_id (str): 例 "202305050811" (12桁のレースID)
  """

  # ==========================================================
  # ①・② 出走馬一覧・馬IDの取得 (race.netkeiba.com)
  # ==========================================================
  shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
  res = requests.get(shutuba_url, headers=HEADERS, timeout=10)
  res.encoding = "euc-jp"  # netkeibaの文字コード設定
  soup = BeautifulSoup(res.text, "html.parser")

  horses = []
  tr_list = soup.find_all("tr", class_="HorseList")

  for tr in tr_list:
    # 馬番
    umaban_td = tr.find("td", class_=re.compile(r"Umaban"))
    umaban = umaban_td.get_text(strip=True) if umaban_td else None

    # 馬名 & 馬ID
    horse_td = tr.find("td", class_="HorseInfo")
    horse_name, horse_id = None, None
    if horse_td:
      a_tag = horse_td.find("a", href=re.compile(r"/horse/"))
      if a_tag:
        horse_name = a_tag.get_text(strip=True)
        # hrefから10桁の馬IDを抽出
        match = re.search(r"/horse/(\d+)", a_tag["href"])
        if match:
          horse_id = match.group(1)

    if horse_name and horse_id:
      horses.append({
          "umaban": umaban,
          "horse_name": horse_name,
          "horse_id": horse_id,
          "odds": None,
          "popularity": None,
          "past_results": [],
      })

  # ==========================================================
  # ③ 単勝オッズ・人気の取得（netkeibaのオッズAPIを利用）
  # ==========================================================
  odds_api_url = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1"
  try:
    odds_res = requests.get(odds_api_url, headers=HEADERS, timeout=10)
    if odds_res.status_code == 200:
      odds_json = odds_res.json()
      # 単勝データ: odds_json['data']['odds']['1'] -> {"01": ["3.5", "1"], ...}
      odds_dict = odds_json.get("data", {}).get("odds", {}).get("1", {})

      for h in horses:
        if h["umaban"] and h["umaban"].isdigit():
          u_key = str(int(h["umaban"])).zfill(2)  # 2桁ゼロ埋め ("01", "02"...)
          if u_key in odds_dict:
            info = odds_dict[u_key]
            h["odds"] = float(info[0]) if info[0] else None
            h["popularity"] = int(info[1]) if len(info) > 1 else None
  except Exception as e:
    print(f"オッズAPI取得時の注意: {e}")

  # 予備ルート: レース終了後などAPIで取得できない場合は データベース(db.netkeiba)から補完
  if any(h["odds"] is None for h in horses):
    db_race_url = f"https://db.netkeiba.com/race/{race_id}/"
    try:
      db_res = requests.get(db_race_url, headers=HEADERS, timeout=10)
      if db_res.status_code == 200:
        db_res.encoding = "euc-jp"
        dfs = pd.read_html(io.StringIO(db_res.text))
        if dfs:
          df_race = dfs[0]
          if "馬番" in df_race.columns and "単勝" in df_race.columns:
            for h in horses:
              if h["odds"] is None and h["umaban"]:
                matched = df_race[
                    df_race["馬番"].astype(str) == str(h["umaban"])
                ]
                if not matched.empty:
                  try:
                    h["odds"] = float(matched["単勝"].values[0])
                    if "人気" in df_race.columns:
                      h["popularity"] = int(matched["人気"].values[0])
                  except (ValueError, TypeError):
                    pass
    except Exception as e:
      print(f"db.netkeibaからのオッズ補完エラー: {e}")

  # ==========================================================
  # ④ 各馬の過去競走成績の取得 (db.netkeiba.com)
  # ==========================================================
  print(f"全{len(horses)}頭の過去成績を取得中...")
  for h in horses:
    h_id = h["horse_id"]
    horse_url = f"https://db.netkeiba.com/horse/{h_id}/"

    try:
      time.sleep(1)  # サーバー負荷軽減（重要）
      h_res = requests.get(horse_url, headers=HEADERS, timeout=10)
      h_res.encoding = "euc-jp"

      # HTML内の全テーブルを自動パース
      dfs = pd.read_html(io.StringIO(h_res.text))

      target_df = None
      for df in dfs:
        # テーブル列名に「着順」が含まれるものを判定
        cols_text = "".join([str(c) for c in df.columns])
        if "着順" in cols_text or "着 順" in cols_text:
          target_df = df
          break

      if target_df is not None:
        # 直近5レース分を辞書形式で保存
        h["past_results"] = target_df.head(5).to_dict(orient="records")
      else:
        print(f"【警告】馬ID {h_id} ({h['horse_name']}) の成績テーブルが見つかりません。")

    except Exception as e:
      print(f"【エラー】馬ID {h_id} ({h['horse_name']}) の成績取得失敗: {e}")

  return horses


# --- 動作確認用 ---
if __name__ == "__main__":
  # 例: 12桁のレースID (過去または現在のレースIDを指定)
  RACE_ID = "202305050811"  # 2023年有馬記念の例

  data = get_race_and_horse_data(RACE_ID)

  # 取得結果の表示
  df_summary = pd.DataFrame(data)
  print("\n=== 出走馬・オッズ一覧 ===")
  print(df_summary[["umaban", "horse_name", "odds", "popularity"]])

  # 1頭目の過去成績を表示（例）
  if data and data[0]["past_results"]:
    print(f"\n=== {data[0]['horse_name']} の直近過去成績 ===")
    print(pd.DataFrame(data[0]["past_results"]))
