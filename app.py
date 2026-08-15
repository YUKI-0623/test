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
      "過去5走平均着順",
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
1. **基礎能力 ＆ 適性評価**: 過去成績、上がりタイム、騎手手腕、馬場（{track_cond}）・ペース（{pace_cond}）の適性を評価。
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
    # モデル名を gemini-2.0-flash に修正
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.2
        ),
    )

    data = json.loads(response.text)

    # 1. 危険な人気馬の警告カード表示
    danger_list = data.get("dangerous_popular_horses", [])
    if danger_list:
      st.error("⚠️ **【AI警告】飛ぶ可能性が高い「危険な人気馬」を検知しました**")
      for d in danger_list:
        st.markdown(
            f"・**{d.get('umaban')}番 {d.get('name')}**（単勝"
            f" {d.get('odds')}倍）: {d.get('risk_reason')}"
        )

    # 2. 要点カード表示
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

    # 3. グラフとテーブルの可視化
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
