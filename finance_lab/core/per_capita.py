"""
人均创利：归母净利润 / 在职员工人数。

这是劳动效率的粗口径，不是人均工资；员工数为期末人数，不是全年平均人数。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerCapitaProfit:
    year: int
    parent_net_profit: float  # 元
    employees: int
    profit_per_employee: float  # 元/人

    @property
    def profit_yi(self) -> float:
        return self.parent_net_profit / 1e8

    @property
    def per_capita_wan(self) -> float:
        return self.profit_per_employee / 1e4

    def as_text(self) -> str:
        return (
            f"{self.year} 年归母净利润 {self.profit_yi:,.2f} 亿 / "
            f"员工 {self.employees:,} 人 → 人均创利 {self.per_capita_wan:,.2f} 万元"
        )


PER_CAPITA_FORMULA = "人均创利 = 归母净利润 / 在职员工人数"


def compute_per_capita_profit(
    parent_net_profit: float,
    employees: int,
    year: int,
) -> PerCapitaProfit:
    if employees <= 0:
        raise ValueError("员工人数必须 > 0")
    return PerCapitaProfit(
        year=year,
        parent_net_profit=float(parent_net_profit),
        employees=int(employees),
        profit_per_employee=float(parent_net_profit) / float(employees),
    )
