from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


def retrieved_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return default


def safe_float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "-", "--"):
            return None
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def safe_yi(value: Any, default: float = 0.0) -> float:
    return round(safe_float(value, default * 100000000) / 100000000, 4)


def safe_cn_money_yi(value: Any, default: float = 0.0) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "--"}:
        return default
    if text.endswith("亿"):
        return safe_float(text[:-1], default)
    if text.endswith("万"):
        return round(safe_float(text[:-1], default * 10000) / 10000, 4)
    return safe_yi(text, default)


def ts_to_time(value: Any) -> str:
    raw = safe_float(value)
    if not raw:
        return ""
    if raw > 100000000000:
        raw = raw / 1000
    try:
        return datetime.fromtimestamp(raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def zt_time(value: Any) -> str:
    raw = str(safe_int(value)).zfill(6)
    return f"{raw[0:2]}:{raw[2:4]}:{raw[4:6]}" if raw != "000000" else ""


def compact_date(value: datetime | None = None) -> str:
    dt = value or datetime.now()
    return dt.strftime("%Y%m%d")


def hyphen_date(value: datetime | str | None = None) -> str:
    if value is None:
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def latest_quarter_end(value: datetime | None = None) -> str:
    dt = value or datetime.now()
    quarter_ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
    for month, day in reversed(quarter_ends):
        candidate = datetime(dt.year, month, day)
        # Give disclosures a practical lag so empty future quarter pages are avoided.
        if candidate <= dt - timedelta(days=35):
            return candidate.strftime("%Y%m%d")
    return datetime(dt.year - 1, 12, 31).strftime("%Y%m%d")


def market_prefix(code: str) -> str:
    symbol = re.sub(r"\D", "", str(code))[:6]
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    if symbol.startswith(("0", "2", "3")):
        return f"sz{symbol}"
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return symbol


def eastmoney_secid(code: str) -> str:
    symbol = re.sub(r"\D", "", str(code))[:6]
    market = 1 if symbol.startswith(("6", "9")) else 0
    return f"{market}.{symbol}"


def html_cell_text(html: str) -> str:
    value = re.sub(r"<.*?>", "", html, flags=re.S)
    value = value.replace("&nbsp;", " ").strip()
    return re.sub(r"\s+", " ", value)


def parse_html_table_rows(html: str, min_cols: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(tds) < min_cols:
            continue
        clean = [html_cell_text(td) for td in tds]
        if clean and clean[0].isdigit():
            rows.append(clean)
    return rows


def parse_json_payload(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    return json.loads(text)


def configured_xtick_token() -> str:
    token = os.getenv("XTICK_TOKEN", "").strip()
    if token:
        return token
    try:
        from xtick.scripts.Config import Config  # type: ignore

        return str(getattr(Config, "TOKEN", "")).strip()
    except Exception:
        return ""


@dataclass
class SourceProbe:
    provider: str
    ok: bool
    category: str
    message: str
    count: int = 0
    retrieved_at: str = field(default_factory=retrieved_at)
    sample: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class XTickClient:
    provider = "xtick"

    def __init__(self, token: str | None = None, base_url: str = "http://api.xtick.top"):
        self.token = (token or configured_xtick_token()).strip()
        self.base_url = base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.enabled:
            raise RuntimeError("XTICK_TOKEN is not configured")
        payload = dict(params or {})
        payload["token"] = self.token
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=25) as client:
            for attempt in range(3):
                try:
                    r = await client.get(f"{self.base_url}{path}", params=payload)
                    r.raise_for_status()
                    try:
                        return r.json()
                    except Exception:
                        return parse_json_payload(r.text)
                except Exception as exc:
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"XTick request failed: {last_exc}")

    @staticmethod
    def require_list(data: Any, endpoint: str) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        preview = str(data)[:160].replace("\n", " ")
        preview = re.sub(r"token=[^,'\s]+", "token=***", preview)
        raise RuntimeError(f"XTick {endpoint} returned unexpected payload: {preview}")

    async def stock_info(self, symbol: str = "index") -> list[dict[str, Any]]:
        data = await self.request("/doc/stockinfo", {"symbol": symbol})
        return self.require_list(data, "/doc/stockinfo")

    async def kline_market(
        self,
        code: str,
        start_date: str,
        end_date: str,
        *,
        asset_type: int = 1,
        fq: int = 1,
        period: str = "1d",
    ) -> Any:
        return await self.request(
            "/doc/kline/market",
            {
                "type": asset_type,
                "code": code,
                "fq": fq,
                "period": period,
                "startDate": start_date,
                "endDate": end_date,
            },
        )

    async def market_emotion(self, trade_date: str, asset_type: int = 1) -> Any:
        data = await self.request(
            "/doc/hot/emotion",
            {"type": asset_type, "tradeDate": trade_date},
        )
        return self.require_list(data, "/doc/hot/emotion")

    async def money_flow(self, code: str, start_date: str, end_date: str, asset_type: int = 1) -> Any:
        data = await self.request(
            "/doc/hot/money",
            {"type": asset_type, "code": code, "startDate": start_date, "endDate": end_date},
        )
        return self.require_list(data, "/doc/hot/money")

    async def news(self, trade_date: str, minutes: int = 0) -> Any:
        data = await self.request(
            "/doc/hot/news",
            {"minutes": minutes, "tradeDate": trade_date},
        )
        return self.require_list(data, "/doc/hot/news")

    async def longhubang_history(self, trade_date: str) -> Any:
        return await self.request(
            "/doc/order/longhubang",
            {"tradeDate": trade_date},
        )

    async def quant_data_realtime(self, field: str = "all", asset_type: int = 1) -> Any:
        return await self.request(
            "/doc/quant/data",
            {"type": asset_type, "field": field},
        )

    async def concept_stocks(self, symbol: str = "sw1") -> Any:
        return await self.request("/doc/hot/bk", {"symbol": symbol})


class SinaQuoteClient:
    provider = "sina"

    index_codes = ("sh000001", "sz399001", "sz399006", "sh000688", "bj899050")

    async def index_quotes(self, codes: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        quote_codes = codes or self.index_codes
        url = "https://hq.sinajs.cn/list=" + ",".join(quote_codes)
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            r = await client.get(url)
            r.raise_for_status()
        raw = r.content.decode("gbk", errors="ignore")
        out: list[dict[str, Any]] = []
        for code, payload in re.findall(r"hq_str_(\w+)=\"(.*?)\";", raw):
            parts = payload.split(",")
            if len(parts) < 10 or not parts[0]:
                continue
            prev_close = safe_float(parts[2])
            current = safe_float(parts[3]) or safe_float(parts[1])
            quote_date, quote_clock = "", ""
            for i, item in enumerate(parts):
                if re.match(r"20\d{2}-\d{2}-\d{2}$", item):
                    quote_date = item
                    quote_clock = parts[i + 1] if i + 1 < len(parts) else ""
                    break
            out.append(
                {
                    "provider": self.provider,
                    "code": code,
                    "name": parts[0],
                    "current": round(current, 4),
                    "prev_close": round(prev_close, 4),
                    "pct_chg": round((current - prev_close) / prev_close * 100, 4) if prev_close else 0,
                    "open": safe_float(parts[1]),
                    "high": safe_float(parts[4]),
                    "low": safe_float(parts[5]),
                    "amount_yuan": safe_float(parts[9]),
                    "quote_time": f"{quote_date} {quote_clock}".strip(),
                }
            )
        return out


class TencentQuoteClient:
    provider = "tencent"

    @staticmethod
    def quote_symbol(code: str) -> str:
        raw = str(code).strip().lower()
        if raw.startswith(("sh", "sz", "bj")):
            return raw
        symbol = re.sub(r"\D", "", raw)[:6]
        if symbol.startswith(("6", "9")):
            return f"sh{symbol}"
        if symbol.startswith(("4", "8")):
            return f"bj{symbol}"
        return f"sz{symbol}"

    async def quotes(self, codes: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        symbols = [self.quote_symbol(x) for x in codes if str(x).strip()]
        if not symbols:
            return []
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            r = await client.get("https://qt.gtimg.cn/q=" + ",".join(symbols))
            r.raise_for_status()
        raw = r.content.decode("gbk", errors="ignore")
        out: list[dict[str, Any]] = []
        for symbol, payload in re.findall(r"v_(\w+)=\"(.*?)\";", raw):
            parts = payload.split("~")
            if len(parts) < 50 or not parts[1]:
                continue
            out.append(
                {
                    "provider": self.provider,
                    "code": parts[2],
                    "symbol": symbol,
                    "name": parts[1],
                    "current": safe_float(parts[3]),
                    "prev_close": safe_float(parts[4]),
                    "open": safe_float(parts[5]),
                    "volume": safe_float(parts[6]),
                    "amount_yuan": safe_float(parts[37]) * 10000,
                    "pct_chg": safe_float(parts[32]),
                    "change": safe_float(parts[31]),
                    "high": safe_float(parts[33]),
                    "low": safe_float(parts[34]),
                    "turnover_rate": safe_float(parts[38]),
                    "pe_dynamic": safe_float(parts[39]),
                    "pb": safe_float(parts[46]),
                    "total_mv_yi": safe_float(parts[45]),
                    "float_mv_yi": safe_float(parts[44]),
                    "limit_up": safe_float(parts[47]) if len(parts) > 47 else 0,
                    "limit_down": safe_float(parts[48]) if len(parts) > 48 else 0,
                    "quote_time": parts[30],
                }
            )
        return out


class SinaGlobalClient:
    provider = "sina_global"

    default_codes = (
        "gb_dji",
        "gb_ixic",
        "gb_inx",
        "hkHSI",
        "rt_hk00700",
        "rt_hk09988",
        "fx_susdcnh",
        "hf_GC",
        "hf_CL",
    )

    async def quotes(self, codes: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        quote_codes = codes or self.default_codes
        url = "https://hq.sinajs.cn/list=" + ",".join(quote_codes)
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            r = await client.get(url)
            r.raise_for_status()
        raw = r.content.decode("gbk", errors="ignore")
        out: list[dict[str, Any]] = []
        for code, payload in re.findall(r"hq_str_(\w+)=\"(.*?)\";", raw):
            parts = payload.split(",")
            if not parts or not parts[0]:
                continue
            row: dict[str, Any] = {"provider": self.provider, "code": code}
            if code.startswith("gb_") and len(parts) > 4:
                row.update(
                    {
                        "name": parts[0],
                        "current": safe_float(parts[1]),
                        "pct_chg": safe_float(parts[2]),
                        "change": safe_float(parts[4]),
                        "quote_time": parts[3],
                    }
                )
            elif code.startswith("hk") or code.startswith("rt_hk"):
                row.update(
                    {
                        "name": parts[1] if len(parts) > 1 else parts[0],
                        "current": safe_float(parts[6] if len(parts) > 6 else ""),
                        "pct_chg": safe_float(parts[8] if len(parts) > 8 else ""),
                        "change": safe_float(parts[7] if len(parts) > 7 else ""),
                        "quote_time": " ".join(x for x in [parts[17] if len(parts) > 17 else "", parts[18] if len(parts) > 18 else ""] if x),
                    }
                )
            elif code.startswith("fx_") and len(parts) > 2:
                row.update({"name": code.replace("fx_s", "").upper(), "current": safe_float(parts[1]), "pct_chg": 0, "quote_time": parts[0]})
            elif code.startswith("hf_") and len(parts) > 1:
                quote_time = " ".join(x for x in [parts[12] if len(parts) > 12 else "", parts[6] if len(parts) > 6 else ""] if x)
                row.update(
                    {
                        "name": parts[13] if len(parts) > 13 and parts[13] else code.replace("hf_", ""),
                        "current": safe_float(parts[0]),
                        # Sina futures payloads do not expose percent change in the
                        # same position as equities; keep pct neutral to avoid
                        # displaying price as a huge percentage move.
                        "pct_chg": 0,
                        "quote_time": quote_time,
                    }
                )
            if row.get("name"):
                out.append(row)
        return out


class SinaFinanceClient:
    provider = "sina_finance"

    source_map = {
        "balance": "fzb",
        "income": "lrb",
        "cashflow": "llb",
    }

    async def finance_statement(self, code: str, statement: str, limit_reports: int = 4) -> list[dict[str, Any]]:
        source = self.source_map.get(statement, statement)
        symbol = market_prefix(code)
        url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        params = {"paperCode": symbol, "source": source, "type": "0", "page": "1", "num": str(max(limit_reports, 1))}
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
        data = (((r.json().get("result") or {}).get("data")) or {})
        report_dates = data.get("report_date") or []
        report_list = data.get("report_list") or {}
        out: list[dict[str, Any]] = []
        for item in report_dates[:limit_reports]:
            report_date = str(item.get("date_value") or "")
            payload = report_list.get(report_date) or {}
            rows = payload.get("data") or []
            out.append(
                {
                    "provider": self.provider,
                    "code": re.sub(r"\D", "", str(code))[:6],
                    "symbol": symbol,
                    "statement": statement,
                    "report_date": report_date,
                    "publish_date": payload.get("publish_date"),
                    "is_audit": payload.get("is_audit"),
                    "currency": payload.get("rCurrency"),
                    "items_count": len(rows),
                    "items": [
                        {
                            "title": str(x.get("item_title") or ""),
                            "value": safe_float_or_none(x.get("item_value")),
                            "yoy": safe_float_or_none(x.get("item_tongbi")),
                        }
                        for x in rows
                        if x.get("item_title")
                    ],
                }
            )
        return out

    @staticmethod
    def pick(items: list[dict[str, Any]], names: tuple[str, ...]) -> float | None:
        for name in names:
            for item in items:
                if str(item.get("title")) == name and item.get("value") is not None:
                    return item.get("value")
        for name in names:
            for item in items:
                if name in str(item.get("title")) and item.get("value") is not None:
                    return item.get("value")
        return None

    async def financial_snapshot(self, code: str, limit_reports: int = 2) -> list[dict[str, Any]]:
        balance, income, cashflow = await asyncio.gather(
            self.finance_statement(code, "balance", limit_reports),
            self.finance_statement(code, "income", limit_reports),
            self.finance_statement(code, "cashflow", limit_reports),
        )
        by_date: dict[str, dict[str, Any]] = {}
        for rows in (balance, income, cashflow):
            for row in rows:
                by_date.setdefault(
                    row["report_date"],
                    {
                        "provider": self.provider,
                        "code": re.sub(r"\D", "", str(code))[:6],
                        "symbol": row.get("symbol"),
                        "report_date": row["report_date"],
                        "publish_date": row.get("publish_date"),
                    },
                )[f"{row['statement']}_items"] = row.get("items_count", 0)
                by_date[row["report_date"]][f"{row['statement']}_raw"] = row.get("items", [])
        for row in by_date.values():
            balance_items = row.get("balance_raw") or []
            income_items = row.get("income_raw") or []
            cashflow_items = row.get("cashflow_raw") or []
            row.update(
                {
                    "total_assets_yi": safe_yi(self.pick(balance_items, ("资产总计", "总资产"))),
                    "total_liability_yi": safe_yi(self.pick(balance_items, ("负债合计", "负债总计"))),
                    "monetary_fund_yi": safe_yi(self.pick(balance_items, ("货币资金",))),
                    "revenue_yi": safe_yi(self.pick(income_items, ("营业总收入", "营业收入"))),
                    "net_profit_yi": safe_yi(self.pick(income_items, ("归属于母公司股东的净利润", "净利润"))),
                    "operating_cashflow_yi": safe_yi(self.pick(cashflow_items, ("经营活动产生的现金流量净额",))),
                }
            )
            row.pop("balance_raw", None)
            row.pop("income_raw", None)
            row.pop("cashflow_raw", None)
        return sorted(by_date.values(), key=lambda x: str(x.get("report_date", "")), reverse=True)


class ExchangeMarginClient:
    provider = "exchange_margin"

    async def sse_summary(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.sse.com.cn/"}
        params = {
            "isPagination": "true",
            "beginDate": start_date.replace("-", ""),
            "endDate": end_date.replace("-", ""),
            "tabType": "",
            "stockCode": "",
            "pageHelp.pageSize": "5000",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "5",
        }
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r = await client.get("https://query.sse.com.cn/marketdata/tradedata/queryMargin.do", params=params)
            r.raise_for_status()
        out = []
        for item in r.json().get("result") or []:
            out.append(
                {
                    "provider": self.provider,
                    "market": "SSE",
                    "trade_date": str(item.get("opDate") or item.get("date") or item.get("tradeDate") or ""),
                    "margin_balance_yuan": safe_float(item.get("rzrqjyzl") or item.get("rzrqyl") or item.get("rzrqye")),
                    "fin_balance_yuan": safe_float(item.get("rzye")),
                    "fin_buy_yuan": safe_float(item.get("rzmre")),
                    "loan_balance_yuan": safe_float(item.get("rqylje")),
                }
            )
        return out

    async def szse_summary(self, date: str) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.szse.cn/disclosure/margin/margin/index.html"}
        base = datetime.strptime(hyphen_date(date), "%Y-%m-%d")
        last_payload: Any = None
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            for offset in range(0, 10):
                query_date = (base - timedelta(days=offset)).strftime("%Y-%m-%d")
                params = {
                    "SHOWTYPE": "JSON",
                    "CATALOGID": "1837_xxpl",
                    "txtDate": query_date,
                    "tab1PAGENO": "1",
                    "random": "0.7425245522795993",
                }
                r = await client.get("https://www.szse.cn/api/report/ShowReport/data", params=params)
                r.raise_for_status()
                tables = r.json()
                last_payload = tables
                rows = tables[0].get("data") if isinstance(tables, list) and tables else []
                if not rows:
                    continue
                out = []
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    out.append(
                        {
                            "provider": self.provider,
                            "market": "SZSE",
                            "trade_date": query_date,
                            "fin_buy_yi": safe_float(item.get("jrrzmr")),
                            "fin_balance_yi": safe_float(item.get("jrrzye")),
                            "loan_sell_volume_yi": safe_float(item.get("jrrjmc")),
                            "loan_balance_volume_yi": safe_float(item.get("jrrjyl")),
                            "loan_balance_yi": safe_float(item.get("jrrjye")),
                            "margin_balance_yi": safe_float(item.get("jrrzrjye")),
                        }
                    )
                if out:
                    return out
        raise RuntimeError(f"SZSE margin returned no rows: {str(last_payload)[:120]}")


class EastmoneyClient:
    provider = "eastmoney"

    base_url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    cache_dir = Path("backend/app/static/cache/eastmoney")
    default_fields = (
        "f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,"
        "f20,f21,f23,f62,f66,f69,f72,f75,f78,f81,f84,f87,"
        "f124,f128,f140,f141,f136,f152,f184"
    )
    search_token = "D43BF722C8E33BD0A0BCFE2EF5E1263C"

    async def clist(
        self,
        fs: str,
        *,
        fields: str | None = None,
        fid: str = "f3",
        pages: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        }
        cache_key = hashlib.sha1(f"{fs}|{fields or self.default_fields}|{fid}|{pages}|{page_size}".encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        rows: list[dict[str, Any]] = []
        urls = (
            self.base_url,
            "https://push2.eastmoney.com/api/qt/clist/get",
            "https://82.push2.eastmoney.com/api/qt/clist/get",
        )
        try:
            async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
                for pn in range(1, max(pages, 1) + 1):
                    params = {
                        "pn": pn,
                        "pz": page_size,
                        "po": 1,
                        "np": 1,
                        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                        "fltt": 2,
                        "invt": 2,
                        "fid": fid,
                        "fs": fs,
                        "fields": fields or self.default_fields,
                    }
                    data: dict[str, Any] | None = None
                    last_exc: Exception | None = None
                    for url in urls:
                        for attempt in range(2):
                            try:
                                r = await client.get(url, params=params)
                                r.raise_for_status()
                                data = r.json().get("data") or {}
                                break
                            except Exception as exc:
                                last_exc = exc
                                await asyncio.sleep(0.45 * (attempt + 1))
                        if data is not None:
                            break
                    if data is None:
                        raise RuntimeError(f"Eastmoney clist failed: {type(last_exc).__name__}: {last_exc}")
                    diff = data.get("diff") or []
                    rows.extend(diff)
                    total = safe_int(data.get("total"))
                    if not diff or (total and len(rows) >= total):
                        break
                    await asyncio.sleep(0.12)
            self.write_cache(cache_path, rows)
            return rows
        except Exception as exc:
            cached = self.read_cache(cache_path)
            if cached:
                return cached
            raise RuntimeError(f"Eastmoney clist failed: {type(exc).__name__}: {exc}") from exc

    def write_cache(self, path: Path, rows: list[dict[str, Any]]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"retrieved_at": retrieved_at(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return

    def read_cache(self, path: Path) -> list[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("rows") or []
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def normalize_quote(self, row: dict[str, Any], *, kind: str) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": kind,
            "code": str(row.get("f12", "")),
            "name": str(row.get("f14", "")),
            "current": safe_float(row.get("f2")),
            "pct_chg": safe_float(row.get("f3")),
            "change": safe_float(row.get("f4")),
            "volume": safe_float(row.get("f5")),
            "amount_yi": safe_yi(row.get("f6")),
            "turnover_rate": safe_float(row.get("f8")),
            "pe_dynamic": safe_float(row.get("f9")),
            "volume_ratio": safe_float(row.get("f10")),
            "high": safe_float(row.get("f15")),
            "low": safe_float(row.get("f16")),
            "open": safe_float(row.get("f17")),
            "prev_close": safe_float(row.get("f18")),
            "total_mv_yi": safe_yi(row.get("f20")),
            "float_mv_yi": safe_yi(row.get("f21")),
            "pb": safe_float(row.get("f23")),
            "main_net_inflow_yi": safe_yi(row.get("f62")),
            "super_net_inflow_yi": safe_yi(row.get("f66")),
            "super_net_pct": safe_float(row.get("f69")),
            "big_net_inflow_yi": safe_yi(row.get("f72")),
            "big_net_pct": safe_float(row.get("f75")),
            "mid_net_inflow_yi": safe_yi(row.get("f78")),
            "mid_net_pct": safe_float(row.get("f81")),
            "small_net_inflow_yi": safe_yi(row.get("f84")),
            "small_net_pct": safe_float(row.get("f87")),
            "main_net_pct": safe_float(row.get("f184")),
            "leader": "" if row.get("f128") in (None, "-") else str(row.get("f128")),
            "leader_code": "" if row.get("f140") in (None, "-") else str(row.get("f140")),
            "leader_pct_chg": safe_float(row.get("f136")),
            "quote_time": ts_to_time(row.get("f124")),
        }

    async def a_spot(self, limit: int = 300) -> list[dict[str, Any]]:
        fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        rows = await self.clist(fs, pages=max(1, min(60, (limit + 99) // 100)), page_size=100)
        return [self.normalize_quote(x, kind="a_share") for x in rows[:limit]]

    async def board_rank(self, kind: str = "industry", limit: int = 500) -> list[dict[str, Any]]:
        fs = "m:90+t:2" if kind == "industry" else "m:90+t:3"
        rows = await self.clist(fs, pages=max(1, min(8, (limit + 99) // 100)), page_size=100)
        return [self.normalize_quote(x, kind=kind) for x in rows[:limit]]

    async def industry_rank(self, limit: int = 500) -> list[dict[str, Any]]:
        return await self.board_rank("industry", limit)

    async def concept_rank(self, limit: int = 500) -> list[dict[str, Any]]:
        return await self.board_rank("concept", limit)

    async def etf_rank(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.clist("b:MK0021,b:MK0022,b:MK0023,b:MK0024", pages=max(1, min(16, (limit + 99) // 100)), page_size=100)
        return [self.normalize_quote(x, kind="etf") for x in rows[:limit]]

    async def board_constituents(self, board_code: str, limit: int = 200) -> list[dict[str, Any]]:
        code = board_code.strip().upper()
        if not code.startswith("BK"):
            return []
        rows = await self.clist(f"b:{code}", pages=max(1, min(8, (limit + 99) // 100)), page_size=100)
        return [self.normalize_quote(x, kind="board_constituent") for x in rows[:limit]]

    async def search_board(self, keyword: str) -> list[dict[str, Any]]:
        if not keyword.strip():
            return []
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"}
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            r = await client.get(
                "https://searchapi.eastmoney.com/api/suggest/get",
                params={"input": keyword.strip(), "type": "14", "token": self.search_token},
            )
            r.raise_for_status()
        rows = ((r.json().get("QuotationCodeTable") or {}).get("Data") or [])
        return [
            {
                "provider": self.provider,
                "code": str(x.get("Code") or x.get("UnifiedCode") or ""),
                "name": str(x.get("Name") or ""),
                "quote_id": str(x.get("QuoteID") or ""),
                "security_type": str(x.get("SecurityTypeName") or ""),
            }
            for x in rows
        ]

    async def board_constituents_by_name(self, name: str, limit: int = 200) -> tuple[str, list[dict[str, Any]]]:
        target = name.strip()
        if re.fullmatch(r"BK\d{4}", target, flags=re.I):
            code = target.upper()
            return code, await self.board_constituents(code, limit)
        if not target:
            return "", []
        for hit in await self.search_board(target):
            code = str(hit.get("code", ""))
            if code.startswith("BK"):
                return code, await self.board_constituents(code, limit)
        boards = await self.industry_rank(600)
        if not any(target in x.get("name", "") or x.get("name", "") in target for x in boards):
            boards += await self.concept_rank(600)
        exact = [x for x in boards if x.get("name") == target]
        fuzzy = [x for x in boards if target in x.get("name", "") or x.get("name", "") in target]
        hit = (exact or fuzzy or [None])[0]
        if not hit:
            return "", []
        code = str(hit.get("code", ""))
        return code, await self.board_constituents(code, limit)

    async def stock_fund_flow_history(self, code: str, limit: int = 120) -> list[dict[str, Any]]:
        symbol = re.sub(r"\D", "", str(code))[:6]
        if not symbol:
            return []
        params = {
            "lmt": str(max(1, min(limit, 120))),
            "klt": "101",
            "secid": eastmoney_secid(symbol),
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        cache_key = hashlib.sha1(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"fflow_{cache_key}.json"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
            "Origin": "https://quote.eastmoney.com",
            "Accept": "application/json,text/plain,*/*",
            "Connection": "close",
        }
        try:
            payload: dict[str, Any] | None = None
            last_exc: Exception | None = None
            urls = (
                "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            )
            async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
                for attempt in range(4):
                    for url in urls:
                        try:
                            r = await client.get(url, params=params)
                            r.raise_for_status()
                            payload = r.json()
                            break
                        except Exception as exc:
                            last_exc = exc
                            await asyncio.sleep(0.35 * (attempt + 1))
                    if payload is not None:
                        break
            if payload is None:
                raise RuntimeError(str(last_exc))
            lines = ((payload.get("data") or {}).get("klines")) or []
            rows: list[dict[str, Any]] = []
            for line in lines:
                parts = str(line).split(",")
                if len(parts) < 11:
                    continue
                rows.append(
                    {
                        "provider": self.provider,
                        "category": "stock_fund_flow_day",
                        "code": symbol,
                        "trade_date": parts[0],
                        "main_net_yi": safe_yi(parts[1]),
                        "small_net_yi": safe_yi(parts[2]),
                        "mid_net_yi": safe_yi(parts[3]),
                        "big_net_yi": safe_yi(parts[4]),
                        "super_net_yi": safe_yi(parts[5]),
                        "main_net_pct": safe_float(parts[6]),
                        "small_net_pct": safe_float(parts[7]),
                        "mid_net_pct": safe_float(parts[8]),
                        "big_net_pct": safe_float(parts[9]),
                        "super_net_pct": safe_float(parts[10]),
                    }
                )
            if rows:
                self.write_cache(cache_path, rows)
            return rows
        except Exception as exc:
            cached = self.read_cache(cache_path)
            if cached:
                return cached
            raise RuntimeError(f"Eastmoney stock fund flow {symbol} failed: {type(exc).__name__}: {exc}") from exc

    async def stock_fund_flow_windows(self, code: str, float_mv_yi: float, windows: tuple[int, ...] = (3, 5, 20)) -> dict[str, float]:
        if not float_mv_yi:
            return {}
        rows = await self.stock_fund_flow_history(code, max(windows) + 8)
        if not rows:
            return {}
        out: dict[str, float] = {}
        for days in windows:
            valid = rows[-days:]
            if len(valid) < days:
                continue
            total_main = sum(safe_float(x.get("main_net_yi")) for x in valid)
            out[f"flow_{days}d"] = round(total_main / float_mv_yi * 100, 2)
        return out

    async def _limit_pool(self, endpoint: str, sort: str, category: str, date: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        query_date = compact_date() if not date else str(date).replace("-", "")[:8]
        params = {
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": "0",
            "pagesize": str(max(1, min(limit, 10000))),
            "sort": sort,
            "date": query_date,
        }
        cache_key = hashlib.sha1(json.dumps({"endpoint": endpoint, **params}, sort_keys=True).encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"limit_{cache_key}.json"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
        urls = (f"https://push2ex.eastmoney.com/{endpoint}", f"http://push2ex.eastmoney.com/{endpoint}")
        try:
            payload: dict[str, Any] | None = None
            last_exc: Exception | None = None
            async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
                for url in urls:
                    try:
                        r = await client.get(url, params=params)
                        r.raise_for_status()
                        payload = r.json()
                        break
                    except Exception as exc:
                        last_exc = exc
                        await asyncio.sleep(0.25)
            if payload is None:
                raise RuntimeError(str(last_exc))
            raw = ((payload.get("data") or {}).get("pool")) or []
            rows = [self._normalize_limit_pool_row(x, category, query_date) for x in raw[:limit] if isinstance(x, dict)]
            if rows:
                self.write_cache(cache_path, rows)
            return rows
        except Exception as exc:
            cached = self.read_cache(cache_path)
            if cached:
                return cached
            raise RuntimeError(f"Eastmoney limit pool {endpoint} failed: {type(exc).__name__}: {exc}") from exc

    def _normalize_limit_pool_row(self, row: dict[str, Any], category: str, query_date: str) -> dict[str, Any]:
        zttj = row.get("zttj") if isinstance(row.get("zttj"), dict) else {}
        return {
            "provider": self.provider,
            "category": category,
            "trade_date": hyphen_date(query_date),
            "code": str(row.get("c") or ""),
            "name": str(row.get("n") or ""),
            "price": round(safe_float(row.get("p")) / 1000, 4),
            "limit_price": round(safe_float(row.get("ztp")) / 1000, 4),
            "pct_chg": safe_float(row.get("zdp")),
            "amount_yi": safe_yi(row.get("amount")),
            "float_mv_yi": safe_yi(row.get("ltsz")),
            "total_mv_yi": safe_yi(row.get("tshare")),
            "turnover_rate": safe_float(row.get("hs")),
            "limit_days": safe_int(row.get("lbc") or row.get("days")),
            "zt_stat": f"{zttj.get('days', '?')}天{zttj.get('ct', '?')}板" if zttj else "",
            "first_limit_time": zt_time(row.get("fbt") or row.get("yfbt")),
            "last_limit_time": zt_time(row.get("lbt")),
            "seal_fund_yi": safe_yi(row.get("fund")),
            "break_times": safe_int(row.get("zbc") or row.get("oc")),
            "industry": str(row.get("hybk") or ""),
            "amplitude": safe_float(row.get("zf")),
            "speed": safe_float(row.get("zs")),
        }

    async def limit_up_pool(self, date: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return await self._limit_pool("getTopicZTPool", "fbt:asc", "limit_up_pool", date, limit)

    async def break_limit_pool(self, date: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return await self._limit_pool("getTopicZBPool", "fbt:asc", "break_limit_pool", date, limit)

    async def limit_down_pool(self, date: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return await self._limit_pool("getTopicDTPool", "fund:asc", "limit_down_pool", date, limit)

    async def yesterday_limit_pool(self, date: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return await self._limit_pool("getYesterdayZTPool", "zs:desc", "yesterday_limit_pool", date, limit)

    async def datacenter(
        self,
        report_name: str,
        *,
        columns: str = "ALL",
        filter_: str = "",
        sort_columns: str = "",
        sort_types: str = "",
        pages: int = 1,
        page_size: int = 100,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        }
        params: dict[str, Any] = {
            "reportName": report_name,
            "columns": columns,
            "pageNumber": "1",
            "pageSize": str(page_size),
            "source": "WEB",
            "client": "WEB",
        }
        if filter_:
            params["filter"] = filter_
        if sort_columns:
            params["sortColumns"] = sort_columns
        if sort_types:
            params["sortTypes"] = sort_types
        if extra:
            params.update(extra)
        cache_key = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"dc_{cache_key}.json"
        rows: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
                total_pages = max(1, pages)
                for page in range(1, total_pages + 1):
                    params["pageNumber"] = str(page)
                    params["p"] = str(page)
                    params["pageNo"] = str(page)
                    params["pageNum"] = str(page)
                    r = await client.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params=params)
                    r.raise_for_status()
                    payload = r.json()
                    result = payload.get("result") or {}
                    if not result and payload.get("success") is False:
                        raise RuntimeError(str(payload.get("message") or "empty result"))
                    data = result.get("data") or []
                    rows.extend(x for x in data if isinstance(x, dict))
                    total_pages = min(max(safe_int(result.get("pages"), 1), 1), max(1, pages))
                    if not data or page >= total_pages:
                        break
                    await asyncio.sleep(0.15)
            self.write_cache(cache_path, rows)
            return rows
        except Exception as exc:
            cached = self.read_cache(cache_path)
            if cached:
                return cached
            raise RuntimeError(f"Eastmoney datacenter {report_name} failed: {type(exc).__name__}: {exc}") from exc

    async def lhb_daily(self, start_date: str, end_date: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_=f"(TRADE_DATE<='{hyphen_date(end_date)}')(TRADE_DATE>='{hyphen_date(start_date)}')",
            sort_columns="SECURITY_CODE,TRADE_DATE",
            sort_types="1,-1",
            pages=max(1, min(8, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "lhb_daily",
                "trade_date": hyphen_date(x.get("TRADE_DATE")),
                "code": str(x.get("SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "reason": str(x.get("EXPLANATION") or x.get("EXPLAIN") or ""),
                "close": safe_float(x.get("CLOSE_PRICE")),
                "pct_chg": safe_float(x.get("CHANGE_RATE")),
                "net_buy_yi": safe_yi(x.get("BILLBOARD_NET_AMT")),
                "buy_yi": safe_yi(x.get("BILLBOARD_BUY_AMT")),
                "sell_yi": safe_yi(x.get("BILLBOARD_SELL_AMT")),
                "deal_yi": safe_yi(x.get("BILLBOARD_DEAL_AMT")),
                "turnover_rate": safe_float(x.get("TURNOVERRATE")),
            }
            for x in rows[:limit]
        ]

    async def lhb_institution_trades(self, start_date: str, end_date: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPT_ORGANIZATION_TRADE_DETAILS",
            filter_=f"(TRADE_DATE>='{hyphen_date(start_date)}')(TRADE_DATE<='{hyphen_date(end_date)}')",
            sort_columns="NET_BUY_AMT,TRADE_DATE,SECURITY_CODE",
            sort_types="-1,-1,1",
            pages=max(1, min(8, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "lhb_institution",
                "trade_date": hyphen_date(x.get("TRADE_DATE")),
                "code": str(x.get("SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "reason": str(x.get("EXPLANATION") or ""),
                "close": safe_float(x.get("CLOSE_PRICE")),
                "pct_chg": safe_float(x.get("CHANGE_RATE")),
                "buy_count": safe_int(x.get("BUY_COUNT") or x.get("BUY_TIMES")),
                "sell_count": safe_int(x.get("SELL_COUNT") or x.get("SELL_TIMES")),
                "institution_buy_yi": safe_yi(x.get("BUY_AMT")),
                "institution_sell_yi": safe_yi(x.get("SELL_AMT")),
                "institution_net_yi": safe_yi(x.get("NET_BUY_AMT")),
                "turnover_rate": safe_float(x.get("TURNOVERRATE")),
            }
            for x in rows[:limit]
        ]

    async def lhb_institution_seats(self, cycle: str = "01", limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPT_ORGANIZATION_SEATNEW",
            filter_=f'(STATISTICSCYCLE="{cycle}")',
            sort_columns="ONLIST_TIMES,SECURITY_CODE",
            sort_types="-1,1",
            pages=max(1, min(8, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "lhb_institution_seat",
                "cycle": cycle,
                "code": str(x.get("SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "board": str(x.get("BOARD_NAME") or ""),
                "pct_chg": safe_float(x.get("CHANGE_RATE")),
                "onlist_times": safe_int(x.get("ONLIST_TIMES")),
                "buy_times": safe_int(x.get("BUY_TIMES")),
                "sell_times": safe_int(x.get("SELL_TIMES")),
                "buy_yi": safe_yi(x.get("BUY_AMT")),
                "sell_yi": safe_yi(x.get("SELL_AMT")),
                "net_buy_yi": safe_yi(x.get("NET_BUY_AMT")),
            }
            for x in rows[:limit]
        ]

    async def margin_account(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPTA_WEB_MARGIN_DAILYTRADE",
            sort_columns="STATISTICS_DATE",
            sort_types="-1",
            pages=max(1, min(4, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "margin_account",
                "trade_date": hyphen_date(x.get("STATISTICS_DATE")),
                "fin_balance_yi": safe_float(x.get("FIN_BALANCE")),
                "loan_balance_yi": safe_float(x.get("LOAN_BALANCE")),
                "margin_balance_yi": safe_float(x.get("MARGIN_BALANCE")),
                "fin_buy_yi": safe_float(x.get("FIN_BUY_AMT")),
                "loan_sell_yi": safe_float(x.get("LOAN_SELL_AMT")),
                "margin_trade_yi": safe_float(x.get("MARGIN_TRADE_AMT")),
                "avg_guarantee_ratio": safe_float(x.get("AVG_GUARANTEE_RATIO")),
                "investor_num": safe_int(x.get("INVESTOR_NUM")),
                "trade_amt_ratio": safe_float(x.get("TRADE_AMT_RATIO")),
            }
            for x in rows[:limit]
        ]

    async def northbound_deal_history(self, limit: int = 20) -> list[dict[str, Any]]:
        labels = {"001": "沪股通", "003": "深股通", "005": "北向合计"}
        out: list[dict[str, Any]] = []
        for mutual_type, label in labels.items():
            rows = await self.datacenter(
                "RPT_MUTUAL_DEAL_HISTORY",
                filter_=f'(MUTUAL_TYPE="{mutual_type}")',
                sort_columns="TRADE_DATE",
                sort_types="-1",
                pages=1,
                page_size=limit,
            )
            out.extend(
                {
                    "provider": self.provider,
                    "category": "northbound_deal",
                    "type": label,
                    "trade_date": hyphen_date(x.get("TRADE_DATE")),
                    "deal_amt_yi": round(safe_float(x.get("DEAL_AMT")) / 100, 4),
                    "deal_num": safe_int(x.get("DEAL_NUM")),
                    "lead_stock": str(x.get("LEAD_STOCKS_NAME") or ""),
                    "lead_stock_code": str(x.get("LEAD_STOCKS_CODE") or ""),
                    "lead_stock_pct": safe_float(x.get("LS_CHANGE_RATE")),
                    "quota_balance": str(x.get("QUOTA_BALANCE_TEXT") or ""),
                }
                for x in rows[:limit]
            )
        return out

    async def restricted_release(self, start_date: str, end_date: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPT_LIFT_STAGE",
            columns=(
                "SECURITY_CODE,SECURITY_NAME_ABBR,FREE_DATE,CURRENT_FREE_SHARES,ABLE_FREE_SHARES,"
                "LIFT_MARKET_CAP,FREE_RATIO,NEW,B20_ADJCHRATE,A20_ADJCHRATE,FREE_SHARES_TYPE,TOTAL_RATIO,"
                "NON_FREE_SHARES,BATCH_HOLDER_NUM"
            ),
            filter_=f"(FREE_DATE>='{hyphen_date(start_date)}')(FREE_DATE<='{hyphen_date(end_date)}')",
            sort_columns="FREE_DATE,CURRENT_FREE_SHARES",
            sort_types="1,1",
            pages=max(1, min(12, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "restricted_release",
                "code": str(x.get("SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "free_date": hyphen_date(x.get("FREE_DATE")),
                "current_free_shares_wan": safe_float(x.get("CURRENT_FREE_SHARES")),
                "able_free_shares_wan": safe_float(x.get("ABLE_FREE_SHARES")),
                "lift_market_cap_yi": round(safe_float(x.get("LIFT_MARKET_CAP")) / 10000, 4),
                "free_ratio": round(safe_float(x.get("FREE_RATIO")) * 100, 4),
                "total_ratio": round(safe_float(x.get("TOTAL_RATIO")) * 100, 4),
                "shares_type": str(x.get("FREE_SHARES_TYPE") or ""),
                "batch_holder_num": safe_int(x.get("BATCH_HOLDER_NUM")),
            }
            for x in rows[:limit]
        ]

    async def executive_hold_changes(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.datacenter(
            "RPT_EXECUTIVE_HOLD_DETAILS",
            columns="ALL",
            sort_columns="CHANGE_DATE,SECURITY_CODE,PERSON_NAME",
            sort_types="-1,1,1",
            pages=max(1, min(6, (limit + 99) // 100)),
            page_size=100,
        )
        return [
            {
                "provider": self.provider,
                "category": "executive_hold_change",
                "change_date": hyphen_date(x.get("CHANGE_DATE")),
                "code": str(x.get("SECURITY_CODE") or x.get("DERIVE_SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "person": str(x.get("PERSON_NAME") or ""),
                "change_reason": str(x.get("CHANGE_REASON") or x.get("CHANGE_TYPE") or ""),
                "change_shares": safe_float(x.get("CHANGE_SHARES") or x.get("CHANGE_NUM")),
                "avg_price": safe_float(x.get("AVERAGE_PRICE") or x.get("AVG_PRICE")),
                "after_shares": safe_float(x.get("AFTER_CHANGE_SHARES") or x.get("HOLD_NUM")),
            }
            for x in rows[:limit]
        ]

    async def fund_holdings(self, date: str | None = None, org_type: str = "fund", limit: int = 500) -> list[dict[str, Any]]:
        type_map = {"fund": "1", "qfii": "2", "social_security": "3", "broker": "4", "insurance": "5", "trust": "6"}
        report_date = hyphen_date(date or latest_quarter_end())
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/zlsj/"}
        params = {
            "date": report_date,
            "type": type_map.get(org_type, "1"),
            "zjc": "0",
            "sortField": "HOULD_NUM",
            "sortDirec": "1",
            "pageNum": "1",
            "pageSize": str(limit),
            "p": "1",
            "pageNo": "1",
        }
        cache_key = hashlib.sha1(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"fund_hold_{cache_key}.json"
        try:
            async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
                r = await client.get("http://data.eastmoney.com/dataapi/zlsj/list", params=params)
                r.raise_for_status()
            rows = r.json().get("data") or []
            self.write_cache(cache_path, rows)
        except Exception as exc:
            rows = self.read_cache(cache_path)
            if not rows:
                raise RuntimeError(f"Eastmoney fund holdings failed: {type(exc).__name__}: {exc}") from exc
        return [
            {
                "provider": self.provider,
                "category": "fund_holdings",
                "report_date": report_date,
                "org_type": str(x.get("ORG_TYPE_NAME") or org_type),
                "code": str(x.get("SECURITY_CODE") or ""),
                "name": str(x.get("SECURITY_NAME_ABBR") or ""),
                "holder_count": safe_int(x.get("HOULD_NUM")),
                "total_shares": safe_float(x.get("TOTAL_SHARES")),
                "hold_value_yi": safe_yi(x.get("HOLD_VALUE")),
                "free_shares_ratio": safe_float(x.get("FREESHARES_RATIO")),
                "total_shares_ratio": safe_float(x.get("TOTALSHARES_RATIO")),
                "change_label": str(x.get("HOLDCHA") or ""),
                "change_shares": safe_float(x.get("HOLDCHA_NUM")),
                "change_ratio": safe_float(x.get("HOLDCHA_RATIO")),
            }
            for x in rows[:limit]
        ]


class ThsClient:
    provider = "ths"

    async def industry_code_map(self) -> dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            r = await client.get("https://q.10jqka.com.cn/thshy/")
            r.raise_for_status()
        html = r.content.decode("gbk", errors="ignore")
        pairs = re.findall(r"thshy/detail/code/(\d+)/\"[^>]*>([^<]+)</a>", html)
        return {html_cell_text(name): code for code, name in pairs}

    async def industry_rank(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}
        urls = [
            "https://q.10jqka.com.cn/thshy/",
            "https://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/2/ajax/1/",
        ]
        rows: list[list[str]] = []
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            for url in urls:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    rows.extend(parse_html_table_rows(r.content.decode("gbk", errors="ignore"), 12))
                except Exception:
                    if not rows:
                        raise
                    break
        out = []
        for row in rows:
            out.append(
                {
                    "provider": self.provider,
                    "rank": safe_int(row[0]),
                    "name": row[1],
                    "pct_chg": safe_float(row[2]),
                    "amount_yi": safe_float(row[4]),
                    "net_inflow_yi": safe_float(row[5]),
                    "up_count": safe_int(row[6]),
                    "down_count": safe_int(row[7]),
                    "leader": row[9],
                    "leader_pct_chg": safe_float(row[11]),
                }
            )
        return out

    async def industry_constituents_by_name(self, name: str, limit: int = 80) -> tuple[str, list[dict[str, Any]]]:
        code_map = await self.industry_code_map()
        code = code_map.get(name)
        if not code:
            for industry_name, industry_code in code_map.items():
                if name in industry_name or industry_name in name:
                    code = industry_code
                    break
        if not code:
            return "", []

        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}
        rows: list[list[str]] = []
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            for page in range(1, 6):
                url = (
                    f"https://q.10jqka.com.cn/thshy/detail/code/{code}/"
                    if page == 1
                    else f"https://q.10jqka.com.cn/thshy/detail/code/{code}/page/{page}/"
                )
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    html = r.content.decode("gbk", errors="ignore")
                except Exception:
                    if rows:
                        break
                    raise
                page_rows = parse_html_table_rows(html, 13)
                if not page_rows:
                    break
                rows.extend(page_rows)
                if len(rows) >= limit:
                    break
                page_info = re.search(r'class="page_info">(\d+)/(\d+)</span>', html)
                if page_info and safe_int(page_info.group(1)) >= safe_int(page_info.group(2)):
                    break
                await asyncio.sleep(0.12)

        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            out.append(
                {
                    "provider": self.provider,
                    "kind": "industry_constituent",
                    "code": row[1],
                    "name": row[2],
                    "current": safe_float(row[3]),
                    "pct_chg": safe_float(row[4]),
                    "change": safe_float(row[5]),
                    "turnover_rate": safe_float(row[7]),
                    "volume_ratio": safe_float(row[8]),
                    "amplitude": safe_float(row[9]),
                    "amount_yi": safe_cn_money_yi(row[10]),
                    "float_mv_yi": safe_cn_money_yi(row[12]),
                    "main_net_inflow_yi": 0.0,
                    "pe_dynamic": 0.0,
                    "pb": 0.0,
                    "quote_time": retrieved_at(),
                }
            )
        return code, out


class DangInvestClient:
    provider = "danginvest"
    base_url = "https://dang-invest.com/api/market"

    mode_aliases = {
        "major": "industry",
        "industry": "industry",
        "大类行业": "industry",
        "sub": "ths_industry",
        "ths_industry": "ths_industry",
        "细分行业": "ths_industry",
        "concept": "ths_concept",
        "ths_concept": "ths_concept",
        "概念": "ths_concept",
    }

    sort_aliases = {
        "change_desc": "change_desc",
        "涨幅": "change_desc",
        "领涨": "change_desc",
        "change_asc": "change_asc",
        "跌幅": "change_asc",
        "领跌": "change_asc",
        "turnover_desc": "turnover_desc",
        "成交额": "turnover_desc",
        "market_cap_desc": "market_cap_desc",
        "总市值": "market_cap_desc",
    }

    async def request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://dang-invest.com/"}
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r = await client.get(f"{self.base_url}/{path.lstrip('/')}", params=params)
            r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, dict):
            raise RuntimeError("DangInvest returned non-object payload")
        return payload

    async def market_news(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        payload = await self.request("news", {"limit": min(max(limit, 1), 200), "offset": max(offset, 0)})
        rows = payload.get("data") or []
        return [
            {
                "provider": self.provider,
                "category": "market_news",
                "id": x.get("id"),
                "source": str(x.get("source") or ""),
                "published_at": str(x.get("published_at") or ""),
                "title": str(x.get("title") or ""),
                "content": str(x.get("content") or ""),
                "url": str(x.get("url") or ""),
            }
            for x in rows
            if isinstance(x, dict)
        ]

    async def boards_summary(self, mode: str = "sub", sort: str = "change_desc", limit: int = 300) -> list[dict[str, Any]]:
        api_mode = self.mode_aliases.get(mode, mode)
        api_sort = self.sort_aliases.get(sort, sort)
        payload = await self.request(
            "boards/summary",
            {"mode": api_mode, "sort": api_sort, "limit": min(max(limit, 1), 1000)},
        )
        data = payload.get("data") or {}
        rows = data.get("items") or []
        return [
            {
                "provider": self.provider,
                "kind": api_mode,
                "trade_date": str(payload.get("tradeDate") or ""),
                "snapshot_time": str(payload.get("asOf") or payload.get("snapshotTsMs") or ""),
                "group_key": str(x.get("groupKey") or ""),
                "name": str(x.get("groupLabel") or x.get("groupKey") or ""),
                "stock_count": safe_int(x.get("count")),
                "total_mv_yi": safe_yi(x.get("totalMarketCapYuan")),
                "amount_yi": safe_yi(x.get("totalTurnoverYuan")),
                "pct_chg": safe_float(x.get("changePct")),
                "size": str(x.get("size") or ""),
            }
            for x in rows
            if isinstance(x, dict)
        ]

    async def boards_detail(
        self,
        mode: str,
        group_key: str,
        sort: str = "change_desc",
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        api_mode = self.mode_aliases.get(mode, mode)
        api_sort = self.sort_aliases.get(sort, sort)
        payload = await self.request(
            "boards/detail",
            {
                "mode": api_mode,
                "groupKey": group_key,
                "sort": api_sort,
                "items_limit": min(max(limit, 1), 500),
                "items_offset": max(offset, 0),
            },
        )
        data = payload.get("data") or {}
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        items = data.get("items") or []
        normalized = [
            {
                "provider": self.provider,
                "kind": "danginvest_board_constituent",
                "code": str(x.get("code") or x.get("stockCode") or x.get("symbol") or ""),
                "name": str(x.get("name") or x.get("stockName") or x.get("shortName") or ""),
                "current": safe_float(x.get("price") or x.get("lastPrice") or x.get("close")),
                "pct_chg": safe_float(x.get("changePct") or x.get("pctChg")),
                "amount_yi": safe_yi(x.get("turnoverYuan") or x.get("amountYuan")),
                "total_mv_yi": safe_yi(x.get("marketCapYuan")),
                "float_mv_yi": safe_yi(x.get("floatMarketCapYuan")),
            }
            for x in items
            if isinstance(x, dict)
        ]
        return summary, normalized


class HhxgClient:
    provider = "hhxg"
    base_url = "https://hhxg.top/static/data"

    async def fetch_json(self, path: str) -> dict[str, Any] | list[Any]:
        headers = {"User-Agent": "a-share-research-skill/1.0", "X-Skill-Client": "codex"}
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r = await client.get(f"{self.base_url}/{path.lstrip('/')}")
            r.raise_for_status()
        return r.json()

    async def snapshot(self) -> dict[str, Any]:
        data = await self.fetch_json("assistant/skill_snapshot.json")
        return data if isinstance(data, dict) else {}

    async def trading_days(self, year: int | None = None) -> list[str]:
        target_year = year or datetime.now().year
        data = await self.fetch_json(f"calendar/trading_days_{target_year}.json")
        if isinstance(data, list):
            return [str(x) for x in data]
        return [str(x) for x in (data.get("days") or [])] if isinstance(data, dict) else []

    async def calendar_events(self, kind: str, month: str | None = None) -> list[dict[str, Any]]:
        if kind == "delivery":
            path = f"calendar/delivery_{datetime.now().year}.json"
        else:
            target_month = (month or datetime.now().strftime("%Y-%m")).replace("-", "")
            path = f"calendar/{kind}_{target_month}.json"
        data = await self.fetch_json(path)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return [x for x in (data.get("events") or []) if isinstance(x, dict)] if isinstance(data, dict) else []


class CninfoClient:
    provider = "cninfo"

    async def irm_questions(self, code: str, page_size: int = 30, page_num: int = 1) -> list[dict[str, Any]]:
        symbol = re.sub(r"\D", "", str(code))[:6]
        if not symbol:
            return []
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://irm.cninfo.com.cn/"}
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r1 = await client.post(
                "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
                data={"keyWord": symbol},
            )
            r1.raise_for_status()
            hits = (r1.json().get("data") or [])
            if not hits:
                return []
            org_id = str(hits[0].get("secid") or "")
            params = {
                "_t": "1",
                "stockcode": symbol,
                "orgId": org_id,
                "pageSize": min(max(page_size, 1), 100),
                "pageNum": max(page_num, 1),
                "keyWord": "",
                "startDay": "",
                "endDay": "",
            }
            r2 = await client.post("https://irm.cninfo.com.cn/newircs/company/question", params=params)
            r2.raise_for_status()
        rows = (r2.json().get("rows") or [])
        out: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "provider": self.provider,
                    "category": "irm_question",
                    "code": str(item.get("stockCode") or symbol),
                    "name": str(item.get("companyShortName") or ""),
                    "industry": "、".join(str(x) for x in (item.get("trade") or [])),
                    "question": str(item.get("mainContent") or ""),
                    "answer": str(item.get("attachedContent") or ""),
                    "answerer": str(item.get("attachedAuthor") or ""),
                    "ask_time": ts_to_time(item.get("pubDate")),
                    "answer_time": ts_to_time(item.get("attachedPubDate")),
                    "update_time": ts_to_time(item.get("updateDate")),
                    "question_id": str(item.get("indexId") or ""),
                }
            )
        return out

    async def announcements(
        self,
        *,
        keyword: str = "",
        stock_code: str = "",
        days: int = 30,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        end = datetime.now()
        start = end - timedelta(days=days)
        query = (stock_code or keyword).strip()
        column = ""
        if stock_code.startswith("6"):
            column = "sse"
        elif stock_code.startswith(("0", "3")):
            column = "szse"
        payload = {
            "pageNum": 1,
            "pageSize": min(max(limit, 1), 30),
            "column": column,
            "tabName": "fulltext",
            "plate": "",
            "stock": "",
            "searchkey": query,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start:%Y-%m-%d}~{end:%Y-%m-%d}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.cninfo.com.cn/",
            "Origin": "https://www.cninfo.com.cn",
        }
        async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
            r = await client.post("https://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload)
            r.raise_for_status()
        raw = (r.json().get("announcements") or [])[:limit]
        out: list[dict[str, Any]] = []
        for item in raw:
            title = re.sub(r"</?em>", "", str(item.get("announcementTitle", "")))
            sec_name = re.sub(r"</?em>", "", str(item.get("secName", "") or item.get("tileSecName", "")))
            adjunct = str(item.get("adjunctUrl", ""))
            out.append(
                {
                    "provider": self.provider,
                    "code": str(item.get("secCode", "")),
                    "name": sec_name,
                    "title": title,
                    "announcement_time": ts_to_time(item.get("announcementTime")),
                    "url": f"https://static.cninfo.com.cn/{adjunct}" if adjunct else "",
                    "type": str(item.get("announcementTypeName") or item.get("announcementType") or ""),
                }
            )
        return out


class TushareHttpClient:
    provider = "tushare"

    def __init__(self, token: str | None = None, base_url: str = "https://api.tushare.pro"):
        self.token = (token or os.getenv("TUSHARE_TOKEN", "")).strip()
        self.base_url = base_url

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def request(self, api_name: str, params: dict[str, Any] | None = None, fields: str = "") -> list[dict[str, Any]]:
        if not self.enabled:
            raise RuntimeError("TUSHARE_TOKEN is not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                self.base_url,
                json={"api_name": api_name, "token": self.token, "params": params or {}, "fields": fields},
            )
            r.raise_for_status()
        data = r.json().get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        return [dict(zip(columns, row)) for row in items]


async def probe_sources(include_samples: bool = False) -> list[SourceProbe]:
    probes: list[SourceProbe] = []

    xtick = XTickClient()
    if xtick.enabled:
        try:
            rows = await xtick.stock_info("index")
            probes.append(SourceProbe("xtick", True, "stock_master/index", "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe("xtick", False, "stock_master/index", str(exc)))
        trade_date = datetime.now().strftime("%Y-%m-%d")
        try:
            rows = await xtick.stock_info("etf")
            probes.append(SourceProbe("xtick", True, "stock_master/etf", "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe("xtick", False, "stock_master/etf", str(exc)))
        try:
            rows = await xtick.market_emotion(trade_date)
            probes.append(SourceProbe("xtick", True, "hot/market_emotion", "ok", len(rows) if hasattr(rows, "__len__") else 1, sample=rows[:1] if include_samples and isinstance(rows, list) else None))
        except Exception as exc:
            probes.append(SourceProbe("xtick", False, "hot/market_emotion", str(exc)))
        try:
            rows = await xtick.money_flow("all", trade_date, trade_date)
            probes.append(SourceProbe("xtick", True, "hot/money_flow_all", "ok", len(rows) if hasattr(rows, "__len__") else 1, sample=rows[:2] if include_samples and isinstance(rows, list) else None))
        except Exception as exc:
            probes.append(SourceProbe("xtick", False, "hot/money_flow_all", str(exc)))
    else:
        probes.append(SourceProbe("xtick", False, "stock_master/index", "XTICK_TOKEN not configured"))

    try:
        rows = await SinaQuoteClient().index_quotes()
        probes.append(SourceProbe("sina", True, "index_realtime", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("sina", False, "index_realtime", str(exc)))

    try:
        rows = await TencentQuoteClient().quotes(("600519", "000001", "430047"))
        probes.append(SourceProbe("tencent", True, "a_share_realtime_quote", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("tencent", False, "a_share_realtime_quote", str(exc)))

    try:
        ths = ThsClient()
        rows = await ths.industry_rank()
        probes.append(SourceProbe("ths", True, "industry_rank/fund_flow", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("ths", False, "industry_rank/fund_flow", str(exc)))
    try:
        code, rows = await ThsClient().industry_constituents_by_name("光伏设备", 30)
        probes.append(SourceProbe("ths", True, f"industry_constituents/{code or '光伏设备'}", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("ths", False, "industry_constituents/光伏设备", str(exc)))

    east = EastmoneyClient()
    today = datetime.now()
    start_10 = (today - timedelta(days=10)).strftime("%Y%m%d")
    end_today = today.strftime("%Y%m%d")
    future_180 = (today + timedelta(days=180)).strftime("%Y%m%d")
    for name, category, coro in [
        ("eastmoney", "a_share_spot/fund_flow", east.a_spot(30)),
        ("eastmoney", "industry_rank/fund_flow", east.industry_rank(120)),
        ("eastmoney", "concept_rank/fund_flow", east.concept_rank(120)),
        ("eastmoney", "etf_rank/fund_flow", east.etf_rank(60)),
    ]:
        try:
            rows = await coro
            probes.append(SourceProbe(name, True, category, "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe(name, False, category, str(exc)))

    try:
        code, rows = await east.board_constituents_by_name("光伏设备", 30)
        probes.append(SourceProbe("eastmoney", True, f"board_constituents/{code or '光伏设备'}", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("eastmoney", False, "board_constituents/光伏设备", str(exc)))
    try:
        rows = await east.stock_fund_flow_history("600519", 5)
        probes.append(SourceProbe("eastmoney", True, "stock_fund_flow_120d/push2his", "ok", len(rows), sample=rows[-3:] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("eastmoney", False, "stock_fund_flow_120d/push2his", str(exc)))
    try:
        rows = await east.limit_up_pool(end_today, 20)
        probes.append(SourceProbe("eastmoney", True, "limit_up_pool/push2ex", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("eastmoney", False, "limit_up_pool/push2ex", str(exc)))

    for category, coro in [
        ("lhb/daily_public", east.lhb_daily(start_10, end_today, 30)),
        ("lhb/institution_trade_public", east.lhb_institution_trades(start_10, end_today, 30)),
        ("lhb/institution_seat_public", east.lhb_institution_seats("01", 30)),
        ("margin/eastmoney_account_public", east.margin_account(10)),
        ("northbound/eastmoney_deal_public", east.northbound_deal_history(3)),
        ("unlock/eastmoney_restricted_public", east.restricted_release(end_today, future_180, 30)),
        ("reduction/eastmoney_executive_hold_public", east.executive_hold_changes(30)),
        ("institution/eastmoney_fund_hold_public", east.fund_holdings(limit=30)),
    ]:
        try:
            rows = await coro
            probes.append(SourceProbe("eastmoney", True, category, "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe("eastmoney", False, category, str(exc)))

    sina_finance = SinaFinanceClient()
    try:
        rows = await sina_finance.financial_snapshot("600519", 1)
        probes.append(SourceProbe("sina_finance", True, "financial_three_statements", "ok", len(rows), sample=rows[:1] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("sina_finance", False, "financial_three_statements", str(exc)))

    exchange_margin = ExchangeMarginClient()
    try:
        rows = await exchange_margin.sse_summary(start_10, end_today)
        probes.append(SourceProbe("exchange", True, "margin/sse_official", "ok", len(rows), sample=rows[:2] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("exchange", False, "margin/sse_official", str(exc)))
    try:
        rows = await exchange_margin.szse_summary(end_today)
        probes.append(SourceProbe("exchange", True, "margin/szse_official", "ok", len(rows), sample=rows[:2] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("exchange", False, "margin/szse_official", str(exc)))

    try:
        rows = await CninfoClient().announcements(days=3, limit=5)
        probes.append(SourceProbe("cninfo", True, "announcements/latest", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("cninfo", False, "announcements/latest", str(exc)))
    try:
        rows = await CninfoClient().irm_questions("002594", page_size=5)
        probes.append(SourceProbe("cninfo", True, "irm/investor_questions", "ok", len(rows), sample=rows[:2] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("cninfo", False, "irm/investor_questions", str(exc)))

    dang = DangInvestClient()
    try:
        rows = await dang.market_news(5)
        probes.append(SourceProbe("danginvest", True, "market_news", "ok", len(rows), sample=rows[:2] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("danginvest", False, "market_news", str(exc)))
    try:
        rows = await dang.boards_summary("sub", "change_desc", 20)
        probes.append(SourceProbe("danginvest", True, "boards_summary/ths_industry", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("danginvest", False, "boards_summary/ths_industry", str(exc)))

    hhxg = HhxgClient()
    try:
        data = await hhxg.snapshot()
        sections = [k for k in ("market", "hot_themes", "ladder", "hotmoney", "sectors", "news") if data.get(k)]
        probes.append(SourceProbe("hhxg", True, "daily_snapshot/market_theme_ladder", "ok", len(sections), sample={k: data.get(k) for k in sections[:2]} if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("hhxg", False, "daily_snapshot/market_theme_ladder", str(exc)))
    try:
        rows = await hhxg.trading_days()
        probes.append(SourceProbe("hhxg", True, "calendar/trading_days", "ok", len(rows), sample=rows[:5] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("hhxg", False, "calendar/trading_days", str(exc)))

    try:
        rows = await SinaGlobalClient().quotes()
        probes.append(SourceProbe("sina_global", True, "global_quotes", "ok", len(rows), sample=rows[:4] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("sina_global", False, "global_quotes", str(exc)))

    tushare = TushareHttpClient()
    if tushare.enabled:
        try:
            rows = await tushare.request("trade_cal", {"start_date": datetime.now().strftime("%Y%m%d"), "end_date": datetime.now().strftime("%Y%m%d")}, "exchange,cal_date,is_open")
            probes.append(SourceProbe("tushare", True, "trade_cal/http", "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe("tushare", False, "trade_cal/http", str(exc)))
    else:
        probes.append(SourceProbe("tushare", False, "pro_market/fundamental/http", "TUSHARE_TOKEN not configured"))

    for provider, env_name, category in [
        ("equal_data", "EQUAL_DATA_API_KEY", "events/institution/announcement"),
        ("tavily", "TAVILY_API_KEY", "news_search"),
        ("serper", "SERPER_API_KEY", "news_search"),
        ("serpapi", "SERPAPI_API_KEY", "news_search"),
        ("brave", "BRAVE_API_KEY", "news_search"),
        ("searxng", "SEARXNG_URL", "metasearch"),
    ]:
        configured = bool(os.getenv(env_name, "").strip())
        probes.append(SourceProbe(provider, configured, category, "configured" if configured else f"{env_name} not configured"))

    return probes
