from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, Header, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings

from backend.app.expanded_reports import EXPANDED_REPORT_IDS, render_expanded_report
from backend.app.source_registry import (
    CninfoClient,
    EastmoneyClient,
    SinaFinanceClient,
    XTickClient,
    retrieved_at,
)


# =========================
# Config
# =========================

class Settings(BaseSettings):
    app_env: str = "dev"
    data_provider: str = "demo"
    report_dir: str = "backend/app/static/reports"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    tavily_api_key: str = ""
    serper_api_key: str = ""
    serpapi_api_key: str = ""
    brave_api_key: str = ""
    searxng_url: str = ""
    tushare_token: str = ""
    xtick_token: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def report_path(self) -> Path:
        p = Path(self.report_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()


# =========================
# Models
# =========================

Impact = Literal["利多", "利空", "中性"]
ReportType = Literal[
    "market_replay",
    "quant_factor",
    "sector_stock",
    "agent_debate",
    "sector_flow_rotation",
    "smart_money_clusters",
    "sector_valuation_diagnosis",
    "trend_resonance",
    "watchlist_terminal",
    "index_etf_monitor",
    "liquidity_dashboard",
    "earnings_catalyst_calendar",
    "single_stock_event_risk",
    "industry_chain_map",
    "global_mapping",
]


@dataclass
class IndexSnapshot:
    name: str
    pct_chg: float
    up_count: int
    down_count: int
    main_net_inflow: float
    volatility: float = 50
    relative_strength: float = 50

    @property
    def up_ratio(self) -> float:
        return round(self.up_count / max(self.up_count + self.down_count, 1) * 100, 2)


@dataclass
class SectorFlow:
    name: str
    pct_chg: float
    main_net_inflow: float


@dataclass
class MarketEvent:
    title: str
    impact: Impact = "中性"
    pricing: str = "正在定价"
    source: str = "system"
    relation: str = "需盘面验证"
    url: str | None = None
    published_at: str | None = None


@dataclass
class MarketSnapshot:
    trade_date: str
    indices: list[IndexSnapshot]
    leaders: list[SectorFlow]
    laggards: list[SectorFlow]
    turnover_change_pct: float = 0
    northbound_flow: float | None = None
    events: list[MarketEvent] = field(default_factory=list)


@dataclass
class QuantSnapshot:
    trade_date: str
    index_name: str
    index_level: float
    ma5: float
    ma20: float
    momentum: float
    emotion: float
    capital: float
    composite: float
    trend: str = "→"
    percentile_60d: float = 15
    events: list[MarketEvent] = field(default_factory=list)

    @property
    def dist_ma5(self) -> float:
        return round((self.index_level - self.ma5) / self.ma5 * 100, 2)

    @property
    def dist_ma20(self) -> float:
        return round((self.index_level - self.ma20) / self.ma20 * 100, 2)


@dataclass
class StockFlow:
    code: str
    name: str
    float_mv: float
    flow_3d: float | None
    flow_5d: float | None
    flow_20d: float | None
    is_st: bool = False
    fundamentals: str = "待联网财务与公告校验"
    industry_position: str = "待确认"
    concept_rating: str = "中"


@dataclass
class SectorStockSnapshot:
    trade_date: str
    sector: str
    stocks: list[StockFlow]
    events: list[MarketEvent] = field(default_factory=list)


@dataclass
class AgentFinding:
    role: str
    verdict: str
    score: float
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        return cls(settings.openai_base_url, settings.openai_api_key, settings.openai_model)

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.base_url)

    @property
    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def public_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url if self.enabled else "",
            "model": self.model if self.enabled else "",
            "api_key_set": bool(self.api_key),
        }


def resolve_llm_config(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMConfig:
    return LLMConfig(
        base_url=(base_url or settings.openai_base_url or "").strip(),
        api_key=(api_key or settings.openai_api_key or "").strip(),
        model=(model or settings.openai_model or "").strip(),
    )


# =========================
# Utilities
# =========================

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def j(obj) -> str:
    def default(o):
        if dataclass_isinstance(o):
            return asdict(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    return json.dumps(obj, ensure_ascii=False, default=default)


def dataclass_isinstance(o) -> bool:
    return hasattr(o, "__dataclass_fields__")


def clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    try:
        if math.isnan(float(x)):
            return lo
    except Exception:
        return lo
    return max(lo, min(hi, float(x)))


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return default


def code_with_suffix(code: str) -> str:
    symbol = re.sub(r"\D", "", str(code))[:6]
    if symbol.startswith(("6", "5")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8", "9")):
        return f"{symbol}.BJ"
    return symbol


def tag(label: str) -> str:
    colors = {"超预期":"red","符合预期":"orange","不及预期":"green","利多":"red","利空":"green","中性":"blue","冰点":"blue","低迷":"green","活跃":"orange","沸点":"red","背离":"red","共振":"blue","首选":"red","次选":"orange","观察":"blue"}
    return f"<span class='tag {colors.get(label, 'gray')}'>{escape(label)}</span>"


# =========================
# DataHub
# =========================

class DataHub:
    async def market_snapshot(self) -> MarketSnapshot:
        if settings.data_provider == "akshare":
            got = await self._try_akshare_market()
            if got:
                return got
        return MarketSnapshot(
            trade_date=today(),
            indices=[
                IndexSnapshot("上证指数", 1.19, 1244, 1035, -136.21, 42, 62),
                IndexSnapshot("深证成指", 0.22, 1192, 1670, -372.30, 48, 51),
                IndexSnapshot("创业板指", 0.57, 522, 859, -208.80, 55, 56),
                IndexSnapshot("科创50", 4.67, 38, 9, 65.96, 75, 95),
            ],
            leaders=[
                SectorFlow("减肥药", 7.47, 19.83),
                SectorFlow("重组蛋白", 7.04, 7.84),
                SectorFlow("CRO概念", 6.58, 13.24),
                SectorFlow("创新药", 6.12, 45.60),
                SectorFlow("细胞免疫治疗", 5.78, 15.83),
            ],
            laggards=[
                SectorFlow("PCB概念", -3.12, -112.47),
                SectorFlow("华为手机", -3.09, -17.46),
                SectorFlow("医疗废物处理", -3.00, -2.14),
                SectorFlow("回购增持再贷款", -2.97, -174.37),
                SectorFlow("苹果概念", -2.89, -103.23),
            ],
            turnover_change_pct=8.4,
            events=[
                MarketEvent("政策预期升温，成长板块修复", "利多", "正在定价", "Demo", "科创与医药共振"),
                MarketEvent("隔夜科技线波动放大", "中性", "已消化", "Demo", "电子链分歧"),
            ],
        )

    async def quant_snapshot(self) -> QuantSnapshot:
        return QuantSnapshot(
            trade_date=today(),
            index_name="上证指数",
            index_level=4075.18,
            ma5=4087.96,
            ma20=4063.66,
            momentum=3,
            emotion=6,
            capital=36,
            composite=15,
            trend="↓",
            percentile_60d=12,
            events=[
                MarketEvent("指数收涨但因子仍处冰点", "中性", "正在定价", "Demo", "资金与情绪背离"),
                MarketEvent("政策预期托底，观察资金回流", "利多", "未充分定价", "Demo", "政策底验证"),
            ],
        )

    async def sector_stock_snapshot(self, sector: str) -> SectorStockSnapshot:
        try:
            return await self._live_sector_stock_snapshot(sector)
        except Exception as exc:
            return self._sector_stock_fallback(sector, exc)

    async def _live_sector_stock_snapshot(self, sector: str) -> SectorStockSnapshot:
        east = EastmoneyClient()
        requested = (sector or "全市场").strip()
        full_market_aliases = {"", "全市场", "全市场扫描", "市场", "A股", "a股", "全部"}

        industry_boards, concept_boards = await asyncio.gather(
            east.industry_rank(160),
            east.concept_rank(220),
        )
        all_boards = industry_boards + concept_boards

        ranked_boards = self._rank_market_boards(all_boards)
        selected = ranked_boards[0] if ranked_boards else {}
        board_code = str(selected.get("code", "")) if selected else ""
        constituents: list[dict[str, Any]] = []

        if requested not in full_market_aliases:
            board_code, constituents = await east.board_constituents_by_name(requested, 240)
            selected = self._match_board(all_boards, board_code, requested) or {
                "name": requested,
                "code": board_code,
                "kind": "custom",
                "pct_chg": 0,
                "main_net_inflow_yi": 0,
                "main_net_pct": 0,
                "leader": "",
                "leader_pct_chg": 0,
                "quote_time": retrieved_at(),
            }

        if not constituents and board_code:
            constituents = await east.board_constituents(board_code, 240)

        if not constituents:
            constituents = await east.a_spot(100)
            selected = {
                "name": requested if requested not in full_market_aliases else "全市场强势股",
                "code": "",
                "kind": "a_share",
                "pct_chg": 0,
                "main_net_inflow_yi": 0,
                "main_net_pct": 0,
                "leader": "",
                "leader_pct_chg": 0,
                "quote_time": retrieved_at(),
            }

        constituents = self._dedupe_constituents(constituents)
        constituents.sort(
            key=lambda x: (
                num(x.get("main_net_inflow_yi")),
                num(x.get("amount_yi")),
                num(x.get("pct_chg")),
            ),
            reverse=True,
        )

        flow_windows = await self._fund_flow_windows(constituents)
        top_for_detail = constituents[: min(10, len(constituents))]
        finance_map, announcement_map = await asyncio.gather(
            self._sina_finance_snapshots(top_for_detail[:8]),
            self._cninfo_announcements(top_for_detail),
        )

        target_name = str(selected.get("name") or requested or "全市场强势股")
        stocks: list[StockFlow] = []
        flow_missing = 0
        for row in constituents:
            code = str(row.get("code") or "")[:6]
            name = str(row.get("name") or "")
            float_mv = round(num(row.get("float_mv_yi")) or num(row.get("total_mv_yi")), 2)
            windows = flow_windows.get(code) or {}
            flow_3d = windows.get("flow_3d")
            flow_5d = windows.get("flow_5d")
            flow_20d = windows.get("flow_20d")
            if flow_3d is None:
                flow_3d = self._eastmoney_one_day_proxy(row)
                flow_missing += 1

            finance = finance_map.get(code, [])
            anns = announcement_map.get(code, [])
            stocks.append(
                StockFlow(
                    code_with_suffix(code),
                    name,
                    float_mv,
                    flow_3d,
                    flow_5d,
                    flow_20d,
                    is_st=("ST" in name.upper()),
                    fundamentals=self._fundamental_summary(row, finance, anns),
                    industry_position=self._industry_position(target_name, row),
                    concept_rating=self._concept_rating(row, flow_3d, flow_5d, flow_20d),
                )
            )

        quote_time = str(selected.get("quote_time") or retrieved_at())
        top_names = "、".join(x.get("name", "") for x in ranked_boards[:5] if x.get("name"))
        title_prefix = f"全市场精选：{target_name}" if requested in full_market_aliases else target_name
        events = [
            MarketEvent(
                f"全市场扫描锁定{target_name}",
                "利多" if num(selected.get("pct_chg")) > 0 and num(selected.get("main_net_inflow_yi")) > 0 else "中性",
                "已纳入页面",
                "Eastmoney",
                f"板块代码{board_code or '数据缺失'}；涨跌幅{num(selected.get('pct_chg')):.2f}%；主力净流{num(selected.get('main_net_inflow_yi')):.2f}亿；行情时间{quote_time}",
            ),
            MarketEvent(
                "全市场候选板块池",
                "中性",
                "数据审计",
                "Eastmoney",
                f"候选池来自行业+概念排名，前列为：{top_names or '数据缺失'}",
            ),
            MarketEvent(
                "资金口径说明",
                "中性",
                "数据口径",
                "Eastmoney/XTick",
                "优先用东财push2his近20个交易日主力净流入/流通市值计算3D、5D、20D；若东财失败再尝试XTick权限接口；仍缺失时才用东财最新主力净流/流通市值作1D代理。",
            ),
            MarketEvent(
                "数据抓取时间",
                "中性",
                "数据审计",
                "ProviderRegistry",
                retrieved_at(),
            ),
        ]
        if flow_missing:
            events.append(
                MarketEvent(
                    f"{flow_missing}只个股缺少历史资金窗口",
                    "中性",
                    "降级处理",
                    "DataAudit",
                    "这些个股未取得东财push2his或XTick历史窗口，保留东财1D代理或缺失标记，资金评分置信度下降。",
                )
            )
        for rows in announcement_map.values():
            for ann in rows[:1]:
                events.append(
                    MarketEvent(
                        str(ann.get("title") or "巨潮公告"),
                        "中性",
                        str(ann.get("type") or "公告核验"),
                        "CNINFO",
                        str(ann.get("name") or ann.get("code") or "重点成分股"),
                        str(ann.get("url") or "") or None,
                        str(ann.get("announcement_time") or "") or None,
                    )
                )
                if len(events) >= 14:
                    break
            if len(events) >= 14:
                break

        return SectorStockSnapshot(today(), title_prefix, stocks, events)

    def _choose_market_board(self, boards: list[dict[str, Any]]) -> dict[str, Any]:
        ranked = self._rank_market_boards(boards)
        return ranked[0] if ranked else (boards[0] if boards else {})

    def _rank_market_boards(self, boards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        excluded = ("昨日", "ST", "转债", "B股", "融资融券", "沪股通", "深股通", "基金重仓", "预亏", "MSCI", "标准普尔")
        candidates = [
            x for x in boards
            if str(x.get("code", "")).startswith("BK")
            and x.get("name")
            and not any(word in str(x.get("name", "")) for word in excluded)
        ]
        return sorted(candidates, key=self._board_score, reverse=True)

    def _board_score(self, row: dict[str, Any]) -> float:
        return (
            num(row.get("pct_chg")) * 8
            + num(row.get("main_net_inflow_yi")) * 0.35
            + num(row.get("main_net_pct")) * 1.4
            + num(row.get("leader_pct_chg")) * 0.8
            + min(num(row.get("amount_yi")), 1000) / 120
        )

    def _match_board(self, boards: list[dict[str, Any]], code: str, name: str) -> dict[str, Any] | None:
        if code:
            hit = next((x for x in boards if str(x.get("code")) == code), None)
            if hit:
                return hit
        return next((x for x in boards if str(x.get("name")) == name or name in str(x.get("name")) or str(x.get("name")) in name), None)

    def _dedupe_constituents(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            code = str(row.get("code") or "")[:6]
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(row)
        return out

    async def _fund_flow_windows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        east = EastmoneyClient()
        xtick = XTickClient()
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
        semaphore = asyncio.Semaphore(2)

        async def one(row: dict[str, Any]) -> tuple[str, dict[str, float] | None]:
            code = str(row.get("code") or "")[:6]
            float_mv = num(row.get("float_mv_yi")) or num(row.get("total_mv_yi"))
            if not code or not float_mv:
                return code, None
            try:
                async with semaphore:
                    windows = await east.stock_fund_flow_windows(code, float_mv)
                    await asyncio.sleep(0.18)
                if windows:
                    return code, windows
            except Exception:
                pass
            if not xtick.enabled:
                return code, None
            try:
                async with semaphore:
                    data = await xtick.money_flow(code, start_date, end_date)
                valid = sorted(
                    [x for x in data if isinstance(x, dict) and x.get("time")],
                    key=lambda x: num(x.get("time")),
                )
                if not valid:
                    return code, None

                def net_yi(item: dict[str, Any]) -> float:
                    buy = num(item.get("buyMostAmount")) + num(item.get("buyBigAmount"))
                    sell = num(item.get("sellMostAmount")) + num(item.get("sellBigAmount"))
                    return round((buy - sell) / 100000000, 4)

                nets = [net_yi(x) for x in valid]
                windows = {
                    f"flow_{days}d": round(sum(nets[-days:]) / float_mv * 100, 2)
                    for days in (3, 5, 20)
                    if len(nets) >= days
                }
                return code, windows
            except Exception:
                return code, None

        results = await asyncio.gather(*(one(row) for row in rows), return_exceptions=True)
        out: dict[str, dict[str, float]] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            code, windows = result
            if code and windows:
                out[code] = windows
        return out

    async def _sina_finance_snapshots(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        client = SinaFinanceClient()
        semaphore = asyncio.Semaphore(4)

        async def one(row: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
            code = str(row.get("code") or "")[:6]
            try:
                async with semaphore:
                    return code, await client.financial_snapshot(code, 1)
            except Exception:
                return code, []

        pairs = await asyncio.gather(*(one(row) for row in rows), return_exceptions=True)
        out: dict[str, list[dict[str, Any]]] = {}
        for pair in pairs:
            if isinstance(pair, Exception):
                continue
            code, data = pair
            out[code] = data
        return out

    async def _cninfo_announcements(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        client = CninfoClient()
        semaphore = asyncio.Semaphore(4)

        async def one(row: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
            code = str(row.get("code") or "")[:6]
            try:
                async with semaphore:
                    return code, await client.announcements(stock_code=code, days=30, limit=2)
            except Exception:
                return code, []

        pairs = await asyncio.gather(*(one(row) for row in rows), return_exceptions=True)
        out: dict[str, list[dict[str, Any]]] = {}
        for pair in pairs:
            if isinstance(pair, Exception):
                continue
            code, data = pair
            out[code] = data
        return out

    def _eastmoney_one_day_proxy(self, row: dict[str, Any]) -> float | None:
        float_mv = num(row.get("float_mv_yi")) or num(row.get("total_mv_yi"))
        if not float_mv:
            return None
        return round(num(row.get("main_net_inflow_yi")) / float_mv * 100, 2)

    def _fundamental_summary(self, row: dict[str, Any], finance: list[dict[str, Any]], anns: list[dict[str, Any]]) -> str:
        pe = num(row.get("pe_dynamic"))
        pb = num(row.get("pb"))
        parts = [
            f"涨跌幅{num(row.get('pct_chg')):.2f}%",
            f"成交额{num(row.get('amount_yi')):.2f}亿",
            f"PE(动){pe:.2f}" if pe > 0 else "PE(动)亏损/缺失",
            f"PB{pb:.2f}" if pb > 0 else "PB数据缺失",
        ]
        if finance:
            latest = finance[0]
            report_date = str(latest.get("report_date") or "最新报告期")
            parts.append(
                f"{report_date}营收{num(latest.get('revenue_yi')):.2f}亿、归母净利{num(latest.get('net_profit_yi')):.2f}亿、经营现金流{num(latest.get('operating_cashflow_yi')):.2f}亿"
            )
        else:
            parts.append("三表快照数据缺失")
        if anns:
            parts.append(f"近30日公告：{str(anns[0].get('title') or '')[:38]}")
        else:
            parts.append("近30日未检索到重点公告")
        return "；".join(parts)

    def _industry_position(self, sector: str, row: dict[str, Any]) -> str:
        return (
            f"{sector}成分股；流通市值{num(row.get('float_mv_yi')):.2f}亿，"
            f"当日成交{num(row.get('amount_yi')):.2f}亿，换手率{num(row.get('turnover_rate')):.2f}%；"
            "具体产业链环节需继续用主营收入结构和公告复核"
        )

    def _concept_rating(self, row: dict[str, Any], flow_3d: float | None, flow_5d: float | None, flow_20d: float | None) -> str:
        pct = num(row.get("pct_chg"))
        if all(x is not None and x > 0 for x in (flow_3d, flow_5d, flow_20d)) and pct > 0:
            return "强"
        if (flow_3d is not None and flow_3d > 0) or pct > 0:
            return "中"
        return "弱"

    def _sector_stock_fallback(self, sector: str, exc: Exception) -> SectorStockSnapshot:
        raw = [
            ("000159.SZ","国际实业",4.81,None,None,None),("000821.SZ","ST京机",6.05,None,None,None),
            ("001269.SZ","欧晶科技",1.92,None,None,None),("002056.SZ","横店东磁",16.25,None,None,None),
            ("002079.SZ","苏州固锝",8.11,None,None,None),("002129.SZ","TCL中环",40.40,None,None,None),
            ("002150.SZ","正泰电源",3.59,None,None,None),("002459.SZ","晶澳科技",33.06,None,None,None),
            ("002506.SZ","协鑫集成",58.44,None,None,None),("002623.SZ","亚玛顿",1.93,None,None,None),
            ("002865.SZ","钧达股份",2.24,None,None,None),("003022.SZ","联泓新科",13.34,None,None,None),
            ("300051.SZ","琏升科技",3.67,None,None,None),("300080.SZ","易成新能",18.71,None,None,None),
            ("300093.SZ","*ST金刚",2.31,None,None,None),("300118.SZ","东方日升",9.27,None,None,None),
            ("300274.SZ","阳光电源",15.88,None,None,None),("300316.SZ","晶盛机电",12.32,None,None,None),
            ("300345.SZ","华民股份",4.80,None,None,None),("300393.SZ","中来股份",9.56,None,None,None),
        ]
        stocks = [StockFlow(c,n,mv,f3,f5,f20,("ST" in n)) for c,n,mv,f3,f5,f20 in raw]
        return SectorStockSnapshot(today(), sector, stocks, [
            MarketEvent("联网数据源取数失败，已回退到本地样例结构", "中性", "低置信度", "Fallback", f"{type(exc).__name__}: {str(exc)[:180]}"),
            MarketEvent("请优先检查东财/XTick/CNINFO网络连通性", "中性", "数据审计", "DataAudit", "当前页面仅用于模板预览，不应用于投资研究结论。"),
        ])

    async def _try_akshare_market(self) -> MarketSnapshot | None:
        try:
            import akshare as ak  # type: ignore
            df = ak.stock_zh_index_spot_em()
            base = await self.market_snapshot()
            # 这里保留保守适配，源站字段变动时不阻断主流程。
            for x in base.indices:
                row = df[df.astype(str).apply(lambda r: r.str.contains(x.name.replace("指数",""), regex=False).any(), axis=1)].head(1)
                if not row.empty:
                    vals = row.iloc[0].to_dict()
                    for k,v in vals.items():
                        if "涨跌幅" in str(k):
                            x.pct_chg = float(v)
            return base
        except Exception:
            return None


# =========================
# SearchHub
# =========================

class SearchHub:
    async def search(self, queries: list[str], days: int = 3, limit: int = 5) -> list[MarketEvent]:
        out: list[MarketEvent] = []
        for q in queries:
            if settings.tavily_api_key:
                out.extend(await self._tavily(q, days, limit))
            elif settings.serper_api_key:
                out.extend(await self._serper(q, days, limit))
            elif settings.serpapi_api_key:
                out.extend(await self._serpapi(q, days, limit))
            elif settings.brave_api_key:
                out.extend(await self._brave(q, days, limit))
            elif settings.searxng_url:
                out.extend(await self._searx(q, days, limit))
            if len(out) >= limit:
                break
        return self._dedupe(out)[:limit]

    async def _tavily(self, q: str, days: int, limit: int) -> list[MarketEvent]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post("https://api.tavily.com/search", json={"api_key": settings.tavily_api_key, "query": q, "topic": "news", "days": days, "max_results": limit})
                r.raise_for_status()
                return [self._from_result(x, "Tavily") for x in r.json().get("results", [])]
        except Exception:
            return []

    async def _serper(self, q: str, days: int, limit: int) -> list[MarketEvent]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post("https://google.serper.dev/news", headers={"X-API-KEY": settings.serper_api_key}, json={"q": q, "num": limit, "tbs": f"qdr:d{days}"})
                r.raise_for_status()
                return [self._from_result(x, "Serper") for x in r.json().get("news", [])]
        except Exception:
            return []

    async def _serpapi(self, q: str, days: int, limit: int) -> list[MarketEvent]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "engine": "google_news",
                        "q": q,
                        "api_key": settings.serpapi_api_key,
                        "hl": "zh-cn",
                        "gl": "cn",
                        "num": limit,
                    },
                )
                r.raise_for_status()
                return [self._from_result(x, "SerpAPI") for x in r.json().get("news_results", [])[:limit]]
        except Exception:
            return []

    async def _brave(self, q: str, days: int, limit: int) -> list[MarketEvent]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/news/search",
                    headers={"X-Subscription-Token": settings.brave_api_key},
                    params={"q": q, "count": min(limit, 20)},
                )
                r.raise_for_status()
                return [self._from_result(x, "Brave") for x in r.json().get("results", [])[:limit]]
        except Exception:
            return []

    async def _searx(self, q: str, days: int, limit: int) -> list[MarketEvent]:
        try:
            since = (datetime.now() - timedelta(days=days)).date().isoformat()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(settings.searxng_url.rstrip("/") + "/search", params={"q": f"{q} after:{since}", "format": "json"})
                r.raise_for_status()
                return [self._from_result(x, "SearxNG") for x in r.json().get("results", [])[:limit]]
        except Exception:
            return []

    def _from_result(self, x: dict, src: str) -> MarketEvent:
        title = str(x.get("title") or x.get("name") or "未命名事件")[:90]
        lower = title.lower()
        impact = "利多" if any(k in lower for k in ["利好","上涨","增长","降息","approval","cut"]) else "利空" if any(k in lower for k in ["风险","制裁","下跌","关税","亏损","跌"]) else "中性"
        return MarketEvent(title, impact, "正在定价", src, "需盘面验证", x.get("url") or x.get("link"), x.get("published_date") or x.get("date"))

    def _dedupe(self, items: list[MarketEvent]) -> list[MarketEvent]:
        seen, out = set(), []
        for e in items:
            key = e.title[:28]
            if key not in seen:
                seen.add(key); out.append(e)
        return out


# =========================
# AgentTeam
# =========================

class AgentTeam:
    def __init__(self, llm: LLMConfig | None = None):
        self.llm = llm or LLMConfig.from_settings()
        self.last_llm_mode = "not_configured"
        self.last_llm_error = ""

    async def run(self, context: dict) -> list[AgentFinding]:
        rule_findings = self._rule_findings(context)
        if not self.llm.enabled:
            self.last_llm_mode = "rule"
            self.last_llm_error = ""
            return rule_findings
        llm_findings = await self._run_llm(context, rule_findings)
        if llm_findings:
            self.last_llm_mode = "llm"
            self.last_llm_error = ""
            return llm_findings
        self.last_llm_mode = "rule_fallback"
        return rule_findings

    def _rule_findings(self, context: dict) -> list[AgentFinding]:
        return [
            self.macro(context),
            self.capital(context),
            self.quant(context),
            self.industry(context),
            self.risk(context),
        ]

    async def _run_llm(self, context: dict, rule_findings: list[AgentFinding]) -> list[AgentFinding]:
        system_prompt = (
            "You are an A-share multi-agent investment research coordinator. "
            "Use only the provided context and rule findings. "
            "Return strict JSON: an array of 5 objects, each with role, verdict, score, evidence, risks. "
            "score must be 0-100. evidence and risks must be short string arrays. "
            "Do not provide investment promises."
        )
        user_payload = {"context": context, "rule_findings": [asdict(x) for x in rule_findings]}
        try:
            headers = {"Content-Type": "application/json"}
            if self.llm.api_key:
                headers["Authorization"] = f"Bearer {self.llm.api_key}"
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    self.llm.chat_completions_url,
                    headers=headers,
                    json={
                        "model": self.llm.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)[:24000]},
                        ],
                        "temperature": 0.2,
                    },
                )
                r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return self._parse_llm_findings(content)
        except Exception as exc:
            self.last_llm_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            return []

    def _parse_llm_findings(self, content: str) -> list[AgentFinding]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\[[\s\S]*\]", text)
        data = json.loads(match.group(0) if match else text)
        out: list[AgentFinding] = []
        for item in data[:8]:
            out.append(
                AgentFinding(
                    role=str(item.get("role", "LLM Analyst"))[:40],
                    verdict=str(item.get("verdict", ""))[:240],
                    score=clamp(float(item.get("score", 50))),
                    evidence=[str(x)[:120] for x in (item.get("evidence") or [])[:5]],
                    risks=[str(x)[:120] for x in (item.get("risks") or [])[:5]],
                )
            )
        return out

    def macro(self, ctx: dict) -> AgentFinding:
        events = ctx.get("events") or ctx.get("market", {}).get("events") or ctx.get("quant", {}).get("events") or []
        fav = sum(1 for e in events if e.get("impact") == "利多")
        neg = sum(1 for e in events if e.get("impact") == "利空")
        return AgentFinding("宏观策略", "政策预期托底，但需要资金确认。", clamp(50 + 10*(fav-neg)), [f"利多{fav}条/利空{neg}条"], ["政策落地慢于预期"])

    def capital(self, ctx: dict) -> AgentFinding:
        sector = ctx.get("sector", {})
        stocks = sector.get("stocks") or []
        if stocks:
            valid = [x for x in stocks if x.get("flow_3d") is not None]
            pos = len([x for x in valid if float(x.get("flow_3d") or 0) > 0])
            avg = sum(float(x.get("flow_3d") or 0) for x in valid) / max(len(valid), 1)
            verdict = f"{pos}/{len(stocks)}只个股3D资金为正，板块资金{'偏强' if avg > 0 else '分歧'}。"
            return AgentFinding("资金流", verdict, clamp(50 + avg * 4 + pos), [f"3D均值{avg:.2f}%", f"样本{len(stocks)}只"], ["资金窗口不完整", "单日代理口径需复核"])
        idx = ctx.get("market", {}).get("indices", [])
        flow = sum(float(x.get("main_net_inflow", 0)) for x in idx)
        return AgentFinding("资金流", "指数涨但主力净流出，诱多背离需防。", clamp(50 + flow/20), [f"主力合计{flow:.2f}亿"], ["放量不延续"])

    def quant(self, ctx: dict) -> AgentFinding:
        sector = ctx.get("sector", {})
        stocks = sector.get("stocks") or []
        if stocks:
            valid = [x for x in stocks if x.get("flow_3d") is not None and x.get("flow_5d") is not None and x.get("flow_20d") is not None]
            all_pos = len([x for x in valid if all(float(x.get(k) or 0) > 0 for k in ("flow_3d", "flow_5d", "flow_20d"))])
            score = clamp(45 + all_pos * 3 + len(valid) / max(len(stocks), 1) * 20)
            return AgentFinding("技术量化", f"{all_pos}只个股三周期全正，强弱分化需要用趋势继续确认。", score, [f"完整窗口{len(valid)}只"], ["强势股高波动", "资金指标滞后"])
        q = ctx.get("quant", {})
        c = float(q.get("composite", 50))
        return AgentFinding("技术量化", "综合因子冰点，反弹需右侧确认。", c, [f"综合因子{c}"], ["冰点钝化"])

    def industry(self, ctx: dict) -> AgentFinding:
        sector = ctx.get("sector", {})
        if sector:
            theme = sector.get("sector", "目标板块")
            stocks = sector.get("stocks") or []
            return AgentFinding("行业轮动", f"{theme}是当前扫描出的重点主线，需验证产业逻辑和资金持续性。", 65, [f"成分股{len(stocks)}只"], ["题材强度可能快于基本面兑现"])
        leaders = ctx.get("market", {}).get("leaders", [])
        theme = leaders[0]["name"] if leaders else "核心主线"
        return AgentFinding("行业轮动", f"领涨集中于{theme}，主线比杂乱轮动更健康。", 65, ["领涨板块相似度较高"], ["单日高潮后分歧"])

    def risk(self, ctx: dict) -> AgentFinding:
        sector = ctx.get("sector", {})
        stocks = sector.get("stocks") or []
        if stocks:
            st_count = len([x for x in stocks if x.get("is_st")])
            missing = len([x for x in stocks if None in (x.get("flow_3d"), x.get("flow_5d"), x.get("flow_20d"))])
            return AgentFinding("风险控制", "重点防范强势主线退潮、公告风险和资金窗口缺失导致的排序偏差。", clamp(55 - st_count * 3 - missing), [f"ST/{st_count}只", f"资金缺口{missing}只"], ["高位补跌", "减持解禁", "业绩不及预期"])
        return AgentFinding("风险控制", "防范指数虚涨、资金外流、题材拥挤。", 35, ["风险前置"], ["高位题材退潮", "外盘扰动", "个股普跌"])


# =========================
# Analytics
# =========================

def market_summary(m: MarketSnapshot) -> dict:
    up = sum(x.up_count for x in m.indices); down = sum(x.down_count for x in m.indices)
    up_ratio = round(up / max(up+down, 1) * 100, 2)
    total_flow = round(sum(x.main_net_inflow for x in m.indices), 2)
    sh = next((x for x in m.indices if x.name == "上证指数"), m.indices[0])
    kc = next((x for x in m.indices if x.name == "科创50"), m.indices[-1])
    diff = round(kc.pct_chg - sh.pct_chg, 2)
    label = "不及预期" if total_flow < -300 and up_ratio < 50 else "符合预期" if total_flow < 0 else "超预期"
    conflict = "指数上行但资金大幅流出，反弹质量偏弱。" if total_flow < 0 else "资金与题材形成正反馈。"
    return {"label": label, "up_ratio": up_ratio, "flow": total_flow, "diff": diff, "leader_count": len([x for x in m.leaders if x.pct_chg > 3]), "conflict": conflict}


def quant_summary(q: QuantSnapshot) -> dict:
    c = q.composite
    if c < 20: return {"zone":"冰点","color":"#58a6ff","state":"极低位，弱修复但未右侧确认。"}
    if c < 40: return {"zone":"低迷","color":"#3fb950","state":"低迷反弹，资金确认前不追高。"}
    if c < 60: return {"zone":"中性","color":"#8b949e","state":"震荡等待方向。"}
    if c < 80: return {"zone":"活跃","color":"#d2991d","state":"趋势活跃，顺势但防拥挤。"}
    return {"zone":"沸点","color":"#f85149","state":"情绪过热，止盈优先。"}


def classify_stock(s: StockFlow) -> tuple[str, int, str]:
    if s.is_st:
        return "风险警示型", 25, "回避"
    if s.flow_3d is not None and (s.flow_5d is None or s.flow_20d is None):
        f3 = s.flow_3d
        score = int(clamp(45 + f3 * 10, 20, 78))
        if f3 > 2:
            mode = "1D代理强流入型"
        elif f3 > 0:
            mode = "1D代理温和流入型"
        elif f3 < -1:
            mode = "1D代理流出型"
        else:
            mode = "1D代理均衡型"
        return mode, score, "谨慎" if score >= 55 else "观望"
    if None in (s.flow_3d, s.flow_5d, s.flow_20d):
        return "数据缺失待验证", 45, "观望"
    f3, f5, f20 = s.flow_3d, s.flow_5d, s.flow_20d
    score = 50
    if f3 > 0 and f5 > 0 and f20 > 0: score += 30
    if f20 > 2: score += 15
    if f3 > f5 > f20: score += 10
    if f3 > 3 and f5 > 3 and f20 > 2: mode = "主力强攻型"
    elif f3 > 1 and f5 > 2 and f20 > 2: mode = "主力建仓型"
    elif f3 > 3 and f5 > 1 and f20 < 0: mode = "短线抢筹型"
    elif f3 < 1 and f5 < 1 and f20 > 2: mode = "长线吸筹型"
    elif f3 > 0 and f5 > 0 and f20 < 0: mode = "趋势转多型"
    elif f3 < 0 and f5 < 0 and f20 < 0: mode = "资金撤退型"; score -= 25
    else: mode = "均衡震荡型"
    score = int(clamp(score))
    return mode, score, "看好" if score >= 70 else "谨慎" if score >= 50 else "观望"


# =========================
# HTML Renderer
# =========================

CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"

def head(title: str) -> str:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><script src="{CDN}"></script><style>
:root{{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--red:#f85149;--green:#3fb950;--orange:#d2991d;--blue:#58a6ff;--purple:#a371f7}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:PingFang SC,Microsoft YaHei,Arial,sans-serif}}.wrap{{max-width:1380px;margin:auto;padding:20px}}.grid{{display:grid;gap:14px}}.g4{{grid-template-columns:repeat(4,1fr)}}.g3{{grid-template-columns:repeat(3,1fr)}}.g2{{grid-template-columns:repeat(2,1fr)}}.card,.banner{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px}}.banner{{background:radial-gradient(circle at top left,rgba(88,166,255,.18),transparent 35%),var(--card);border-radius:20px}}.section{{margin-top:16px}}h1,h2{{margin:0 0 10px}}h1{{font-size:24px}}h2{{font-size:17px}}.num{{font-size:28px;font-weight:900}}.sub,.mini{{color:var(--muted);font-size:13px;line-height:1.55}}.tag{{display:inline-flex;padding:4px 10px;border-radius:999px;color:#fff;font-size:12px;font-weight:800}}.red{{background:var(--red)}}.green{{background:var(--green)}}.orange{{background:var(--orange)}}.blue{{background:var(--blue)}}.gray{{background:#6e7681}}.purple{{background:var(--purple)}}canvas{{width:100%!important;max-height:360px}}.chart{{height:360px}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}}th{{color:var(--muted)}}.risk{{background:rgba(248,81,73,.05);border-color:rgba(248,81,73,.28)}}.line{{height:5px;border-radius:8px;margin-top:12px}}.timeline{{position:relative;padding-left:20px}}.timeline:before{{content:"";position:absolute;left:6px;top:4px;bottom:4px;width:2px;background:var(--border)}}.node{{position:relative;margin:12px 0;padding:12px;border:1px solid var(--border);border-radius:12px;background:rgba(255,255,255,.03)}}.node:before{{content:"";position:absolute;left:-19px;top:16px;width:10px;height:10px;border-radius:50%;background:var(--blue)}}.stock{{border:1px solid var(--border);border-radius:16px;padding:14px;margin-bottom:12px;background:rgba(255,255,255,.025)}}.stock.best{{border-color:var(--red);box-shadow:0 0 18px rgba(248,81,73,.15)}}.pill{{border:1px solid var(--border);border-radius:10px;padding:4px 8px;color:var(--muted);font-size:12px}}.kv{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}}.footer{{color:var(--muted);text-align:center;font-size:12px;margin:24px 0 6px}}@media(max-width:900px){{.g4,.g3,.g2{{grid-template-columns:1fr}}.wrap{{padding:12px}}}}
</style></head><body><div class="wrap">"""

def foot(script: str = "") -> str:
    return script + f"<div class='footer'>基于 AI 分析 + 联网搜索，仅供参考，不构成投资建议。投资有风险，入市需谨慎。生成时间：{now_str()}</div></div></body></html>"


def render_market(m: MarketSnapshot, findings: list[AgentFinding]) -> str:
    s = market_summary(m)
    axis = ["涨跌幅","上涨占比","主力资金","波动率","相对强弱"]
    radar = []
    for x in m.indices:
        radar.append({"label":x.name,"data":[clamp(x.pct_chg*15+50),x.up_ratio,clamp(50+x.main_net_inflow/5),x.volatility,x.relative_strength]})
    leaders = [asdict(x) for x in m.leaders]; laggards = [asdict(x) for x in m.laggards]
    events = "".join(f"<tr><td><b>{escape(e.title)}</b><div class='sub'>{escape(e.relation)}</div></td><td>{tag(e.impact)}</td><td>{escape(e.pricing)}</td><td>{escape(e.source)}</td></tr>" for e in m.events[:5])
    html = head("A股行情多维复盘")
    html += f"""
<div class="banner section"><h1>今日A股多维复盘 {tag(s['label'])}</h1><div class="sub">{escape(s['conflict'])}</div><div class="grid g4 section">
<div class="card"><div class="num">{s['up_ratio']}%</div><div class="mini">赚钱效应</div></div><div class="card"><div class="num">{s['flow']}亿</div><div class="mini">主力净流向</div></div><div class="card"><div class="num">{s['leader_count']}</div><div class="mini">领涨板块数</div></div><div class="card"><div class="num">{m.turnover_change_pct}%</div><div class="mini">成交额环比</div></div></div></div>
<div class="grid g2 section"><div class="card"><h2>四指数雷达对比</h2><div class="chart"><canvas id="radar"></canvas></div><div class="sub">科创50 vs 主板：结构性分化程度 {s['diff']}pct</div></div><div class="card"><h2>四维预期差</h2><div class="grid g2"><div class="card">{tag('符合预期')}<div class="num">{s['diff']}pct</div><div class="mini">指数情绪</div></div><div class="card">{tag('不及预期' if s['flow']<0 else '超预期')}<div class="num">{s['flow']}亿</div><div class="mini">资金流向</div></div><div class="card">{tag('超预期')}<div class="num">{s['leader_count']}</div><div class="mini">板块轮动</div></div><div class="card">{tag('符合预期')}<div class="num">{len(m.events)}</div><div class="mini">事件政策</div></div></div></div></div>
<div class="grid g2 section"><div class="card"><h2>板块资金热力双柱</h2><div class="chart"><canvas id="sectorBar"></canvas></div></div><div class="card"><h2>主力资金结构</h2><div class="chart"><canvas id="flowBar"></canvas></div></div></div>
<div class="card section"><h2>联网事件关联面板</h2><table><thead><tr><th>事件标题</th><th>影响</th><th>定价</th><th>来源</th></tr></thead><tbody>{events}</tbody></table></div>
<div class="card risk section"><h2>风险信号灯</h2><div class="grid g3"><div class="card"><b>R1 诱多背离</b><div class="sub">指数涨但主力资金净流出。</div><div class="line" style="background:#f85149"></div></div><div class="card"><b>R2 结构失衡</b><div class="sub">科创强掩盖多数个股弱。</div><div class="line" style="background:#d2991d"></div></div><div class="card"><b>R3 题材拥挤</b><div class="sub">医药短线涨幅过快。</div><div class="line" style="background:#d2991d"></div></div></div></div>
<div class="card section"><h2>未来催化剂时间轴</h2><div class="timeline"><div class="node"><b>未来3日 · 政策表态</b> {tag('中性')}<div class="sub">观察成交额能否放大。</div></div><div class="node"><b>未来1周 · 业绩窗口</b> {tag('利多')}<div class="sub">医药科技链验证兑现。</div></div><div class="node"><b>未来2周 · 外围利率汇率</b> {tag('中性')}<div class="sub">影响成长股估值弹性。</div></div></div></div>
"""
    script = f"""<script>
const grid='rgba(139,148,158,.25)', text='#8b949e', red='#f85149', green='#3fb950', blue='#58a6ff', orange='#d2991d';
Chart.defaults.color=text; Chart.defaults.borderColor=grid;
const radar={j(radar)}, axis={j(axis)}, leaders={j(leaders)}, laggards={j(laggards)};
new Chart(document.getElementById('radar'),{{type:'radar',data:{{labels:axis,datasets:radar.map((d,i)=>({{...d,borderColor:[red,blue,orange,green][i],backgroundColor:['rgba(248,81,73,.10)','rgba(88,166,255,.10)','rgba(210,153,29,.10)','rgba(63,185,80,.10)'][i]}}))}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom'}}}},scales:{{r:{{min:0,max:100}}}}}}}});
new Chart(document.getElementById('sectorBar'),{{type:'bar',data:{{labels:[...leaders.map(x=>x.name),...laggards.map(x=>x.name)],datasets:[{{label:'涨跌幅%',data:[...leaders.map(x=>x.pct_chg),...laggards.map(x=>x.pct_chg)],backgroundColor:[...leaders.map(x=>'rgba(248,81,73,.78)'),...laggards.map(x=>'rgba(63,185,80,.78)')]}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});
const flows=[...leaders,...laggards];new Chart(document.getElementById('flowBar'),{{type:'bar',data:{{labels:flows.map(x=>x.name),datasets:[{{label:'主力资金(亿)',data:flows.map(x=>x.main_net_inflow),backgroundColor:flows.map(x=>x.main_net_inflow>=0?'rgba(248,81,73,.78)':'rgba(63,185,80,.78)')}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});
</script>"""
    return html + foot(script)


def render_quant(q: QuantSnapshot, findings: list[AgentFinding]) -> str:
    s = quant_summary(q)
    sigs = [
        ("背离","资金-情绪背离","聪明钱逆势布局","强"),
        ("背离","动量-资金背离","底部蓄力待确认","中"),
        ("中性","短压中撑","5日线压制20日线托底","中"),
    ]
    signal_cards = "".join(f"<div class='card' style='background:{'rgba(248,81,73,.1)' if a=='背离' else 'rgba(88,166,255,.1)' if a=='共振' else 'rgba(255,255,255,.03)'}'>{tag(a)}<h2>{escape(b)}</h2><div class='sub'>{escape(c)}</div><div class='line' style='background:{'#f85149' if d=='强' else '#d2991d'}'></div></div>" for a,b,c,d in sigs)
    events = "".join(f"<tr><td><b>{escape(e.title)}</b></td><td>{escape(e.relation)}</td><td>{tag(e.impact)}</td></tr>" for e in q.events[:5])
    html = head("A股大盘量化因子分析")
    html += f"""
<div class="banner section" style="background:radial-gradient(circle at top left,{s['color']}44,transparent 32%),#161b22"><h1>综合因子 <span class="num">{q.composite}</span> {tag(s['zone'])}</h1><div class="sub">{escape(s['state'])}</div><div class="grid g4 section"><div class="card"><div class="num">{q.index_level}</div><div class="mini">指数点位</div></div><div class="card"><div class="num">{q.dist_ma5}%</div><div class="mini">距5日线</div></div><div class="card"><div class="num">{q.dist_ma20}%</div><div class="mini">距20日线</div></div><div class="card"><div class="num">{q.trend}</div><div class="mini">综合趋势</div></div></div></div>
<div class="grid g2 section"><div class="card"><h2>四因子雷达图</h2><div class="chart"><canvas id="factor"></canvas></div><div class="sub">核心发现：资金相对独高、情绪与动量冰点 = 背离信号。</div></div><div class="card"><h2>均线位置K线示意</h2><svg viewBox="0 0 800 220" width="100%" height="220"><line x1="80" y1="110" x2="720" y2="110" stroke="#30363d" stroke-width="12" stroke-linecap="round"/><line x1="480" y1="60" x2="480" y2="170" stroke="#d2991d" stroke-dasharray="7 7"/><line x1="360" y1="60" x2="360" y2="170" stroke="#58a6ff" stroke-dasharray="7 7"/><line x1="430" y1="45" x2="430" y2="185" stroke="#fff" stroke-width="4"/><text x="455" y="55" fill="#d2991d">5日线 {q.ma5}</text><text x="300" y="185" fill="#58a6ff">20日线 {q.ma20}</text><text x="445" y="110" fill="#fff">当前 {q.index_level}</text></svg><div class="sub">5日线下、20日线上：短压中撑。</div></div></div>
<div class="card section"><h2>因子背离/共振信号</h2><div class="grid g3">{signal_cards}</div></div>
<div class="card section"><h2>综合因子温度计</h2><div style="height:34px;border-radius:99px;background:linear-gradient(90deg,#58a6ff 0 20%,#3fb950 20% 40%,#8b949e 40% 60%,#d2991d 60% 80%,#f85149 80%);position:relative"><div style="position:absolute;left:{q.composite}%;top:-10px;width:3px;height:54px;background:#fff"></div></div><div class="sub">冰点20｜沸点80｜近60日 {q.percentile_60d}% 分位</div></div>
<div class="card section"><h2>联网事件关联面板</h2><table><thead><tr><th>事件标题</th><th>因子关联</th><th>影响方向</th></tr></thead><tbody>{events}</tbody></table></div>
<div class="grid g3 section"><div class="card">{tag('利多')}<h2>乐观情景</h2><div class="sub">重回5日线且资金因子>50，目标4100-4150。</div></div><div class="card">{tag('中性')}<h2>基准情景</h2><div class="sub">综合因子20下方，围绕20日线震荡。</div></div><div class="card">{tag('利空')}<h2>悲观情景</h2><div class="sub">跌破20日线，支撑看4020附近。</div></div></div>
"""
    script = f"""<script>const text='#8b949e',blue='#58a6ff';Chart.defaults.color=text;new Chart(document.getElementById('factor'),{{type:'radar',data:{{labels:['动量','情绪','资金','综合'],datasets:[{{label:'当前',data:{j([q.momentum,q.emotion,q.capital,q.composite])},borderColor:blue,backgroundColor:'rgba(88,166,255,.2)'}},{{label:'50中轴',data:[50,50,50,50],borderColor:'rgba(139,148,158,.55)',borderDash:[6,6],pointRadius:0,fill:false}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom'}}}},scales:{{r:{{min:0,max:100}}}}}}}});</script>"""
    return html + foot(script)


def render_sector(ss: SectorStockSnapshot, findings: list[AgentFinding]) -> str:
    def fmt_pct(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}%"

    rows = []
    for st in ss.stocks:
        mode, score, decision = classify_stock(st)
        rows.append({"stock": st, "mode": mode, "score": score, "decision": decision})
    rows.sort(key=lambda x: x["score"], reverse=True)
    leader = rows[0]["stock"].name if rows else "无"
    positive = len([r for r in rows if (r["stock"].flow_3d or 0) > 0])
    allpos = len([r for r in rows if all(v is not None and v > 0 for v in [r["stock"].flow_3d, r["stock"].flow_5d, r["stock"].flow_20d])])
    stage = "吸筹初期" if positive > 0 else "分歧期/数据待验证"
    missing_windows = len([r for r in rows if None in (r["stock"].flow_3d, r["stock"].flow_5d, r["stock"].flow_20d)])
    if missing_windows == len(rows) and rows:
        funding_banner = "本次东财push2his与XTick历史资金窗口均未返回完整数据，已使用东财最新主力净流/流通市值作为1D代理，排序置信度降级。"
        funding_audit = "东财最新主力净流/流通市值1D代理；东财push2his与XTick 3D/5D/20D历史窗口本次不可用。"
    elif missing_windows:
        funding_banner = "部分个股已使用东财push2his或XTick历史资金窗口，缺失个股使用东财主力净流/流通市值1D代理，并在审计中降级。"
        funding_audit = "东财push2his近20个交易日主力净流入/流通市值；东财失败时尝试XTick；仍缺失时东财最新主力净流/流通市值作1D代理。"
    else:
        funding_banner = "已使用东财push2his或XTick近20个交易日资金窗口计算3D/5D/20D，东财实时行情用于交叉校验。"
        funding_audit = "东财push2his近20个交易日主力净流入/流通市值，必要时用XTick历史资金流交叉校验。"
    event_rows = "".join(
        f"<tr><td><b>{escape(e.title)}</b><div class='sub'>{escape(e.relation)}</div></td>"
        f"<td>{tag(e.impact)}</td><td>{escape(e.pricing)}</td><td>{escape(e.source)}</td>"
        f"<td>{escape(e.published_at or '')}</td><td>{f'<a href={escape(e.url)!r} target=_blank>打开</a>' if e.url else '-'}</td></tr>"
        for e in ss.events[:16]
    ) or "<tr><td colspan='6'>近30日事件与公告数据缺失</td></tr>"
    finding_cards = "".join(
        f"<div class='card'><b>{escape(f.role)}</b><div class='num'>{round(f.score, 1)}</div><div class='sub'>{escape(f.verdict)}</div></div>"
        for f in findings[:5]
    )
    cards, table = "", ""
    for i, r in enumerate(rows, 1):
        s, mode, score, decision = r["stock"], r["mode"], r["score"], r["decision"]
        sttag = " " + tag("*ST/ST风险") if s.is_st else ""
        stock_missing = None in (s.flow_3d, s.flow_5d, s.flow_20d)
        flow_note = "三周期资金显示" + escape(mode) if not stock_missing else "资金窗口不完整，使用可得窗口/代理口径降级排序。"
        cards += f"""<div class="stock {'best' if score>=70 and not s.is_st else ''}"><h2>排名{i} · {escape(s.name)}（{escape(s.code)}）· 流通市值{s.float_mv}亿 {sttag}</h2><div class="kv"><span class="pill">资金模式：{escape(mode)}</span><span class="pill">资金质量分：{score}/100</span><span class="pill">3D {fmt_pct(s.flow_3d)}</span><span class="pill">5D {fmt_pct(s.flow_5d)}</span><span class="pill">20D {fmt_pct(s.flow_20d)}</span></div><table><tbody><tr><td>资金判断</td><td>{flow_note}</td></tr><tr><td>基本面亮点</td><td>{escape(s.fundamentals)}</td></tr><tr><td>产业链定位</td><td>{escape(s.industry_position)}</td></tr><tr><td>交叉概念关联</td><td>{escape(ss.sector)} + 当前强势主线/政策产业催化，评级：{escape(s.concept_rating)}</td></tr><tr><td>短期判断</td><td>{escape(decision)}：资金置信度{'不足' if stock_missing else '可跟踪'}，需结合分时成交和公告继续确认。</td></tr><tr><td>半年预期</td><td>重点跟踪财报披露、订单/价格/政策窗口和行业景气验证；风险在于高位拥挤、减持解禁、业绩兑现不及预期。</td></tr>{'<tr><td>特有风险</td><td>风险警示/退市风险，推荐池排除。</td></tr>' if s.is_st else ''}</tbody></table></div>"""
        table += f"<tr><td>{i}</td><td>{escape(s.code)}</td><td>{escape(s.name)}</td><td>{escape(mode)}</td><td>{fmt_pct(s.flow_3d)}</td><td>{fmt_pct(s.flow_5d)}</td><td>{fmt_pct(s.flow_20d)}</td><td>{score}</td><td>{escape(s.concept_rating)}</td><td>{escape(decision)}</td></tr>"
    recs = [r for r in rows if not r["stock"].is_st][:5]
    rec_html = "".join(f"<div class='stock {'best' if i==1 else ''}'><h2>推荐 #{i}：{escape(r['stock'].name)}（{escape(r['stock'].code)}）</h2><div class='kv'>{tag('首选' if i==1 else '次选' if i<=3 else '观察')}<span class='pill'>资金分 {r['score']}</span><span class='pill'>{escape(r['mode'])}</span><span class='pill'>概念评级 {escape(r['stock'].concept_rating)}</span></div><div class='sub'>资金强度、流动性和公告/财务可核验性优先；仅作为研究观察池，不构成买卖建议。</div><table><tbody><tr><td>投资逻辑</td><td>{escape(r['stock'].fundamentals)}</td></tr><tr><td>半年预期</td><td>看行业景气确认和资金持续性；催化为财报/订单/政策，最大风险为高位放量滞涨或公告风险。</td></tr><tr><td>止损/止盈参考</td><td>止损看20日线或前低；止盈看前高、异常放量与资金背离。</td></tr><tr><td>差异化</td><td>相对风险警示股和资金撤退股，具备更好的可跟踪性。</td></tr></tbody></table></div>" for i, r in enumerate(recs,1))
    labels = [r["stock"].name for r in rows]; values = [r["stock"].flow_3d or 0 for r in rows]
    html = head(f"{ss.sector}板块个股分析")
    html += f"""
<div class="banner section"><h1>{escape(ss.sector)}板块资金全景</h1><div class="grid g4 section"><div class="card"><div class="num">{positive}/{len(rows)}</div><div class="mini">资金净流入家数</div></div><div class="card"><div class="num">{escape(leader)}</div><div class="mini">板块资金龙头</div></div><div class="card"><div class="num">{allpos}</div><div class="mini">三周期全正</div></div><div class="card"><div class="num">{escape(stage)}</div><div class="mini">阶段标签</div></div></div><div class="sub section">{escape(funding_banner)}</div></div>
<div class="card section"><h2>个股资金排名柱状图</h2><div class="chart"><canvas id="stockFlow"></canvas></div></div>
<div class="card section"><h2>联网事件、公告与口径</h2><table><thead><tr><th>事件/审计项</th><th>影响</th><th>定价/类型</th><th>来源</th><th>时间</th><th>链接</th></tr></thead><tbody>{event_rows}</tbody></table></div>
<div class="grid g3 section">{finding_cards}</div>
<div class="section"><h2>所有个股逐一深度分析</h2>{cards}</div>
<div class="card section"><h2>资金模式分类汇总表</h2><table><thead><tr><th>排名</th><th>代码</th><th>名称</th><th>模式</th><th>3日</th><th>5日</th><th>20日</th><th>资金分</th><th>概念</th><th>判断</th></tr></thead><tbody>{table}</tbody></table></div>
<div class="card section"><h2>板块半年预期路线图</h2><div class="timeline"><div class="node"><b>当月 · 资金持续性验证</b> {tag('中性')}<div class="sub">观察3D/5D窗口能否继续为正，以及龙头是否放量不滞涨。</div></div><div class="node"><b>下月 · 中报/业绩预告窗口</b> {tag('利多')}<div class="sub">优先筛选资金流入且业绩兑现度高的个股。</div></div><div class="node"><b>3个月内 · 行业数据和政策节点</b> {tag('中性')}<div class="sub">跟踪订单、价格、产能、监管和补贴政策是否验证主线逻辑。</div></div><div class="node"><b>6个月内 · 估值再平衡</b> {tag('中性')}<div class="sub">若资金退潮或基本面不兑现，强势板块可能转入高波动分化。</div></div></div></div>
<div class="section"><h2>精选推荐 3-5 只</h2>{rec_html}</div>
<div class="card section"><h2>数据来源与口径说明</h2><table><tbody><tr><td>交易日/生成日</td><td>{escape(ss.trade_date)} / {escape(now_str())}</td></tr><tr><td>板块与成分股</td><td>东方财富行业/概念排名、板块成分股接口；全市场模式下自动选择综合强度最高主线。</td></tr><tr><td>资金口径</td><td>{escape(funding_audit)}</td></tr><tr><td>财务与公告</td><td>新浪财务三表快照用于重点股，巨潮资讯近30日公告用于事件核验。</td></tr><tr><td>缺失字段</td><td>{missing_windows}只个股资金窗口不完整；主营收入结构、估值历史分位、券商一致预期仍需专业数据源补齐。</td></tr><tr><td>置信度</td><td>{'中高' if missing_windows < max(1, len(rows)//4) else '中'}：行情与资金可得，基本面业务纯度仍需公告/年报继续验证。</td></tr></tbody></table></div>
<div class="card risk section"><h2>风险汇总</h2><div class="grid g4"><div class="card"><b>主线退潮</b><div class="sub">单日强势板块若次日资金不延续，容易高波动回撤。</div></div><div class="card"><b>估值拥挤</b><div class="sub">高PE、高PB个股需要业绩兑现支撑。</div></div><div class="card"><b>公告风险</b><div class="sub">减持、解禁、监管问询和业绩变脸会改变排序。</div></div><div class="card"><b>口径差异</b><div class="sub">不同数据源资金定义不同，代理指标仅用于横向比较。</div></div></div></div>
"""
    script = f"""<script>const text='#8b949e';Chart.defaults.color=text;const labels={j(labels)},data={j(values)};new Chart(document.getElementById('stockFlow'),{{type:'bar',data:{{labels,datasets:[{{label:'3D资金强度%',data,backgroundColor:data.map(x=>x>=0?'rgba(248,81,73,.78)':'rgba(63,185,80,.78)')}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});</script>"""
    return html + foot(script)


def render_agents(findings: list[AgentFinding]) -> str:
    score = round(sum(f.score for f in findings)/len(findings), 1)
    card_parts = []
    for finding in findings:
        evidence = "".join(
            f"<span class='pill'>{escape(item)}</span>"
            for item in finding.evidence[:3]
        )
        card_parts.append(
            f"<div class='card'><h2>{escape(finding.role)}</h2>"
            f"<div class='num'>{finding.score}</div>"
            f"<div class='sub'>{escape(finding.verdict)}</div>"
            f"<div class='kv'>{evidence}</div></div>"
        )
    cards = "".join(card_parts)
    risks = "".join(f"<tr><td>{escape(f.role)}</td><td>{escape('；'.join(f.risks) or '暂无')}</td></tr>" for f in findings)
    return head("A股多智能体投研报告") + f"<div class='banner section'><h1>多智能体投研结论</h1><div class='num'>{score}</div><div class='sub'>综合评分：>60偏机会，40-60中性，<40偏风险。</div></div><div class='grid g3 section'>{cards}</div><div class='card section'><h2>风险清单</h2><table><thead><tr><th>角色</th><th>风险</th></tr></thead><tbody>{risks}</tbody></table></div>" + foot()


# =========================
# Pipeline
# =========================

class Pipeline:
    def __init__(self, llm: LLMConfig | None = None):
        self.llm = llm or LLMConfig.from_settings()
        self.data = DataHub()
        self.search = SearchHub()
        self.agents = AgentTeam(self.llm)
        settings.report_path.mkdir(parents=True, exist_ok=True)

    def _llm_status(self) -> dict:
        info = self.llm.public_dict()
        info["mode"] = self.agents.last_llm_mode
        info["error"] = self.agents.last_llm_error
        return info

    async def generate(self, report_type: ReportType, sector: str = "光伏设备") -> dict:
        if report_type == "market_replay":
            m = await self.data.market_snapshot()
            ev = await self.search.search(["A股 今日 宏观政策 央行 财政部 发改委 国常会", "A股 今日 产业新闻 领涨 领跌 板块", "隔夜 美股 纳指 标普 A50 人民币汇率"], 3, 5)
            if ev: m.events = ev
            f = await self.agents.run({"market": json.loads(j(m)), "events": [asdict(e) for e in m.events]})
            html, title = render_market(m, f), "A股行情多维复盘"
        elif report_type == "quant_factor":
            q = await self.data.quant_snapshot()
            ev = await self.search.search(["A股 央行 公开市场操作 证监会 两融 ETF资金流向", "VIX 美股 美元人民币 A股 情绪"], 3, 5)
            if ev: q.events = ev
            f = await self.agents.run({"quant": json.loads(j(q)), "events": [asdict(e) for e in q.events]})
            html, title = render_quant(q, f), "A股大盘量化因子分析"
        elif report_type == "sector_stock":
            ss = await self.data.sector_stock_snapshot(sector)
            target = ss.sector or sector
            ev = await self.search.search([f"{target} 行业 价格 供需 产能 近30天", f"{target} 上市公司 公告 业绩 订单 定增 减持", f"{target} 机构研报 评级 近1月"], 30, 5)
            if ev:
                ss.events.extend(ev)
            f = await self.agents.run({"sector": json.loads(j(ss)), "events": [asdict(e) for e in ss.events]})
            html, title = render_sector(ss, f), f"{ss.sector}板块个股分析"
        elif report_type in EXPANDED_REPORT_IDS:
            html, title = await render_expanded_report(report_type, sector)
        else:
            m, q = await self.data.market_snapshot(), await self.data.quant_snapshot()
            f = await self.agents.run({"market": json.loads(j(m)), "quant": json.loads(j(q))})
            html, title = render_agents(f), "A股多智能体投研报告"
        fn = self._save(report_type, html)
        return {"report_type": report_type, "filename": fn, "url": f"/reports/{fn}", "title": title, "generated_at": now_str(), "llm": self._llm_status()}

    async def generate_all(self, sector: str = "光伏设备") -> list[dict]:
        out = []
        for rt in ["market_replay", "quant_factor", "sector_stock", *EXPANDED_REPORT_IDS, "agent_debate"]:
            out.append(await self.generate(rt, sector))
        return out

    def _save(self, report_type: str, html: str) -> str:
        fn = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        (settings.report_path / fn).write_text(html, encoding="utf-8")
        (settings.report_path / f"{report_type}_latest.html").write_text(html, encoding="utf-8")
        return fn

    def list_reports(self) -> list[dict]:
        fs = sorted(settings.report_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"filename":p.name, "url":f"/reports/{p.name}", "mtime":datetime.fromtimestamp(p.stat().st_mtime).isoformat()} for p in fs]


# =========================
# FastAPI
# =========================

app = FastAPI(title="A-Share Research HTML Skill", version="0.1.0")
app.mount("/static", StaticFiles(directory="backend/app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    reports = Pipeline().list_reports()
    cards = "".join(f"<a class='card' href='{r['url']}' target='_blank'><b>{r['filename']}</b><span>{r['mtime']}</span></a>" for r in reports[:30]) or "<div class='empty'>暂无报告，点击刷新全部。</div>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A股投研页面中心</title><style>body{{margin:0;background:#0d1117;color:#e6edf3;font-family:PingFang SC,Microsoft YaHei,Arial,sans-serif}}.wrap{{max-width:1200px;margin:auto;padding:24px}}.top{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}}.btn{{background:#238636;color:#fff;border-radius:10px;padding:10px 14px;text-decoration:none}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:18px}}.card{{display:flex;flex-direction:column;gap:8px;color:#e6edf3;text-decoration:none;background:#161b22;border:1px solid #30363d;border-radius:16px;padding:16px}}span,p{{color:#8b949e}}</style></head><body><div class="wrap"><div class="top"><div><h1>A股投研 HTML 页面中心</h1><p>行情复盘｜量化因子｜板块个股｜资金轮动｜聪明资金｜估值诊断｜趋势共振｜自选股｜指数ETF｜流动性｜催化日历｜事件风险｜产业链｜海外映射｜多智能体</p></div><a class="btn" href="/api/reports/refresh-all">刷新全部页面</a></div><div class="grid">{cards}</div></div></body></html>"""

@app.get("/reports/{filename}")
async def report(filename: str):
    p = settings.report_path / filename
    if not p.exists():
        return HTMLResponse("<h1>报告不存在</h1>", status_code=404)
    return FileResponse(p, media_type="text/html")

@app.get("/api/reports")
async def list_reports():
    return Pipeline().list_reports()

@app.post("/api/reports/generate")
async def generate(
    report_type: ReportType,
    sector: str = Query("光伏设备"),
    llm_base_url: str | None = Query(None),
    llm_api_key: str | None = Query(None),
    llm_model: str | None = Query(None),
    x_llm_api_key: str | None = Header(None, alias="X-LLM-API-Key"),
):
    return await Pipeline(resolve_llm_config(llm_base_url, llm_api_key or x_llm_api_key, llm_model)).generate(report_type, sector)

@app.get("/api/reports/refresh-all")
async def refresh_all(
    sector: str = Query("光伏设备"),
    llm_base_url: str | None = Query(None),
    llm_api_key: str | None = Query(None),
    llm_model: str | None = Query(None),
    x_llm_api_key: str | None = Header(None, alias="X-LLM-API-Key"),
):
    return await Pipeline(resolve_llm_config(llm_base_url, llm_api_key or x_llm_api_key, llm_model)).generate_all(sector)

@app.get("/api/health")
async def health():
    return {"ok": True, "provider": settings.data_provider, "report_dir": str(settings.report_path), "default_llm": LLMConfig.from_settings().public_dict()}
