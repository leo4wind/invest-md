"""
入口：知名公司人均创利对比。

干什么：
  1. 用 AKShare 拉各行业龙头股的年度归母净利润
  2. 用东财公司概况取在职员工人数
  3. 计算 人均创利 = 归母净利润 / 员工人数

运行：
    uv run python -m finance_lab.apps.per_capita_profit
    uv run python -m finance_lab.apps.per_capita_profit --year 2025
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

import pandas as pd

from finance_lab.core.knowledge import find_term
from finance_lab.core.market_data import (
    fetch_annual_parent_net_profit,
    fetch_employee_count,
)
from finance_lab.core.paths import OUTPUT_DIR
from finance_lab.core.per_capita import PER_CAPITA_FORMULA, compute_per_capita_profit
from finance_lab.core.samples import SECTOR_SAMPLES
from finance_lab.reports.per_capita import render_html


@dataclass
class Row:
    sector: str
    name: str
    symbol: str
    year: int
    profit_yi: float
    employees: int
    per_capita_wan: float


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="知名公司人均创利（归母净利润/员工人数）")
    p.add_argument("--year", type=int, default=None, help="报告年份，默认最近一年年报")
    return p


def analyze_one(item: dict, year: int | None) -> Row:
    y, profit = fetch_annual_parent_net_profit(item["symbol"], year=year)
    employees = fetch_employee_count(item["symbol"])
    result = compute_per_capita_profit(profit, employees, y)
    return Row(
        sector=item["sector"],
        name=item["name"],
        symbol=item["symbol"],
        year=result.year,
        profit_yi=result.profit_yi,
        employees=result.employees,
        per_capita_wan=result.per_capita_wan,
    )


def to_table(rows: list[Row]) -> pd.DataFrame:
    df = pd.DataFrame([asdict(r) for r in rows]).rename(
        columns={
            "sector": "行业",
            "name": "名称",
            "symbol": "代码",
            "year": "年份",
            "profit_yi": "归母净利润(亿)",
            "employees": "员工人数",
            "per_capita_wan": "人均创利(万元)",
        }
    )
    return df.sort_values("人均创利(万元)", ascending=False).reset_index(drop=True)


def print_table(table: pd.DataFrame) -> None:
    show = table.copy()
    show["归母净利润(亿)"] = show["归母净利润(亿)"].map(lambda x: f"{x:,.2f}")
    show["员工人数"] = show["员工人数"].map(lambda x: f"{int(x):,}")
    show["人均创利(万元)"] = show["人均创利(万元)"].map(lambda x: f"{x:,.2f}")
    print(show.to_string(index=False))


def main() -> None:
    args = build_parser().parse_args()

    print("=" * 60)
    print("1) 公式说明")
    print("=" * 60)
    print(PER_CAPITA_FORMULA)
    print()
    print(find_term("归母净利润").summary())
    print()
    print(find_term("扣非净利润").summary())
    print()
    print("口径: 归母净利润（年报）÷ 东财披露的期末在职人数；不是人均工资，也不是全年平均人数。")
    print()

    print("=" * 60)
    print("2) 拉取并计算")
    print("=" * 60)
    rows: list[Row] = []
    for item in SECTOR_SAMPLES:
        try:
            row = analyze_one(item, args.year)
            rows.append(row)
            print(f"  OK {item['sector']:4} {item['name']}: {row.per_capita_wan:,.2f} 万元/人")
        except Exception as e:
            print(f"  FAIL {item['sector']} {item['name']}: {e}")

    if not rows:
        raise SystemExit("全部样本计算失败")

    table = to_table(rows)
    years = sorted({int(y) for y in table["年份"]})
    year_label = str(years[0]) if len(years) == 1 else f"{min(years)}–{max(years)}"

    print()
    print("=" * 72)
    print(f"人均创利对比（按人均创利排序，{year_label}）")
    print("=" * 72)
    print_table(table)

    out = OUTPUT_DIR / "per_capita_profit.html"
    render_html(table, year_label, PER_CAPITA_FORMULA, out)
    print()
    print(f"可视化: {out}")


if __name__ == "__main__":
    main()
