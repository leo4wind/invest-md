"""
入口：自动计算 NPV 与 IRR。

干什么：
  1. 从知识体系读出「净现值」「内部收益率」公式
  2. 按现金流序列计算 NPV(r) 与 IRR
  3. 可选：用 A 股买卖价自动生成「买入 → 持有 → 卖出」现金流

运行示例：
    # 教材式现金流（默认演示）
    uv run python -m finance_lab.apps.irr_npv

    # 手输：初始投 100，此后三期各回 40；折现率 10%
    uv run python -m finance_lab.apps.irr_npv --invest 100 --cf 40,40,40 --r 0.10

    # 完整序列（CF0 为负）
    uv run python -m finance_lab.apps.irr_npv --cf -100000,35000,40000,45000 --r 0.08

    # 从 CSV 读两列：period,cf 或单列 cf
    uv run python -m finance_lab.apps.irr_npv --csv path/to/cashflows.csv --r 0.08

    # A 股持有期：按首末日收盘价自动生成现金流并算 IRR/NPV
    uv run python -m finance_lab.apps.irr_npv --stock 300534 --start 20240101 --end 20260725 --r 0.08
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from finance_lab.core.irr_npv import (
    annualize_holding_irr,
    build_cash_flows,
    compute_npv_irr,
    npv_at_times,
    parse_cash_flows,
)
from finance_lab.core.knowledge import find_term
from finance_lab.core.market_data import fetch_a_share_daily, resolve_discount_rate


def normalize_a_share_symbol(code: str) -> str:
    """300534 / sz300534 / SH600519 → 新浪风格 sh/sz + 6 位。"""
    s = code.strip().lower().replace(".", "")
    if s.startswith(("sh", "sz")) and len(s) >= 8:
        return s[:2] + s[2:8]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"无法识别 A 股代码: {code!r}")
    if digits.startswith(("5", "6", "9")):
        return "sh" + digits
    return "sz" + digits


def load_cash_flows_csv(path: Path) -> list[float]:
    """支持: 单列数值；或含 cf/现金流 列；或 period,cf。"""
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"CSV 为空: {path}")

    # 尝试按表头读
    with path.open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = False
        reader = csv.DictReader(f) if has_header else None
        if reader and reader.fieldnames:
            fields = [x.strip().lower() for x in reader.fieldnames]
            cf_key = None
            for cand in ("cf", "cashflow", "cash_flow", "现金流", "金额"):
                if cand in fields:
                    cf_key = reader.fieldnames[fields.index(cand)]
                    break
            if cf_key is None and len(reader.fieldnames) == 1:
                cf_key = reader.fieldnames[0]
            if cf_key is not None:
                rows = list(reader)
                # 若有 period，按 period 排序
                period_key = None
                for cand in ("period", "t", "期", "期数"):
                    if cand in fields:
                        period_key = reader.fieldnames[fields.index(cand)]
                        break
                if period_key is not None:
                    rows.sort(key=lambda r: float(r[period_key]))
                return [float(r[cf_key]) for r in rows]

    # 无表头：逐行一个数，或一行逗号分隔
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1 and ("," in lines[0] or " " in lines[0]):
        return parse_cash_flows(lines[0])
    return [float(ln.split(",")[0]) for ln in lines]


def cash_flows_from_stock(
    symbol: str,
    start: str,
    end: str,
    shares: float = 1.0,
) -> tuple[list[float], dict]:
    """
    用区间首日买入、末日卖出构造两期现金流（未计入分红）:
      CF0 = −买入价 × 股数
      CF1 = 卖出价 × 股数
    """
    sina = normalize_a_share_symbol(symbol)
    daily = fetch_a_share_daily(sina, start, end)
    buy = float(daily["close"].iloc[0])
    sell = float(daily["close"].iloc[-1])
    buy_date = daily["date"].iloc[0]
    sell_date = daily["date"].iloc[-1]
    years = max((sell_date - buy_date).days / 365.25, 1e-9)
    cfs = [-buy * shares, sell * shares]
    meta = {
        "symbol": sina,
        "buy_date": str(buy_date.date()),
        "sell_date": str(sell_date.date()),
        "buy_price": buy,
        "sell_price": sell,
        "shares": shares,
        "years": years,
        "n_trading_days": len(daily),
    }
    return cfs, meta


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="自动计算 NPV 与 IRR（知识体系公式）")
    p.add_argument(
        "--cf",
        default=None,
        help="完整现金流，含 CF0，如 -100,40,40,40",
    )
    p.add_argument(
        "--invest",
        type=float,
        default=None,
        help="初始投资（正数）；与 --cf 未来流入配合使用",
    )
    p.add_argument("--csv", type=Path, default=None, help="从 CSV 读取现金流")
    p.add_argument(
        "--r",
        type=float,
        default=None,
        help="折现率（小数，如 0.08）；默认中债10年+溢价",
    )
    p.add_argument("--stock", default=None, help="A股代码，如 300534 或 sz300534")
    p.add_argument("--start", default="20240101", help="股票模式开始日期 YYYYMMDD")
    p.add_argument("--end", default=None, help="股票模式结束日期 YYYYMMDD，默认今天")
    p.add_argument("--shares", type=float, default=100.0, help="股票模式持股数量")
    return p


def resolve_cash_flows(
    args: argparse.Namespace,
) -> tuple[list[float], str, dict | None]:
    """按参数优先级得到现金流、来源说明，以及股票模式元数据。"""
    if args.stock:
        end = args.end or pd.Timestamp.today().strftime("%Y%m%d")
        cfs, meta = cash_flows_from_stock(
            args.stock, args.start, end, shares=args.shares
        )
        src = (
            f"A股持有期自动生成 {meta['symbol']}: "
            f"{meta['buy_date']} 买 {meta['buy_price']:.4f} × {meta['shares']:g} → "
            f"{meta['sell_date']} 卖 {meta['sell_price']:.4f} × {meta['shares']:g} "
            f"（约 {meta['years']:.2f} 年，{meta['n_trading_days']} 个交易日；未计分红）"
        )
        return cfs, src, meta

    if args.csv is not None:
        return load_cash_flows_csv(args.csv), f"CSV: {args.csv}", None

    if args.cf is not None and args.invest is not None:
        future = parse_cash_flows(args.cf)
        return (
            build_cash_flows(future, args.invest),
            f"初始投资 {args.invest:g} + 未来现金流 {future}",
            None,
        )

    if args.cf is not None:
        return parse_cash_flows(args.cf), "命令行 --cf", None

    # 默认教材演示：投 100，三期各回 40
    demo = build_cash_flows([40.0, 40.0, 40.0], 100.0)
    return demo, "默认演示：投资 100，三期各收回 40", None


def main() -> None:
    args = build_parser().parse_args()

    print("=" * 60)
    print("1) 知识体系中的公式说明")
    print("=" * 60)
    print(find_term("净现值").summary())
    print()
    print(find_term("内部收益率").summary())
    print()

    print("=" * 60)
    print("2) 现金流输入")
    print("=" * 60)
    cash_flows, source, stock_meta = resolve_cash_flows(args)
    print(f"来源: {source}")
    print(f"CF = {cash_flows}")
    print()

    print("=" * 60)
    print("3) 计算结果")
    print("=" * 60)
    rate, rate_src = resolve_discount_rate(args.r)
    print(f"折现率来源: {rate_src}")
    result = compute_npv_irr(cash_flows, rate)

    if stock_meta is None:
        print(result.as_text())
    else:
        years = float(stock_meta["years"])
        timed_npv = npv_at_times(rate, cash_flows, [0.0, years])
        holding_return = result.irr  # 两期模型下 IRR = 卖/买 - 1
        print(f"现金流 CF0…CF1 = {list(cash_flows)}")
        print(f"折现率 r = {rate:.4%}")
        print(f"NPV(r) = {timed_npv:,.4f}  （按实际持有 {years:.2f} 年折现）")
        if holding_return is not None:
            ann = annualize_holding_irr(holding_return, years)
            print(f"持有期总回报 = {holding_return:.4%}")
            print(f"年化 IRR ≈ {ann:.4%}")
        decision = (
            "NPV>0，按折现率口径增值"
            if timed_npv > 0
            else ("NPV=0，临界" if timed_npv == 0 else "NPV<0，未覆盖资本成本")
        )
        print(f"决策提示: {decision}")

    print()
    print("说明: 公式文本来自 金融投资知识体系.json；股票模式数据来自 AKShare。")


if __name__ == "__main__":
    main()
