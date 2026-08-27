"""
对照知识体系公式计算净现值（NPV）与内部收益率（IRR）。

知识体系:
  NPV = Σ [CFt ÷ (1 + r)^t] − 初始投资
  IRR: 令 NPV = 0 的折现率

本模块统一用「含 t=0 的现金流序列」计算（与上式等价）:
  CF0 = −初始投资（通常为负），CF1…CFn 为各期净流入
  NPV(r) = Σ_{t=0}^{n} CFt / (1+r)^t
  IRR 满足 NPV(IRR) = 0
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NpvIrrResult:
    """NPV / IRR 计算结果。"""

    cash_flows: tuple[float, ...]
    discount_rate: float
    npv: float
    irr: float | None
    irr_note: str

    @property
    def initial_investment(self) -> float:
        """初始投资（正数）；若 CF0≥0 则返回 0。"""
        cf0 = self.cash_flows[0] if self.cash_flows else 0.0
        return float(-cf0) if cf0 < 0 else 0.0

    def as_text(self) -> str:
        lines = [
            f"现金流 CF0…CFn = {list(self.cash_flows)}",
            f"折现率 r = {self.discount_rate:.4%}",
            f"NPV(r) = {self.npv:,.4f}",
        ]
        if self.irr is not None:
            lines.append(f"IRR = {self.irr:.4%}  ({self.irr_note})")
        else:
            lines.append(f"IRR = 无解  ({self.irr_note})")
        decision = "NPV>0，按折现率口径项目增值" if self.npv > 0 else (
            "NPV=0，临界" if self.npv == 0 else "NPV<0，按折现率口径未覆盖资本成本"
        )
        lines.append(f"决策提示: {decision}")
        return "\n".join(lines)


def parse_cash_flows(text: str) -> list[float]:
    """解析逗号/空格分隔的现金流，如 '-100,40,40,40'。"""
    parts = [p.strip() for p in text.replace(";", ",").replace(" ", ",").split(",")]
    values = [float(p) for p in parts if p]
    if not values:
        raise ValueError("现金流为空")
    return values


def build_cash_flows(
    future_cfs: list[float],
    initial_investment: float,
) -> list[float]:
    """
    按知识体系写法组装序列：初始投资为正数，未来各期流入为正。

    返回 [−初始投资, CF1, CF2, …]
    """
    if initial_investment < 0:
        raise ValueError("initial_investment 应为正数（投入金额）")
    return [-float(initial_investment), *[float(x) for x in future_cfs]]


def npv(rate: float, cash_flows: list[float] | tuple[float, ...]) -> float:
    """NPV(r) = Σ CFt / (1+r)^t，t 从 0 起（整数期）。"""
    if rate <= -1:
        raise ValueError("折现率 r 必须 > -1")
    total = 0.0
    for t, cf in enumerate(cash_flows):
        total += float(cf) / (1.0 + rate) ** t
    return float(total)


def npv_at_times(
    rate: float,
    cash_flows: list[float] | tuple[float, ...],
    times: list[float] | tuple[float, ...],
) -> float:
    """按任意时点（年）折现：NPV = Σ CFi / (1+r)^{ti}。"""
    if rate <= -1:
        raise ValueError("折现率 r 必须 > -1")
    if len(cash_flows) != len(times):
        raise ValueError("cash_flows 与 times 长度须一致")
    total = 0.0
    for cf, t in zip(cash_flows, times, strict=True):
        total += float(cf) / (1.0 + rate) ** float(t)
    return float(total)


def _npv_derivative(rate: float, cash_flows: list[float] | tuple[float, ...]) -> float:
    """d(NPV)/dr，供牛顿法用。"""
    total = 0.0
    for t, cf in enumerate(cash_flows):
        if t == 0:
            continue
        total -= t * float(cf) / (1.0 + rate) ** (t + 1)
    return float(total)


def irr(
    cash_flows: list[float] | tuple[float, ...],
    *,
    guess: float = 0.1,
    tol: float = 1e-10,
    max_iter: int = 100,
) -> tuple[float | None, str]:
    """
    求使 NPV=0 的 IRR。

    返回 (irr 或 None, 说明)。非常规现金流可能多解；此处返回牛顿法/括号搜索找到的一个根。
    """
    cfs = [float(x) for x in cash_flows]
    if len(cfs) < 2:
        return None, "至少需要两期现金流（含初始投资）"

    signs = {np.sign(x) for x in cfs if x != 0}
    if len(signs) < 2:
        return None, "现金流未改变符号，通常无有限 IRR"

    # 牛顿法
    r = guess
    for _ in range(max_iter):
        f = npv(r, cfs)
        if abs(f) < tol:
            return float(r), "牛顿法收敛"
        df = _npv_derivative(r, cfs)
        if abs(df) < 1e-18:
            break
        r_next = r - f / df
        if r_next <= -0.999999:
            break
        if abs(r_next - r) < tol:
            return float(r_next), "牛顿法收敛"
        r = r_next

    # 括号搜索：在 (-0.99, 10] 上找变号区间再二分
    grid = np.concatenate(
        [
            np.linspace(-0.99, -0.01, 40),
            np.linspace(0.0, 1.0, 80),
            np.linspace(1.0, 10.0, 40),
        ]
    )
    prev_r, prev_v = float(grid[0]), npv(float(grid[0]), cfs)
    for r_i in grid[1:]:
        r_i = float(r_i)
        v = npv(r_i, cfs)
        if prev_v == 0:
            return prev_r, "网格搜索命中零点"
        if v == 0:
            return r_i, "网格搜索命中零点"
        if prev_v * v < 0:
            lo, hi = prev_r, r_i
            flo, fhi = prev_v, v
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                fm = npv(mid, cfs)
                if abs(fm) < tol or abs(hi - lo) < tol:
                    return float(mid), "二分法（非常规现金流时可能只是其中一个根）"
                if flo * fm <= 0:
                    hi, fhi = mid, fm
                else:
                    lo, flo = mid, fm
            return float(0.5 * (lo + hi)), "二分法近似"
        prev_r, prev_v = r_i, v

    return None, "未找到使 NPV=0 的折现率（可能无解或多解失败）"


def compute_npv_irr(
    cash_flows: list[float] | tuple[float, ...],
    discount_rate: float,
) -> NpvIrrResult:
    """同时计算给定折现率下的 NPV，以及 IRR。"""
    cfs = tuple(float(x) for x in cash_flows)
    rate = float(discount_rate)
    irr_value, note = irr(cfs)
    return NpvIrrResult(
        cash_flows=cfs,
        discount_rate=rate,
        npv=npv(rate, cfs),
        irr=irr_value,
        irr_note=note,
    )


def annualize_holding_irr(period_irr: float, years: float) -> float:
    """把「整段持有期 IRR」换算成年化： (1+R)^(1/years) - 1。"""
    if years <= 0:
        raise ValueError("years 必须 > 0")
    return float((1.0 + period_irr) ** (1.0 / years) - 1.0)
