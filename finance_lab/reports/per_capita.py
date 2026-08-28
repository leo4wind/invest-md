"""人均创利对比页。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def render_html(table: pd.DataFrame, year_label: str, formula: str, out_path: Path) -> None:
    show = table.copy()
    show["归母净利润(亿)"] = show["归母净利润(亿)"].map(lambda x: f"{x:,.2f}")
    show["员工人数"] = show["员工人数"].map(lambda x: f"{int(x):,}")
    show["人均创利(万元)"] = show["人均创利(万元)"].map(lambda x: f"{x:,.2f}")
    table_html = show.to_html(index=False, classes="cmp", border=0, escape=True)

    labels = [f"{n}·{s}" for n, s in zip(table["名称"], table["行业"])]
    payload = {
        "labels": labels,
        "per_capita": [round(float(x), 2) for x in table["人均创利(万元)"]],
        "profit": [round(float(x), 2) for x in table["归母净利润(亿)"]],
    }

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>人均创利对比</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  body {{
    margin: 0; font-family: "PingFang SC", "Noto Sans SC", sans-serif;
    background: linear-gradient(165deg, #efe8dc, #f6f1e8 55%, #e8eef0);
    color: #1c1917; line-height: 1.55;
  }}
  header, main {{ max-width: 1100px; margin: 0 auto; padding: 24px 28px; }}
  h1 {{ margin: 0 0 8px; font-size: 26px; }}
  .muted {{ color: #57534e; font-size: 14px; }}
  section {{
    background: #fffdf8; border: 1px solid #e7e5e4; border-radius: 14px;
    padding: 16px 18px; margin: 14px 0;
  }}
  table.cmp {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table.cmp th, table.cmp td {{ padding: 8px 10px; border-bottom: 1px solid #e7e5e4; text-align: right; }}
  table.cmp th:nth-child(-n+3), table.cmp td:nth-child(-n+3) {{ text-align: left; }}
  canvas {{ max-height: 420px; }}
</style>
</head>
<body>
<header>
  <h1>知名公司人均创利</h1>
  <p class="muted">年份：{year_label} · {formula} · 员工人数为东财最新披露期末在职人数</p>
</header>
<main>
  <section>
    <p class="muted">人均创利衡量的是「这么多劳动力一共给股东赚了多少钱」，不是人均工资。劳动密集型公司分母大，数字会明显偏低。</p>
    {table_html}
  </section>
  <section>
    <canvas id="bar"></canvas>
  </section>
</main>
<script>
const payload = {json.dumps(payload, ensure_ascii=False)};
new Chart(document.getElementById("bar"), {{
  type: "bar",
  data: {{
    labels: payload.labels,
    datasets: [{{
      label: "人均创利（万元）",
      data: payload.per_capita,
      backgroundColor: "#0f766e"
    }}]
  }},
  options: {{
    indexAxis: "y",
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ title: {{ display: true, text: "万元 / 人" }} }} }}
  }}
}});
</script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
