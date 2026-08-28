"""从 AKShare 拉取行情等原始数据（优先较稳定的新浪接口）。"""

from __future__ import annotations

import os
import urllib.request

import akshare as ak
import pandas as pd
import requests


def _disable_system_proxy() -> None:
    """部分东财接口会被系统代理干扰，取数前尽量直连。"""
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")
    urllib.request.getproxies = lambda: {}  # type: ignore[assignment]
    if getattr(requests.sessions.Session.request, "_lab_no_proxy", False):
        return
    _orig = requests.sessions.Session.request

    def _no_proxy_request(self, method, url, **kwargs):
        kwargs["proxies"] = {"http": None, "https": None}
        return _orig(self, method, url, **kwargs)

    _no_proxy_request._lab_no_proxy = True  # type: ignore[attr-defined]
    requests.sessions.Session.request = _no_proxy_request  # type: ignore[method-assign]


def sina_to_em_symbol(symbol: str) -> str:
    """sh600519 → SH600519（东方财富现金流量表用）。"""
    return symbol[:2].upper() + symbol[2:]


def fetch_a_share_daily(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    拉取 A 股日线。

    symbol: 带市场前缀，如 sh600519、sz300750
    start_date / end_date: YYYYMMDD
    adjust: qfq=前复权, hfq=后复权, ""=不复权
    """
    df = ak.stock_zh_a_daily(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    if df is None or df.empty:
        raise RuntimeError(f"未取到日线: {symbol}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    return out


def fetch_china_5y_yield_percent(as_of: str | None = None) -> float | None:
    """
    尝试读取中债国债 5 年收益率（单位：百分比，如 1.44 表示 1.44%）。
    失败时返回 None。
    """
    try:
        end = as_of or pd.Timestamp.today().strftime("%Y%m%d")
        start = (pd.Timestamp(end) - pd.Timedelta(days=14)).strftime("%Y%m%d")
        curve = ak.bond_china_yield(start_date=start, end_date=end)
        if curve is None or curve.empty:
            return None
        mask = curve["曲线名称"].astype(str).str.contains("中债国债收益率曲线", na=False)
        rows = curve.loc[mask] if mask.any() else curve
        return float(rows.iloc[-1]["5年"])
    except Exception:
        return None


def resolve_risk_free(cli_rf: float | None = None) -> tuple[float, str]:
    """决定年化无风险利率 Rf（小数），并返回来源说明。"""
    if cli_rf is not None:
        return cli_rf, "命令行 --rf"

    y5 = fetch_china_5y_yield_percent()
    if y5 is not None:
        return y5 / 100.0, f"中债国债5年收益率 {y5:.4f}%"

    return 0.02, "默认 2%（未能读取国债收益率）"


def fetch_china_10y_yield_percent(as_of: str | None = None) -> float | None:
    """中债国债 10 年收益率（百分比）。"""
    try:
        end = as_of or pd.Timestamp.today().strftime("%Y%m%d")
        start = (pd.Timestamp(end) - pd.Timedelta(days=14)).strftime("%Y%m%d")
        curve = ak.bond_china_yield(start_date=start, end_date=end)
        if curve is None or curve.empty:
            return None
        mask = curve["曲线名称"].astype(str).str.contains("中债国债收益率曲线", na=False)
        rows = curve.loc[mask] if mask.any() else curve
        return float(rows.iloc[-1]["10年"])
    except Exception:
        return None


def resolve_discount_rate(
    cli_r: float | None = None,
    equity_premium: float = 0.05,
) -> tuple[float, str]:
    """
    DCF 折现率 r（小数）。

    默认: 中债10年 + 股权风险溢价；失败则 5年+溢价；再失败用 8%。
    """
    if cli_r is not None:
        return cli_r, "命令行 --r"

    y10 = fetch_china_10y_yield_percent()
    if y10 is not None:
        r = y10 / 100.0 + equity_premium
        return r, f"中债10年 {y10:.4f}% + 溢价 {equity_premium:.0%}"

    y5 = fetch_china_5y_yield_percent()
    if y5 is not None:
        r = y5 / 100.0 + equity_premium
        return r, f"中债5年 {y5:.4f}% + 溢价 {equity_premium:.0%}"

    return 0.08, "默认 8%"


def fetch_annual_fcf(symbol: str, years: int = 5) -> pd.DataFrame:
    """
    年度自由现金流（元）。

    知识体系: FCF = 经营活动现金流净额 - 资本性支出
    这里用东财年报: NETCASH_OPERATE - CONSTRUCT_LONG_ASSET（购建固定资产等）。
    """
    _disable_system_proxy()
    em = sina_to_em_symbol(symbol)
    raw = ak.stock_cash_flow_sheet_by_yearly_em(symbol=em)
    if raw is None or raw.empty:
        raise RuntimeError(f"未取到现金流量表: {symbol}")

    df = raw.copy()
    df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
    # 只要年报 12-31
    df = df[df["REPORT_DATE"].dt.month.eq(12) & df["REPORT_DATE"].dt.day.eq(31)]
    df = df.sort_values("REPORT_DATE").tail(years)

    ocf = pd.to_numeric(df["NETCASH_OPERATE"], errors="coerce")
    capex = pd.to_numeric(df["CONSTRUCT_LONG_ASSET"], errors="coerce").fillna(0.0)
    out = pd.DataFrame(
        {
            "year": df["REPORT_DATE"].dt.year.astype(int),
            "ocf": ocf.to_numpy(),
            "capex": capex.to_numpy(),
            "fcf": (ocf - capex).to_numpy(),
        }
    ).dropna(subset=["fcf"])
    if out.empty:
        raise RuntimeError(f"无法计算年度 FCF: {symbol}")
    return out.reset_index(drop=True)


def fetch_latest_price_and_shares(symbol: str) -> tuple[float, float]:
    """
    最新收盘价与流通股本（来自新浪日线 outstanding_share）。
    返回 (price, shares)。
    """
    end = pd.Timestamp.today().strftime("%Y%m%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=40)).strftime("%Y%m%d")
    daily = fetch_a_share_daily(symbol, start, end)
    price = float(daily["close"].iloc[-1])
    shares = float(daily["outstanding_share"].iloc[-1])
    if price <= 0 or shares <= 0:
        raise RuntimeError(f"价格或股本异常: {symbol}")
    return price, shares


def _code6(symbol: str) -> str:
    """sh600519 / SZ002594 / 600519 → 600519。"""
    digits = "".join(ch for ch in symbol if ch.isdigit())
    if len(digits) < 6:
        raise ValueError(f"无法解析股票代码: {symbol!r}")
    return digits[-6:]


def fetch_employee_count(symbol: str) -> int:
    """
    在职员工人数（东财 F10 公司概况 EMP_NUM）。

    AKShare 的雪球概况接口目前不稳定，这里直接读东财 PageAjax，
    口径通常是最近年报期末在职人数。
    """
    _disable_system_proxy()
    em = sina_to_em_symbol(symbol)
    url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax"
    r = requests.get(url, params={"code": em}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("jbzl") or []
    if not rows:
        raise RuntimeError(f"未取到公司概况: {symbol}")
    emp = rows[0].get("EMP_NUM")
    if emp is None or float(emp) <= 0:
        raise RuntimeError(f"员工人数缺失: {symbol}")
    return int(float(emp))


def _parse_yi_text(value: object) -> float:
    """把同花顺『326.19亿』转成元。"""
    s = str(value).strip().replace(",", "")
    if not s or s in {"False", "None", "nan", "--"}:
        raise ValueError(f"无法解析金额: {value!r}")
    unit = 1.0
    if s.endswith("万亿"):
        unit, s = 1e12, s[:-2]
    elif s.endswith("亿"):
        unit, s = 1e8, s[:-1]
    elif s.endswith("万"):
        unit, s = 1e4, s[:-1]
    return float(s) * unit


def fetch_annual_parent_net_profit(
    symbol: str,
    year: int | None = None,
) -> tuple[int, float]:
    """
    年度归母净利润（元）。

    优先东财利润表 PARENT_NETPROFIT；失败则用同花顺财务摘要「净利润」（年报口径与归母一致）。
    返回 (报告年份, 金额元)。
    """
    _disable_system_proxy()
    em = sina_to_em_symbol(symbol)

    try:
        raw = ak.stock_profit_sheet_by_yearly_em(symbol=em)
        if raw is not None and not raw.empty and "PARENT_NETPROFIT" in raw.columns:
            df = raw.copy()
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
            df["year"] = df["REPORT_DATE"].dt.year.astype(int)
            df["profit"] = pd.to_numeric(df["PARENT_NETPROFIT"], errors="coerce")
            df = df.dropna(subset=["profit"]).sort_values("year")
            if year is not None:
                hit = df[df["year"] == year]
                if hit.empty:
                    raise RuntimeError(f"利润表无 {year} 年数据: {symbol}")
                row = hit.iloc[-1]
            else:
                row = df.iloc[-1]
            return int(row["year"]), float(row["profit"])
    except Exception:
        pass

    ths = ak.stock_financial_abstract_ths(symbol=_code6(symbol), indicator="按年度")
    if ths is None or ths.empty:
        raise RuntimeError(f"未取到年度净利润: {symbol}")
    out = ths.copy()
    out["year"] = pd.to_numeric(out["报告期"].astype(str).str[:4], errors="coerce")
    out = out.dropna(subset=["year"])
    out["year"] = out["year"].astype(int)
    if year is not None:
        hit = out[out["year"] == year]
        if hit.empty:
            raise RuntimeError(f"财务摘要无 {year} 年数据: {symbol}")
        row = hit.iloc[-1]
    else:
        row = out.sort_values("year").iloc[-1]
    return int(row["year"]), _parse_yi_text(row["净利润"])
