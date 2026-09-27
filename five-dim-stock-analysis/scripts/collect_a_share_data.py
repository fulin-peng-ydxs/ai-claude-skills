#!/usr/bin/env python3
"""Collect reproducible public A-share datasets without hiding partial failures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import akshare as ak
    import pandas as pd
except ImportError as exc:  # pragma: no cover - depends on host environment
    print(
        json.dumps(
            {
                "status": "dependency_missing",
                "error": str(exc),
                "action": "Use public web sources; do not auto-install dependencies.",
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    raise SystemExit(3) from exc


@dataclass(frozen=True)
class SecurityId:
    code: str
    exchange: str

    @property
    def suffix(self) -> str:
        return f"{self.code}.{self.exchange}"

    @property
    def prefix(self) -> str:
        return f"{self.exchange}{self.code}"


def normalize_ticker(raw: str) -> SecurityId:
    value = raw.strip().upper().replace(" ", "")
    match = re.fullmatch(r"(?:(SH|SZ|BJ))?(\d{6})(?:\.(SH|SZ|BJ))?", value)
    if not match:
        raise ValueError("ticker must look like 600519, 600519.SH, or SH600519")
    prefix_exchange, code, suffix_exchange = match.groups()
    if prefix_exchange and suffix_exchange and prefix_exchange != suffix_exchange:
        raise ValueError("ticker contains conflicting exchange identifiers")
    exchange = prefix_exchange or suffix_exchange
    if code.startswith("6"):
        inferred = "SH"
    elif code.startswith(("0", "3")):
        inferred = "SZ"
    elif code.startswith(("4", "8", "92")):
        inferred = "BJ"
    else:
        raise ValueError(f"unsupported or non-A-share code: {code}")
    exchange = exchange or inferred
    if exchange != inferred:
        raise ValueError(f"ticker code {code} conflicts with exchange {exchange}")
    return SecurityId(code=code, exchange=exchange)


def json_default(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    return str(value)


def frame_date_range(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    candidates = [
        column
        for column in frame.columns
        if any(token in str(column).upper() for token in ("DATE", "日期", "报告期", "变更日"))
    ]
    for column in candidates:
        parsed = pd.to_datetime(frame[column], errors="coerce").dropna()
        if not parsed.empty:
            return parsed.min().date().isoformat(), parsed.max().date().isoformat()
    return None, None


def serializable_sample(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.iloc[:2, :12].to_dict(orient="records")
    return [
        {
            str(key): json_default(value) if not isinstance(value, (str, int, bool)) else value
            for key, value in row.items()
        }
        for row in records
    ]


class Collector:
    def __init__(self, output: Path, security: SecurityId) -> None:
        self.output = output
        self.security = security
        self.datasets: list[dict[str, Any]] = []

    def collect(
        self,
        name: str,
        provider: str,
        call: Callable[[], pd.DataFrame],
        transform: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    ) -> None:
        entry: dict[str, Any] = {"name": name, "provider": provider, "status": "error"}
        errors: list[dict[str, str]] = []
        frame: pd.DataFrame | None = None
        for attempt in (1, 2):
            try:
                frame = call()
                if not isinstance(frame, pd.DataFrame):
                    raise TypeError(f"expected DataFrame, got {type(frame).__name__}")
                if transform:
                    frame = transform(frame)
                entry["attempts"] = attempt
                break
            except Exception as exc:  # noqa: BLE001 - public clients raise heterogeneous errors.
                errors.append({"type": type(exc).__name__, "message": str(exc)})
        if frame is None:
            entry.update(error_type=errors[-1]["type"], error=errors[-1]["message"], errors=errors, attempts=2)
        elif frame.empty:
            entry.update(status="empty", rows=0, columns=list(map(str, frame.columns)))
        else:
            path = self.output / f"{name}.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            first_date, last_date = frame_date_range(frame)
            entry.update(
                status="ok",
                rows=len(frame),
                columns=list(map(str, frame.columns)),
                first_date=first_date,
                last_date=last_date,
                file=path.name,
                sample=serializable_sample(frame),
            )
        self.datasets.append(entry)


def filter_code(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    for column in ("代码", "股票代码", "SECURITY_CODE"):
        if column in frame.columns:
            return frame.loc[frame[column].astype(str).str.zfill(6) == code].copy()
    return frame.iloc[0:0].copy()


def assess_quality(output: Path, datasets: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    by_name = {item["name"]: item for item in datasets}
    warnings: list[str] = []
    required = {
        "company_profile",
        "financial_indicators",
        "balance_sheet",
        "income_statement",
        "cashflow_statement",
        "business_segments",
        "dividends",
        "share_capital",
    }
    missing_required = sorted(name for name in required if by_name.get(name, {}).get("status") != "ok")
    if missing_required:
        warnings.append(f"Core datasets unavailable: {', '.join(missing_required)}")

    has_price = any(by_name.get(name, {}).get("status") == "ok" for name in ("price_history", "valuation_history"))
    has_valuation = any(
        by_name.get(name, {}).get("status") == "ok"
        for name in ("valuation_pe_ttm", "valuation_pb", "valuation_history")
    )
    if not has_price:
        warnings.append("No price series is available; do not state a current or historical price.")
    if not has_valuation:
        warnings.append("No valuation history is available; scoring item 12 and price bands must be N/A.")

    for item in datasets:
        if item["status"] == "error":
            warnings.append(
                f"{item['name']} failed after {item.get('attempts', 1)} attempt(s); use the documented fallback source."
            )
        if item["status"] == "empty":
            warnings.append(
                f"{item['name']} returned an empty dataset; verify official disclosures before concluding the event is absent."
            )

    valuation_path = output / "valuation_pe_ttm.csv"
    if valuation_path.exists():
        valuation = pd.read_csv(valuation_path)
        if {"date", "value"}.issubset(valuation.columns):
            dates = pd.to_datetime(valuation["date"], errors="coerce").dropna()
            values = pd.to_numeric(valuation["value"], errors="coerce").dropna()
        else:
            dates, values = pd.Series(dtype="datetime64[ns]"), pd.Series(dtype="float64")
        if not dates.empty:
            span_years = (dates.max() - dates.min()).days / 365.25
            if span_years < 9.5 or len(values[values > 0]) < 500:
                warnings.append(
                    f"PE history fails the ten-year coverage gate: {span_years:.2f} years, "
                    f"{len(values[values > 0])} positive observations."
                )

    forecast_path = output / "profit_forecast.csv"
    indicators_path = output / "financial_indicators.csv"
    if forecast_path.exists():
        forecast = pd.read_csv(forecast_path)
        forecast_years = sorted(
            int(match.group(1))
            for column in forecast.columns
            if (match := re.fullmatch(r"(\d{4})预测每股收益", str(column)))
        )
        if not any("日期" in str(column) or "DATE" in str(column).upper() for column in forecast.columns):
            warnings.append("Profit forecast has no observation date; freshness must be verified from another public source.")
        if indicators_path.exists() and forecast_years:
            indicators = pd.read_csv(indicators_path)
            report_dates = (
                pd.to_datetime(indicators["REPORT_DATE"], errors="coerce")
                if "REPORT_DATE" in indicators.columns
                else pd.Series(dtype="datetime64[ns]")
            )
            annual_years = report_dates.loc[
                (report_dates.dt.month == 12) & (report_dates.dt.day == 31)
            ].dt.year.dropna()
            if not annual_years.empty:
                latest_actual = int(annual_years.max())
                nonfuture = [year for year in forecast_years if year <= latest_actual]
                if nonfuture:
                    warnings.append(
                        f"Forecast columns include completed fiscal years {nonfuture}; FY1-FY3 must start after {latest_actual}."
                    )

    core_ready = not missing_required and has_price and has_valuation
    return core_ready, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="A-share ticker, e.g. 600519.SH")
    parser.add_argument("--output", required=True, type=Path, help="New or empty output directory")
    parser.add_argument("--years", type=int, default=10, choices=range(5, 16), metavar="5-15")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        security = normalize_ticker(args.ticker)
    except ValueError as exc:
        print(json.dumps({"status": "invalid_ticker", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    output: Path = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        print(json.dumps({"status": "output_not_empty", "path": str(output)}, ensure_ascii=False), file=sys.stderr)
        return 2

    today = datetime.now().astimezone().date()
    start = today - timedelta(days=int(args.years * 365.25) + 14)
    start_text, end_text = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    collector = Collector(output, security)

    collector.collect("company_profile", "CNINFO via AKShare", lambda: ak.stock_profile_cninfo(security.code))
    collector.collect(
        "financial_indicators",
        "Eastmoney via AKShare",
        lambda: ak.stock_financial_analysis_indicator_em(security.suffix, "按报告期"),
    )
    collector.collect("balance_sheet", "Eastmoney via AKShare", lambda: ak.stock_balance_sheet_by_report_em(security.prefix))
    collector.collect("income_statement", "Eastmoney via AKShare", lambda: ak.stock_profit_sheet_by_report_em(security.prefix))
    collector.collect("cashflow_statement", "Eastmoney via AKShare", lambda: ak.stock_cash_flow_sheet_by_report_em(security.prefix))
    collector.collect("business_segments", "Eastmoney via AKShare", lambda: ak.stock_zygc_em(security.prefix))
    collector.collect(
        "price_history",
        "Eastmoney via AKShare",
        lambda: ak.stock_zh_a_hist(security.code, "daily", start_text, end_text, ""),
    )
    for indicator, filename in (("市盈率(TTM)", "valuation_pe_ttm"), ("市净率", "valuation_pb")):
        collector.collect(
            filename,
            "Baidu Stock via AKShare",
            lambda indicator=indicator: ak.stock_zh_valuation_baidu(security.code, indicator, "近十年"),
        )
    collector.collect("valuation_history", "Eastmoney via AKShare", lambda: ak.stock_value_em(security.code))
    collector.collect("peer_valuation", "Eastmoney via AKShare", lambda: ak.stock_zh_valuation_comparison_em(security.prefix))
    collector.collect("peer_dupont", "Eastmoney via AKShare", lambda: ak.stock_zh_dupont_comparison_em(security.prefix))
    collector.collect("dividends", "Eastmoney via AKShare", lambda: ak.stock_fhps_detail_em(security.code))
    collector.collect("dividends_cninfo", "CNINFO via AKShare", lambda: ak.stock_dividend_cninfo(security.code))
    collector.collect("share_capital", "Eastmoney via AKShare", lambda: ak.stock_zh_a_gbjg_em(security.suffix))
    collector.collect(
        "share_changes",
        "CNINFO via AKShare",
        lambda: ak.stock_share_change_cninfo(security.code, start_text, end_text),
    )
    collector.collect(
        "rights_issues",
        "CNINFO via AKShare",
        lambda: ak.stock_allotment_cninfo(security.code, start_text, end_text),
    )
    collector.collect(
        "profit_forecast",
        "Eastmoney via AKShare",
        lambda: ak.stock_profit_forecast_em(),
        transform=lambda frame: filter_code(frame, security.code),
    )

    ok_count = sum(item["status"] == "ok" for item in collector.datasets)
    core_ready, quality_warnings = assess_quality(output, collector.datasets)
    overall_status = "ok" if core_ready else "partial" if ok_count else "failed"
    manifest = {
        "status": overall_status,
        "ticker": security.suffix,
        "collected_at": datetime.now().astimezone().isoformat(),
        "akshare_version": getattr(ak, "__version__", "unknown"),
        "requested_years": args.years,
        "successful_datasets": ok_count,
        "total_datasets": len(collector.datasets),
        "datasets": collector.datasets,
        "quality_warnings": quality_warnings,
        "warnings": [
            "Aggregated datasets are collection aids, not the final authority.",
            "Verify the latest financial period and any conflicting values against official filings.",
            "An empty or failed endpoint is not evidence that the underlying fact is absent.",
        ],
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "manifest": str(manifest_path),
                "successful_datasets": ok_count,
                "total_datasets": len(collector.datasets),
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok_count else 4


if __name__ == "__main__":
    raise SystemExit(main())
