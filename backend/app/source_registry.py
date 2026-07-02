from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


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
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(f"{self.base_url}{path}", params=payload)
            r.raise_for_status()
            try:
                return r.json()
            except Exception:
                return parse_json_payload(r.text)

    async def stock_info(self, symbol: str = "index") -> list[dict[str, Any]]:
        data = await self.request("/doc/stockinfo", {"symbol": symbol})
        return data if isinstance(data, list) else []

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
        return await self.request(
            "/doc/hot/emotion",
            {"type": asset_type, "tradeDate": trade_date},
        )


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


class ThsClient:
    provider = "ths"

    async def industry_rank(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}
        urls = [
            "https://q.10jqka.com.cn/thshy/",
            "https://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/2/ajax/1/",
        ]
        rows: list[list[str]] = []
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            for url in urls:
                r = await client.get(url)
                r.raise_for_status()
                rows.extend(parse_html_table_rows(r.content.decode("gbk", errors="ignore"), 12))
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


async def probe_sources(include_samples: bool = False) -> list[SourceProbe]:
    probes: list[SourceProbe] = []

    xtick = XTickClient()
    if xtick.enabled:
        try:
            rows = await xtick.stock_info("index")
            probes.append(SourceProbe("xtick", True, "stock_master/index", "ok", len(rows), sample=rows[:3] if include_samples else None))
        except Exception as exc:
            probes.append(SourceProbe("xtick", False, "stock_master/index", str(exc)))
    else:
        probes.append(SourceProbe("xtick", False, "stock_master/index", "XTICK_TOKEN not configured"))

    try:
        rows = await SinaQuoteClient().index_quotes()
        probes.append(SourceProbe("sina", True, "index_realtime", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("sina", False, "index_realtime", str(exc)))

    try:
        rows = await ThsClient().industry_rank()
        probes.append(SourceProbe("ths", True, "industry_rank/fund_flow", "ok", len(rows), sample=rows[:3] if include_samples else None))
    except Exception as exc:
        probes.append(SourceProbe("ths", False, "industry_rank/fund_flow", str(exc)))

    for provider, env_name, category in [
        ("tushare", "TUSHARE_TOKEN", "pro_market/fundamental"),
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
