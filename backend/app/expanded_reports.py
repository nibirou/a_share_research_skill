from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

from backend.app.source_registry import (
    CninfoClient,
    EastmoneyClient,
    SinaFinanceClient,
    SinaGlobalClient,
    SinaQuoteClient,
    ThsClient,
    XTickClient,
    retrieved_at,
)


EXPANDED_REPORT_IDS = [
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

EXPANDED_REPORT_TITLES = {
    "sector_flow_rotation": "板块资金轮动与六个月展望",
    "smart_money_clusters": "聪明资金攻击宽度诊断",
    "sector_valuation_diagnosis": "板块估值与基本面诊断",
    "trend_resonance": "趋势共振与强弱背离",
    "watchlist_terminal": "自选股池深度分析终端",
    "index_etf_monitor": "指数 ETF 风格监控",
    "liquidity_dashboard": "市场流动性仪表盘",
    "earnings_catalyst_calendar": "财报与催化日历",
    "single_stock_event_risk": "单股事件风险雷达",
    "industry_chain_map": "产业链传导与受益矩阵",
    "global_mapping": "海外映射与 A 股联动",
}

PROMPT_FILES = {
    "sector_flow_rotation": "04_sector_flow_rotation.md",
    "smart_money_clusters": "05_smart_money_attack_width.md",
    "sector_valuation_diagnosis": "06_sector_valuation_diagnosis.md",
    "trend_resonance": "07_trend_resonance.md",
    "watchlist_terminal": "08_watchlist_terminal.md",
    "index_etf_monitor": "09_index_etf_style_monitor.md",
    "liquidity_dashboard": "10_liquidity_dashboard.md",
    "earnings_catalyst_calendar": "11_earnings_catalyst_calendar.md",
    "single_stock_event_risk": "12_single_stock_event_risk.md",
    "industry_chain_map": "13_industry_chain_map.md",
    "global_mapping": "14_global_mapping.md",
}

PROMPT_DIR = Path("skill/references/html_prompts")
CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"


@dataclass
class ExpandedContext:
    retrieved_at: str
    indices: list[dict[str, Any]]
    industries: list[dict[str, Any]]
    concepts: list[dict[str, Any]]
    etfs: list[dict[str, Any]]
    a_spot: list[dict[str, Any]]
    target_board_code: str
    target_constituents: list[dict[str, Any]]
    xtick_index_count: int | None
    xtick_etf_count: int | None
    xtick_emotion: dict[str, Any] | None
    xtick_money_top: list[dict[str, Any]]
    xtick_news: list[dict[str, Any]]
    announcements: list[dict[str, Any]]
    global_quotes: list[dict[str, Any]]
    lhb_rows: list[dict[str, Any]]
    lhb_institution_rows: list[dict[str, Any]]
    lhb_seat_rows: list[dict[str, Any]]
    margin_rows: list[dict[str, Any]]
    northbound_rows: list[dict[str, Any]]
    unlock_rows: list[dict[str, Any]]
    reduction_rows: list[dict[str, Any]]
    reduction_announcements: list[dict[str, Any]]
    institution_hold_rows: list[dict[str, Any]]
    financial_rows: list[dict[str, Any]]
    errors: list[str]


_CTX_CACHE: dict[str, tuple[float, ExpandedContext]] = {}


def sanitize_error(text: str) -> str:
    return re.sub(r"token=[^,;\s]+", "token=***", text)


def normalize_xtick_money(rows: Any, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        code = str(row.get("code", ""))
        if code.startswith("899"):
            continue
        buy = (
            float(row.get("buyMostAmount") or 0)
            + float(row.get("buyBigAmount") or 0)
            + float(row.get("buyMediumAmount") or 0)
        )
        sell = (
            float(row.get("sellMostAmount") or 0)
            + float(row.get("sellBigAmount") or 0)
            + float(row.get("sellMediumAmount") or 0)
        )
        out.append(
            {
                "provider": "xtick",
                "code": code,
                "net_inflow_yi": round((buy - sell) / 100000000, 4),
                "buy_count": int(row.get("buyNumber") or 0),
                "sell_count": int(row.get("sellNumber") or 0),
            }
        )
    return sorted(out, key=lambda x: abs(float(x.get("net_inflow_yi") or 0)), reverse=True)[:limit]


async def collect_expanded_context(target: str = "光伏设备", ttl_seconds: int = 90) -> ExpandedContext:
    global _CTX_CACHE
    now = datetime.now().timestamp()
    cache_key = target.strip() or "default"
    if cache_key in _CTX_CACHE and now - _CTX_CACHE[cache_key][0] <= ttl_seconds:
        return _CTX_CACHE[cache_key][1]

    errors: list[str] = []
    trade_date = datetime.now().strftime("%Y-%m-%d")
    east = EastmoneyClient()

    async def get_indices() -> list[dict[str, Any]]:
        try:
            return await SinaQuoteClient().index_quotes()
        except Exception as exc:
            errors.append(f"Sina index failed: {type(exc).__name__}: {exc}")
            return []

    async def get_industries() -> list[dict[str, Any]]:
        try:
            return await ThsClient().industry_rank()
        except Exception as exc:
            errors.append(f"THS industry failed: {type(exc).__name__}: {exc}")
        try:
            return await east.industry_rank(500)
        except Exception as exc:
            errors.append(f"Eastmoney industry failed: {type(exc).__name__}: {exc}")
            return []

    async def get_concepts() -> list[dict[str, Any]]:
        try:
            return await east.concept_rank(300)
        except Exception as exc:
            errors.append(f"Eastmoney concept failed: {type(exc).__name__}: {exc}")
            return []

    async def get_etfs() -> list[dict[str, Any]]:
        try:
            return await east.etf_rank(120)
        except Exception as exc:
            errors.append(f"Eastmoney ETF failed: {type(exc).__name__}: {exc}")
            return []

    async def get_a_spot() -> list[dict[str, Any]]:
        try:
            return await east.a_spot(160)
        except Exception as exc:
            errors.append(f"Eastmoney A spot failed: {type(exc).__name__}: {exc}")
            return []

    async def get_target_constituents() -> tuple[str, list[dict[str, Any]]]:
        try:
            return await east.board_constituents_by_name(target, 120)
        except Exception as exc:
            errors.append(f"Eastmoney board constituents failed: {type(exc).__name__}: {exc}")
            return "", []

    async def get_xtick_bundle() -> tuple[int | None, int | None, dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
        xtick = XTickClient()
        index_count: int | None = None
        etf_count: int | None = None
        emotion: dict[str, Any] | None = None
        money: list[dict[str, Any]] = []
        news: list[dict[str, Any]] = []
        try:
            index_count = len(await xtick.stock_info("index"))
        except Exception as exc:
            errors.append(f"XTick index master failed: {type(exc).__name__}: {exc}")
        try:
            etf_count = len(await xtick.stock_info("etf"))
        except Exception as exc:
            errors.append(f"XTick ETF master failed: {type(exc).__name__}: {exc}")
        try:
            raw = await xtick.market_emotion(trade_date)
            emotion = raw[0] if isinstance(raw, list) and raw else raw if isinstance(raw, dict) else None
        except Exception as exc:
            errors.append(f"XTick emotion failed: {type(exc).__name__}: {exc}")
        try:
            money = normalize_xtick_money(await xtick.money_flow("all", trade_date, trade_date))
        except Exception as exc:
            errors.append(f"XTick money failed: {type(exc).__name__}: {exc}")
        try:
            raw_news = await xtick.news(trade_date, 0)
            news = raw_news[:10] if isinstance(raw_news, list) else []
        except Exception as exc:
            errors.append(f"XTick news failed: {type(exc).__name__}: {exc}")
        return index_count, etf_count, emotion, money, news

    async def get_announcements() -> list[dict[str, Any]]:
        try:
            stock_code = target if target.strip().isdigit() and len(target.strip()) == 6 else ""
            keyword = "" if stock_code else target
            return await CninfoClient().announcements(keyword=keyword, stock_code=stock_code, days=30, limit=12)
        except Exception as exc:
            errors.append(f"CNINFO announcement failed: {type(exc).__name__}: {exc}")
            return []

    async def get_global_quotes() -> list[dict[str, Any]]:
        try:
            return await SinaGlobalClient().quotes()
        except Exception as exc:
            errors.append(f"Sina global failed: {type(exc).__name__}: {exc}")
            return []

    (
        indices,
        industries,
        concepts,
        etfs,
        a_spot,
        target_bundle,
        xtick_bundle,
        announcements,
        global_quotes,
    ) = await asyncio.gather(
        get_indices(),
        get_industries(),
        get_concepts(),
        get_etfs(),
        get_a_spot(),
        get_target_constituents(),
        get_xtick_bundle(),
        get_announcements(),
        get_global_quotes(),
    )
    target_board_code, target_constituents = target_bundle
    xtick_count, xtick_etf_count, xtick_emotion, xtick_money_top, xtick_news = xtick_bundle

    if not target_constituents:
        await asyncio.sleep(1)
        try:
            target_board_code, target_constituents = await east.board_constituents_by_name(target, 120)
        except Exception as exc:
            errors.append(f"Eastmoney board constituents retry failed: {type(exc).__name__}: {exc}")
    if not target_constituents:
        try:
            ths_code, ths_rows = await ThsClient().industry_constituents_by_name(target, 120)
            if ths_rows:
                target_board_code = f"THS{ths_code}"
                target_constituents = ths_rows
                errors.append("Eastmoney board constituents unavailable; used THS industry constituents fallback")
        except Exception as exc:
            errors.append(f"THS industry constituents fallback failed: {type(exc).__name__}: {exc}")
    if not etfs:
        await asyncio.sleep(0.5)
        try:
            etfs = await east.etf_rank(120)
        except Exception as exc:
            errors.append(f"Eastmoney ETF retry failed: {type(exc).__name__}: {exc}")
    if not a_spot:
        await asyncio.sleep(0.5)
        try:
            a_spot = await east.a_spot(160)
        except Exception as exc:
            errors.append(f"Eastmoney A spot retry failed: {type(exc).__name__}: {exc}")
    if not xtick_emotion and a_spot:
        xtick_emotion = {
            "ztnum": sum(1 for x in a_spot if pct(x.get("pct_chg")) >= 9.8),
            "dtnum": sum(1 for x in a_spot if pct(x.get("pct_chg")) <= -9.8),
            "zbnum": "数据缺失",
            "mhigh": "数据缺失",
            "provider": "eastmoney_proxy",
        }
        errors.append("XTick emotion unavailable; used Eastmoney all-A pct-change proxy for limit-up/down counts")

    if not announcements and target_constituents:
        cninfo = CninfoClient()

        async def get_constituent_announcements(stock: dict[str, Any]) -> list[dict[str, Any]]:
            code = str(stock.get("code", "")).strip()
            if not (code.isdigit() and len(code) == 6):
                return []
            try:
                return await cninfo.announcements(stock_code=code, days=30, limit=4)
            except Exception as exc:
                errors.append(f"CNINFO constituent {code} failed: {type(exc).__name__}: {exc}")
                return []

        batches = await asyncio.gather(*(get_constituent_announcements(x) for x in target_constituents[:4]))
        seen: set[str] = set()
        announcements = []
        for row in [item for batch in batches for item in batch]:
            key = str(row.get("url") or row.get("title") or "")
            if key and key not in seen:
                seen.add(key)
                announcements.append(row)
            if len(announcements) >= 12:
                break

    target_codes = {
        str(x.get("code", "")).strip()
        for x in target_constituents
        if str(x.get("code", "")).strip().isdigit()
    }
    target_name_by_code = {str(x.get("code", "")).strip(): str(x.get("name", "")) for x in target_constituents}
    stock_samples = []
    if target.strip().isdigit() and len(target.strip()) == 6:
        stock_samples.append({"code": target.strip(), "name": target.strip()})
    stock_samples.extend([x for x in target_constituents if str(x.get("code", "")).strip().isdigit()])
    stock_samples = stock_samples[:3]

    def prefer_target_rows(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
        if not rows:
            return []
        if target_codes:
            hits = [x for x in rows if str(x.get("code", "")).strip() in target_codes]
            if hits:
                return hits[:limit]
        return rows[:limit]

    start_10 = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    end_today = datetime.now().strftime("%Y%m%d")
    future_180 = (datetime.now() + timedelta(days=180)).strftime("%Y%m%d")

    async def get_lhb_rows() -> list[dict[str, Any]]:
        try:
            return prefer_target_rows(await east.lhb_daily(start_10, end_today, 80), 12)
        except Exception as exc:
            errors.append(f"Eastmoney LHB daily failed: {type(exc).__name__}: {exc}")
            return []

    async def get_lhb_institution_rows() -> list[dict[str, Any]]:
        try:
            return prefer_target_rows(await east.lhb_institution_trades(start_10, end_today, 80), 12)
        except Exception as exc:
            errors.append(f"Eastmoney LHB institution failed: {type(exc).__name__}: {exc}")
            return []

    async def get_lhb_seat_rows() -> list[dict[str, Any]]:
        try:
            return prefer_target_rows(await east.lhb_institution_seats("01", 80), 12)
        except Exception as exc:
            errors.append(f"Eastmoney LHB seat failed: {type(exc).__name__}: {exc}")
            return []

    async def get_margin_rows() -> list[dict[str, Any]]:
        try:
            return await east.margin_account(12)
        except Exception as exc:
            errors.append(f"Eastmoney margin failed: {type(exc).__name__}: {exc}")
            return []

    async def get_northbound_rows() -> list[dict[str, Any]]:
        try:
            return await east.northbound_deal_history(5)
        except Exception as exc:
            errors.append(f"Eastmoney northbound failed: {type(exc).__name__}: {exc}")
            return []

    async def get_unlock_rows() -> list[dict[str, Any]]:
        try:
            return prefer_target_rows(await east.restricted_release(end_today, future_180, 200), 12)
        except Exception as exc:
            errors.append(f"Eastmoney unlock failed: {type(exc).__name__}: {exc}")
            return []

    async def get_reduction_rows() -> list[dict[str, Any]]:
        try:
            return prefer_target_rows(await east.executive_hold_changes(120), 12)
        except Exception as exc:
            errors.append(f"Eastmoney reduction failed: {type(exc).__name__}: {exc}")
            return []

    async def get_reduction_announcements() -> list[dict[str, Any]]:
        cninfo = CninfoClient()
        queries = []
        if target.strip().isdigit() and len(target.strip()) == 6:
            queries.append(f"{target.strip()} 减持")
        for stock in stock_samples:
            code = str(stock.get("code", "")).strip()
            name = str(stock.get("name", "")).strip()
            if code:
                queries.append(f"{code} 减持")
            if name and name != code:
                queries.append(f"{name} 减持")
        queries.append(f"{target} 减持")
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries[:8]:
            try:
                rows = await cninfo.announcements(keyword=query, days=180, limit=5)
            except Exception as exc:
                errors.append(f"CNINFO reduction {query} failed: {type(exc).__name__}: {exc}")
                continue
            for row in rows:
                key = str(row.get("url") or row.get("title") or "")
                if key and key not in seen:
                    seen.add(key)
                    out.append(row)
                if len(out) >= 10:
                    return out
        return out

    async def get_institution_hold_rows() -> list[dict[str, Any]]:
        try:
            rows = await east.fund_holdings(limit=1200)
            filtered = prefer_target_rows(rows, 12)
            for row in filtered:
                if not row.get("name") and row.get("code") in target_name_by_code:
                    row["name"] = target_name_by_code[row["code"]]
            return filtered
        except Exception as exc:
            errors.append(f"Eastmoney fund holding failed: {type(exc).__name__}: {exc}")
            return []

    async def get_financial_rows() -> list[dict[str, Any]]:
        finance = SinaFinanceClient()

        async def one(stock: dict[str, Any]) -> dict[str, Any] | None:
            code = str(stock.get("code", "")).strip()
            if not (code.isdigit() and len(code) == 6):
                return None
            try:
                rows = await finance.financial_snapshot(code, 1)
            except Exception as exc:
                errors.append(f"Sina finance {code} failed: {type(exc).__name__}: {exc}")
                return None
            if not rows:
                return None
            row = rows[0]
            row["name"] = str(stock.get("name", "") or target_name_by_code.get(code, ""))
            return row

        rows = await asyncio.gather(*(one(x) for x in stock_samples))
        return [x for x in rows if x]

    (
        lhb_rows,
        lhb_institution_rows,
        lhb_seat_rows,
        margin_rows,
        northbound_rows,
        unlock_rows,
        reduction_rows,
        reduction_announcements,
        institution_hold_rows,
        financial_rows,
    ) = await asyncio.gather(
        get_lhb_rows(),
        get_lhb_institution_rows(),
        get_lhb_seat_rows(),
        get_margin_rows(),
        get_northbound_rows(),
        get_unlock_rows(),
        get_reduction_rows(),
        get_reduction_announcements(),
        get_institution_hold_rows(),
        get_financial_rows(),
    )

    ctx = ExpandedContext(
        retrieved_at(),
        indices,
        industries,
        concepts,
        etfs,
        a_spot,
        target_board_code,
        target_constituents,
        xtick_count,
        xtick_etf_count,
        xtick_emotion,
        xtick_money_top,
        xtick_news,
        announcements,
        global_quotes,
        lhb_rows,
        lhb_institution_rows,
        lhb_seat_rows,
        margin_rows,
        northbound_rows,
        unlock_rows,
        reduction_rows,
        reduction_announcements,
        institution_hold_rows,
        financial_rows,
        errors,
    )
    _CTX_CACHE[cache_key] = (now, ctx)
    return ctx


def pct(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def fmt(value: Any, suffix: str = "") -> str:
    try:
        return f"{float(value):+.2f}{suffix}"
    except Exception:
        return f"数据缺失{suffix}"


def emotion_text(emotion: dict[str, Any] | None) -> str:
    if not isinstance(emotion, dict):
        return "XTick 情绪缺失"
    if emotion.get("provider") == "eastmoney_proxy":
        return f"XTick 情绪缺失；东财样本涨停 {emotion.get('ztnum', '数据缺失')}、样本跌停 {emotion.get('dtnum', '数据缺失')}。"
    keys = ("ztnum", "dtnum", "zbnum", "mhigh")
    if any(emotion.get(k) is None for k in keys):
        return "XTick 情绪缺失"
    return (
        f"涨停 {emotion.get('ztnum')}，跌停 {emotion.get('dtnum')}，"
        f"炸板 {emotion.get('zbnum')}，最高连板 {emotion.get('mhigh')}。"
    )


def cls(value: Any) -> str:
    v = pct(value)
    return "up" if v > 0 else "down" if v < 0 else "flat"


def value_for(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    if key == "net_inflow_yi":
        return row.get("main_net_inflow_yi")
    if key == "amount_yi":
        return row.get("amount_yi")
    return 0


def top_industries(ctx: ExpandedContext, key: str, reverse: bool = True, limit: int = 8) -> list[dict[str, Any]]:
    return sorted(ctx.industries, key=lambda x: pct(value_for(x, key)), reverse=reverse)[:limit]


def industry_width(ctx: ExpandedContext) -> float:
    up = sum(int(x.get("up_count") or 0) for x in ctx.industries)
    down = sum(int(x.get("down_count") or 0) for x in ctx.industries)
    if not up and not down and ctx.industries:
        up = sum(1 for x in ctx.industries if pct(x.get("pct_chg")) > 0)
        down = sum(1 for x in ctx.industries if pct(x.get("pct_chg")) < 0)
    return round(up / max(up + down, 1) * 100, 2)


def prompt_path(report_id: str) -> str:
    return str(PROMPT_DIR / PROMPT_FILES[report_id])


def prompt_status(report_id: str) -> str:
    p = PROMPT_DIR / PROMPT_FILES[report_id]
    return "已加载" if p.exists() else "缺失"


def modules_for(report_id: str, target: str, ctx: ExpandedContext) -> list[dict[str, str]]:
    width = industry_width(ctx)
    flow = round(sum(pct(value_for(x, "net_inflow_yi")) for x in ctx.industries), 2)
    leaders = "、".join(x.get("name", "") for x in top_industries(ctx, "pct_chg", True, 3)) or "数据缺失"
    inflow = "、".join(x.get("name", "") for x in top_industries(ctx, "net_inflow_yi", True, 3)) or "数据缺失"
    outflow = "、".join(x.get("name", "") for x in top_industries(ctx, "net_inflow_yi", False, 3)) or "数据缺失"
    index_note = "、".join(f"{x.get('name')} {fmt(x.get('pct_chg'), '%')}" for x in ctx.indices[:4]) or "指数数据缺失"
    etf_note = "、".join(f"{x.get('name')} {fmt(x.get('pct_chg'), '%')}" for x in ctx.etfs[:3]) or "ETF 数据缺失"
    target_stocks = "、".join(f"{x.get('name')} {fmt(x.get('pct_chg'), '%')}" for x in ctx.target_constituents[:3]) or "目标成分股缺失"
    event_note = "；".join(x.get("title", "")[:28] for x in ctx.announcements[:2]) or "近 30 天未检索到目标公告"
    global_note = "、".join(f"{x.get('name')} {fmt(x.get('pct_chg'), '%')}" for x in ctx.global_quotes[:4]) or "海外行情缺失"
    emotion_note = emotion_text(ctx.xtick_emotion).rstrip("。")

    common = {
        "rotation": f"行业上涨家数宽度约 {width:.1f}%，资金净流合计 {flow:+.2f} 亿；领涨集中在 {leaders}。",
        "flow": f"净流入靠前：{inflow}；净流出靠前：{outflow}。",
        "index": f"宽基状态：{index_note}。",
        "events": f"公告/事件：{event_note}。",
        "target": f"目标成分：{target_stocks}。",
        "etf": f"ETF/基金：{etf_note}。",
        "global": f"海外/港美映射：{global_note}。",
        "emotion": f"短线情绪：{emotion_note}。",
        "missing": "龙虎榜、机构席位、机构持仓、解禁、高管增减持、两融、北向和财报三表已接入公共兜底；ETF申赎份额、回购利率、收入结构/业务纯度仍按缺失或代理口径处理。",
    }

    profiles: dict[str, list[dict[str, str]]] = {
        "sector_flow_rotation": [
            {"title": "轮动结论", "body": common["rotation"]},
            {"title": "资金持续性", "body": common["flow"]},
            {"title": "六个月观察轴", "body": f"按当前月到未来五个月跟踪政策、财报、价格、订单、流动性和外部风险六类节点；{common['events']}"},
            {"title": "触发条件", "body": "若净流入行业继续扩散且指数跌幅收敛，轮动质量提升；若资金只集中在少数高位行业，降级为短线交易。"},
        ],
        "smart_money_clusters": [
            {"title": "攻击宽度", "body": f"当前行业宽度约 {width:.1f}%，可作为聪明资金是否扩散的首要观察指标。"},
            {"title": "主攻簇", "body": f"以净流入排序，当前主攻簇集中在 {inflow}。"},
            {"title": "撤离簇", "body": f"资金撤离更明显的方向为 {outflow}。"},
            {"title": "验证信号", "body": f"{common['emotion'].rstrip('。')}；已接入东财龙虎榜与机构席位公共兜底，ETF 份额和连续 3/5/20 日净流入仍需专项接口确认。"},
        ],
        "sector_valuation_diagnosis": [
            {"title": "目标范围", "body": f"当前诊断目标：{target}；若目标不是标准行业名，则先使用全行业扫描结果定位可比组。"},
            {"title": "估值状态", "body": f"已接入东方财富动态 PE/PB/市值字段和 Sina 财报三表摘要作为估值兜底；{common['target']}。ROE、利润率等衍生指标后续可由三表继续计算。"},
            {"title": "资金辅助判断", "body": common["flow"]},
            {"title": "降级规则", "body": "估值或财报字段缺失的行业和个股，只能进入观察池，不能直接进入高置信推荐池。"},
        ],
        "trend_resonance": [
            {"title": "指数共振", "body": common["index"]},
            {"title": "行业共振", "body": f"价格强势行业：{leaders}；资金强势行业：{inflow}。"},
            {"title": "背离识别", "body": "价格上涨但净流出为诱多风险；价格下跌但净流入为承接观察，需下一交易日确认。"},
            {"title": "入池条件", "body": "行业涨幅、资金净流入、上涨家数宽度三者同向时，趋势共振评分上调。"},
        ],
        "watchlist_terminal": [
            {"title": "候选池", "body": f"未传入自选股代码时，默认使用行业领涨股和资金流入行业生成观察池：{leaders}。"},
            {"title": "实时看板", "body": common["index"]},
            {"title": "优先级", "body": f"优先关注价格强、资金强、行业宽度扩散的候选；{common['events']}；ST、公告风险、财报缺失项降级。"},
            {"title": "下一步", "body": "后续可增加 watchlist 参数，支持用户传入股票代码列表后逐一拉取行情、公告和风险。"},
        ],
        "index_etf_monitor": [
            {"title": "宽基状态", "body": common["index"]},
            {"title": "风格判断", "body": "创业板/科创相对上证更弱时，成长风格承压；北证或小盘逆势时，短线风险偏好局部存在。"},
            {"title": "ETF 字段", "body": f"{common['etf']}；已接入 ETF 实时涨跌、成交、资金流，份额/申赎仍需 Tushare ETF 或交易所接口。"},
            {"title": "监控条件", "body": "若指数修复与 ETF 净申购同步，风格趋势可信度提高。"},
        ],
        "liquidity_dashboard": [
            {"title": "成交与宽度", "body": f"行业上涨家数宽度约 {width:.1f}%，行业净流合计 {flow:+.2f} 亿。"},
            {"title": "资金面", "body": common["flow"]},
            {"title": "ETF 与外部流动性", "body": f"{common['etf']}；{common['global']}。两融和北向已接入东财公共兜底，回购利率与 ETF 份额仍需交易所/基金专项接口。"},
            {"title": "风险灯", "body": "指数下跌、行业宽度收窄、资金净流出同时出现时，流动性状态下调。"},
        ],
        "earnings_catalyst_calendar": [
            {"title": "财报窗口", "body": "按当前月到未来五个月跟踪中报/三季报预告、业绩快报、订单公告和政策会议。"},
            {"title": "行业催化", "body": f"优先跟踪资金与涨幅同步的行业：{inflow}。"},
            {"title": "公告接入", "body": f"已接入 CNINFO 近 30 天公告兜底；{common['events']}"},
            {"title": "风险节点", "body": "解禁、减持、监管问询和业绩不及预期是日历中的硬风险项。"},
        ],
        "single_stock_event_risk": [
            {"title": "分析对象", "body": f"当前对象：{target}。如果不是股票代码，则按主题/行业对象输出事件风险模板。"},
            {"title": "行情背景", "body": common["index"]},
            {"title": "事件字段", "body": f"CNINFO 公告已作为官方兜底；{common['events']}。解禁和高管增减持已接入东财结构化兜底，诉讼/质押仍以 CNINFO 公告核验为主。"},
            {"title": "降级规则", "body": "无法验证公告或财报时，结论只给观察，不给强方向判断。"},
        ],
        "industry_chain_map": [
            {"title": "目标产业链", "body": f"以 {target} 为目标，先从全市场行业资金与涨幅定位上游、中游、下游的热度差。"},
            {"title": "受益环节", "body": f"当前资金更偏向：{inflow}；{common['target']}"},
            {"title": "传导逻辑", "body": "价格上涨、订单改善、产能出清、政策补贴和技术迭代是产业链传导的五类核心变量。"},
            {"title": "待补字段", "body": "收入结构、业务纯度、供应链客户、海外收入占比待接入财报和公告解析。"},
        ],
        "global_mapping": [
            {"title": "海外映射", "body": common["global"]},
            {"title": "A 股承接", "body": f"当前 A 股资金承接方向：{inflow}。"},
            {"title": "风险传导", "body": "美元、利率、商品价格和海外科技股波动会影响成长、资源和出口链估值。"},
            {"title": "待补字段", "body": "海外龙头财报摘要、订单和制裁政策仍需 SearchHub/官方公告交叉验证；Sina 全球行情只作为价格层兜底。"},
        ],
    }
    return profiles[report_id]


def render_expanded_report_sync(report_id: str, target: str, ctx: ExpandedContext) -> tuple[str, str]:
    title = EXPANDED_REPORT_TITLES[report_id]
    modules = modules_for(report_id, target, ctx)
    leaders = top_industries(ctx, "pct_chg", True, 10)
    inflows = top_industries(ctx, "net_inflow_yi", True, 10)
    outflows = top_industries(ctx, "net_inflow_yi", False, 10)
    stock_inflows = sorted(ctx.target_constituents or ctx.a_spot, key=lambda x: pct(x.get("main_net_inflow_yi")), reverse=True)[:12]
    etf_leaders = sorted(ctx.etfs, key=lambda x: pct(x.get("pct_chg")), reverse=True)[:10]
    indices_json = json.dumps(ctx.indices, ensure_ascii=False)
    industries_json = json.dumps(leaders, ensure_ascii=False)
    flow_json = json.dumps(inflows + outflows, ensure_ascii=False)
    prompt_file = prompt_path(report_id)
    prompt_loaded = prompt_status(report_id)
    width = industry_width(ctx)
    flow_total = round(sum(pct(value_for(x, "net_inflow_yi")) for x in ctx.industries), 2)
    xtick_emotion_text = emotion_text(ctx.xtick_emotion)

    def index_cards() -> str:
        if not ctx.indices:
            return "<div class='metric'><b>指数数据缺失</b><span>请检查 Sina/XTick 行情源</span></div>"
        return "".join(
            f"<div class='metric'><span>{escape(str(x.get('name', '指数')))}</span>"
            f"<b class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</b>"
            f"<small>{escape(str(x.get('quote_time', '')))}</small></div>"
            for x in ctx.indices[:5]
        )

    def module_cards() -> str:
        return "".join(
            f"<section class='panel'><h2>{escape(m['title'])}</h2><p>{escape(m['body'])}</p></section>"
            for m in modules
        )

    def industry_rows(rows: list[dict[str, Any]], mode: str) -> str:
        if not rows:
            return "<tr><td colspan='6'>数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td><b>{escape(str(x.get('name', '')))}</b></td>"
            f"<td class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</td>"
            f"<td class='{cls(value_for(x, 'net_inflow_yi'))}'>{fmt(value_for(x, 'net_inflow_yi'), ' 亿')}</td>"
            f"<td>{int(x.get('up_count') or 0)}/{int(x.get('down_count') or 0)}</td>"
            f"<td>{escape(str(x.get('leader', '')))}</td></tr>"
            for i, x in enumerate(rows, 1)
        )

    def stock_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('code', '')))}</td><td><b>{escape(str(x.get('name', '')))}</b></td>"
            f"<td class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</td>"
            f"<td class='{cls(x.get('main_net_inflow_yi'))}'>{fmt(x.get('main_net_inflow_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('float_mv_yi'), ' 亿')}</td><td>{fmt(x.get('pe_dynamic'))}/{fmt(x.get('pb'))}</td>"
            f"<td>{'风险降级' if 'ST' in str(x.get('name', '')) or pct(x.get('pe_dynamic')) < 0 else '观察'}</td></tr>"
            for i, x in enumerate(rows, 1)
        )

    def etf_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='6'>数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('code', '')))}</td><td><b>{escape(str(x.get('name', '')))}</b></td>"
            f"<td class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</td>"
            f"<td>{fmt(x.get('amount_yi'), ' 亿')}</td><td class='{cls(x.get('main_net_inflow_yi'))}'>{fmt(x.get('main_net_inflow_yi'), ' 亿')}</td></tr>"
            for i, x in enumerate(rows, 1)
        )

    def global_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='5'>数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('name', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</td><td>{escape(str(x.get('quote_time', '')))}</td></tr>"
            for i, x in enumerate(rows[:10], 1)
        )

    def event_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='5'>近 30 天未检索到目标公告</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('code', '')))}</td><td>{escape(str(x.get('name', '')))}</td>"
            f"<td>{escape(str(x.get('title', ''))[:80])}</td><td>{escape(str(x.get('announcement_time', '')))}</td></tr>"
            for i, x in enumerate(rows[:10], 1)
        )

    def news_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='4'>XTick 新闻缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('platName', '')))}</td><td>{escape(str(x.get('title', ''))[:80])}</td>"
            f"<td><a href='{escape(str(x.get('url', '')))}' target='_blank'>source</a></td></tr>"
            for i, x in enumerate(rows[:8], 1)
        )

    def lhb_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='7'>龙虎榜数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('trade_date', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td class='{cls(x.get('pct_chg'))}'>{fmt(x.get('pct_chg'), '%')}</td>"
            f"<td class='{cls(x.get('net_buy_yi'))}'>{fmt(x.get('net_buy_yi'), ' 亿')}</td><td>{escape(str(x.get('reason', ''))[:42])}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def lhb_institution_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>机构席位数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('trade_date', x.get('cycle', ''))))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td>{int(x.get('buy_count') or x.get('buy_times') or 0)}/{int(x.get('sell_count') or x.get('sell_times') or 0)}</td>"
            f"<td class='{cls(x.get('institution_net_yi', x.get('net_buy_yi')))}'>{fmt(x.get('institution_net_yi', x.get('net_buy_yi')), ' 亿')}</td>"
            f"<td>{fmt(x.get('institution_buy_yi', x.get('buy_yi')), ' 亿')}</td><td>{fmt(x.get('institution_sell_yi', x.get('sell_yi')), ' 亿')}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def margin_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='7'>两融数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('trade_date', '')))}</td><td>{fmt(x.get('margin_balance_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('fin_balance_yi'), ' 亿')}</td><td>{fmt(x.get('fin_buy_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('loan_balance_yi'), ' 亿')}</td><td>{fmt(x.get('avg_guarantee_ratio'), '%')}</td></tr>"
            for i, x in enumerate(rows[:8], 1)
        )

    def northbound_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='7'>北向数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('trade_date', '')))}</td><td>{escape(str(x.get('type', '')))}</td>"
            f"<td>{fmt(x.get('deal_amt_yi'), ' 亿')}</td><td>{int(x.get('deal_num') or 0)}</td>"
            f"<td>{escape(str(x.get('lead_stock', '')))}</td><td class='{cls(x.get('lead_stock_pct'))}'>{fmt(x.get('lead_stock_pct'), '%')}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def unlock_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>未来 180 天未命中结构化解禁数据</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('free_date', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td>{fmt(x.get('lift_market_cap_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('free_ratio'), '%')}</td><td>{int(x.get('batch_holder_num') or 0)}</td><td>{escape(str(x.get('shares_type', ''))[:30])}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def reduction_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='7'>结构化增减持数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('change_date', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td>{escape(str(x.get('person', '')))}</td>"
            f"<td class='{cls(x.get('change_shares'))}'>{fmt(x.get('change_shares'), ' 股')}</td><td>{escape(str(x.get('change_reason', ''))[:28])}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def reduction_announcement_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='5'>CNINFO 未检索到目标相关减持公告</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('code', '')))}</td><td>{escape(str(x.get('name', '')))}</td>"
            f"<td>{escape(str(x.get('title', ''))[:80])}</td><td>{escape(str(x.get('announcement_time', '')))}</td></tr>"
            for i, x in enumerate(rows[:10], 1)
        )

    def institution_hold_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>机构持仓数据缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('report_date', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td>{escape(str(x.get('org_type', '')))}</td>"
            f"<td>{int(x.get('holder_count') or 0)}</td><td>{fmt(x.get('hold_value_yi'), ' 亿')}</td>"
            f"<td>{escape(str(x.get('change_label', '')))} {fmt(x.get('change_ratio'), '%')}</td></tr>"
            for i, x in enumerate(rows[:12], 1)
        )

    def financial_rows_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='9'>财报三表摘要缺失</td></tr>"
        return "".join(
            f"<tr><td>{i}</td><td>{escape(str(x.get('report_date', '')))}</td><td>{escape(str(x.get('code', '')))}</td>"
            f"<td><b>{escape(str(x.get('name', '')))}</b></td><td>{fmt(x.get('revenue_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('net_profit_yi'), ' 亿')}</td><td>{fmt(x.get('operating_cashflow_yi'), ' 亿')}</td>"
            f"<td>{fmt(x.get('total_assets_yi'), ' 亿')}</td><td>{int(x.get('balance_items') or 0)}/{int(x.get('income_items') or 0)}/{int(x.get('cashflow_items') or 0)}</td></tr>"
            for i, x in enumerate(rows[:8], 1)
        )

    errors = "; ".join(sanitize_error(x) for x in ctx.errors) if ctx.errors else "无阻断错误"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <script src="{CDN}"></script>
  <style>
    :root{{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--up:#f85149;--down:#3fb950;--blue:#58a6ff;--warn:#d29922}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:PingFang SC,Microsoft YaHei,Arial,sans-serif}}
    .wrap{{max-width:1380px;margin:auto;padding:22px}}.hero{{border:1px solid var(--line);border-radius:8px;padding:20px;background:linear-gradient(135deg,rgba(88,166,255,.18),rgba(248,81,73,.08)),var(--panel)}}
    h1{{margin:0;font-size:26px}}h2{{font-size:17px;margin:0 0 10px}}p{{line-height:1.7;color:var(--muted);margin:0}}.sub{{color:var(--muted);font-size:13px;margin-top:8px}}
    .grid{{display:grid;gap:14px}}.g5{{grid-template-columns:repeat(5,1fr)}}.g4{{grid-template-columns:repeat(4,1fr)}}.g2{{grid-template-columns:repeat(2,1fr)}}.section{{margin-top:16px}}
    .panel,.metric{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:15px}}.metric{{display:flex;flex-direction:column;gap:6px;min-height:96px}}.metric b{{font-size:24px}}.metric span,.metric small{{color:var(--muted)}}
    .up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}.badge{{display:inline-flex;border:1px solid var(--line);border-radius:6px;padding:5px 9px;color:var(--muted);font-size:12px;margin-right:8px}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted)}}.table-wrap{{overflow:auto}}
    canvas{{width:100%!important;height:340px!important}}.audit{{font-size:12px;color:var(--muted);line-height:1.7}}a{{color:#8bb7ff}}@media(max-width:900px){{.g5,.g4,.g2{{grid-template-columns:1fr}}.wrap{{padding:12px}}}}
  </style>
</head>
<body>
<main class="wrap">
  <section class="hero">
    <div><span class="badge">{escape(report_id)}</span><span class="badge">Prompt: {escape(prompt_loaded)}</span><span class="badge">目标: {escape(target)}</span></div>
    <h1>{escape(title)}</h1>
    <p class="sub">该页面已从提示词层上线到可运行 Pipeline。数据底座使用 Sina 指数、同花顺行业/资金、XTick 主数据探测；高阶字段缺失时按审计规则降级，不编造。</p>
  </section>
  <section class="grid g5 section">{index_cards()}</section>
  <section class="grid g5 section">
    <div class="metric"><span>行业宽度</span><b>{width:.1f}%</b><small>按同花顺行业上涨/下跌家数合计</small></div>
    <div class="metric"><span>行业净流合计</span><b class="{cls(flow_total)}">{flow_total:+.2f} 亿</b><small>THS 或东方财富主力净流入代理口径</small></div>
    <div class="metric"><span>行业覆盖</span><b>{len(ctx.industries)}</b><small>行业样本数</small></div>
    <div class="metric"><span>目标成分股</span><b>{len(ctx.target_constituents)}</b><small>{escape(ctx.target_board_code or '未定位板块代码')}</small></div>
    <div class="metric"><span>公告/新闻</span><b>{len(ctx.announcements)}/{len(ctx.xtick_news)}</b><small>CNINFO / XTick News</small></div>
  </section>
  <section class="grid g4 section">{module_cards()}</section>
  <section class="grid g2 section">
    <div class="panel"><h2>涨幅行业 Top10</h2><canvas id="industryChart"></canvas></div>
    <div class="panel"><h2>资金流向 Top/Bottom</h2><canvas id="flowChart"></canvas></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>行业涨幅表</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>行业</th><th>涨跌幅</th><th>净流入</th><th>涨/跌家数</th><th>领涨股</th></tr></thead><tbody>{industry_rows(leaders, 'pct')}</tbody></table></div></div>
    <div class="panel"><h2>资金流向表</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>行业</th><th>涨跌幅</th><th>净流入</th><th>涨/跌家数</th><th>领涨股</th></tr></thead><tbody>{industry_rows(inflows, 'flow')}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>目标成分股资金/估值</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>名称</th><th>涨跌幅</th><th>主力净流</th><th>流通市值</th><th>PE/PB</th><th>状态</th></tr></thead><tbody>{stock_rows(stock_inflows)}</tbody></table></div></div>
    <div class="panel"><h2>ETF 风格与资金</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>ETF</th><th>涨跌幅</th><th>成交额</th><th>主力净流</th></tr></thead><tbody>{etf_rows(etf_leaders)}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>龙虎榜公共兜底</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>日期</th><th>代码</th><th>名称</th><th>涨跌幅</th><th>净买额</th><th>上榜原因</th></tr></thead><tbody>{lhb_rows_html(ctx.lhb_rows)}</tbody></table></div></div>
    <div class="panel"><h2>机构席位与机构买卖</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>日期/周期</th><th>代码</th><th>名称</th><th>买/卖次数</th><th>机构净买</th><th>机构买入</th><th>机构卖出</th></tr></thead><tbody>{lhb_institution_rows_html(ctx.lhb_institution_rows or ctx.lhb_seat_rows)}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>两融余额与交易</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>日期</th><th>两融余额</th><th>融资余额</th><th>融资买入</th><th>融券余额</th><th>维保比例</th></tr></thead><tbody>{margin_rows_html(ctx.margin_rows)}</tbody></table></div></div>
    <div class="panel"><h2>北向成交兜底</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>日期</th><th>通道</th><th>成交额</th><th>成交笔数</th><th>领涨股</th><th>涨跌幅</th></tr></thead><tbody>{northbound_rows_html(ctx.northbound_rows)}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>未来 180 天解禁</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>解禁日</th><th>代码</th><th>名称</th><th>解禁市值</th><th>占比</th><th>股东数</th><th>类型</th></tr></thead><tbody>{unlock_rows_html(ctx.unlock_rows)}</tbody></table></div></div>
    <div class="panel"><h2>增减持结构化记录</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>日期</th><th>代码</th><th>名称</th><th>人员</th><th>变动股数</th><th>原因</th></tr></thead><tbody>{reduction_rows_html(ctx.reduction_rows)}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>机构持仓兜底</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>报告期</th><th>代码</th><th>名称</th><th>机构</th><th>家数</th><th>持仓市值</th><th>变动</th></tr></thead><tbody>{institution_hold_rows_html(ctx.institution_hold_rows)}</tbody></table></div></div>
    <div class="panel"><h2>财报三表摘要</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>报告期</th><th>代码</th><th>名称</th><th>营收</th><th>净利</th><th>经营现金流</th><th>总资产</th><th>三表项数</th></tr></thead><tbody>{financial_rows_html(ctx.financial_rows)}</tbody></table></div></div>
  </section>
  <section class="panel section"><h2>CNINFO 减持公告核验</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>名称</th><th>公告标题</th><th>时间</th></tr></thead><tbody>{reduction_announcement_rows(ctx.reduction_announcements)}</tbody></table></div></section>
  <section class="grid g2 section">
    <div class="panel"><h2>海外/港美/商品映射</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>资产</th><th>代码</th><th>涨跌幅</th><th>时间</th></tr></thead><tbody>{global_rows(ctx.global_quotes)}</tbody></table></div></div>
    <div class="panel"><h2>CNINFO 公告与事件</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>名称</th><th>公告标题</th><th>时间</th></tr></thead><tbody>{event_rows(ctx.announcements)}</tbody></table></div></div>
  </section>
  <section class="grid g2 section">
    <div class="panel"><h2>XTick 短线情绪/资金</h2><p>{escape(xtick_emotion_text)}</p><div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>净流入</th><th>买单数</th><th>卖单数</th></tr></thead><tbody>{"".join(f"<tr><td>{i}</td><td>{escape(str(x.get('code','')))}</td><td class='{cls(x.get('net_inflow_yi'))}'>{fmt(x.get('net_inflow_yi'), ' 亿')}</td><td>{x.get('buy_count')}</td><td>{x.get('sell_count')}</td></tr>" for i, x in enumerate(ctx.xtick_money_top[:8], 1)) or "<tr><td colspan='5'>资金流缺失</td></tr>"}</tbody></table></div></div>
    <div class="panel"><h2>XTick 实时新闻</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>来源</th><th>标题</th><th>链接</th></tr></thead><tbody>{news_rows(ctx.xtick_news)}</tbody></table></div></div>
  </section>
  <section class="panel section"><h2>数据来源与审计</h2><div class="audit">
    <div>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；抓取时间：{escape(ctx.retrieved_at)}</div>
    <div>Prompt 文件：{escape(prompt_file)}</div>
    <div>Provider：Sina 指数/全球行情/财报三表；同花顺行业行情；东方财富全 A/板块/ETF/成分股/主力资金/龙虎榜/机构席位/两融/北向/解禁/增减持/机构持仓；XTick 指数/ETF主数据、情绪、资金、新闻；CNINFO 公告。</div>
    <div>覆盖：XTick index={ctx.xtick_index_count if ctx.xtick_index_count is not None else '缺失'}，ETF master={ctx.xtick_etf_count if ctx.xtick_etf_count is not None else '缺失'}，东财ETF={len(ctx.etfs)}，目标成分股={len(ctx.target_constituents)}，龙虎榜={len(ctx.lhb_rows)}，机构席位={len(ctx.lhb_institution_rows) + len(ctx.lhb_seat_rows)}，两融={len(ctx.margin_rows)}，北向={len(ctx.northbound_rows)}，解禁={len(ctx.unlock_rows)}，机构持仓={len(ctx.institution_hold_rows)}，三表={len(ctx.financial_rows)}，公告={len(ctx.announcements)}，海外行情={len(ctx.global_quotes)}。</div>
    <div>剩余缺口：ETF申赎份额、回购/SHIBOR、质押诉讼结构化字段、收入结构/业务纯度和估值分位仍需 Tushare/Equal Data/交易所专项接口或公告 PDF 解析补强；当前页面会保留 CNINFO/东财/Sina 公共兜底并在空表处显式标记。</div>
    <div>错误记录：{escape(errors)}</div>
    <div>免责声明：基于 AI 分析 + 联网公开信息，仅供研究参考，不构成投资建议。投资有风险，入市需谨慎。</div>
  </div></section>
</main>
<script>
const text='#8b949e'; Chart.defaults.color=text; Chart.defaults.borderColor='rgba(139,148,158,.25)';
const inds={industries_json};
const flows={flow_json};
new Chart(document.getElementById('industryChart'),{{type:'bar',data:{{labels:inds.map(x=>x.name),datasets:[{{label:'涨跌幅%',data:inds.map(x=>x.pct_chg),backgroundColor:inds.map(x=>x.pct_chg>=0?'rgba(248,81,73,.75)':'rgba(63,185,80,.75)')}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});
new Chart(document.getElementById('flowChart'),{{type:'bar',data:{{labels:flows.map(x=>x.name),datasets:[{{label:'净流入(亿)',data:flows.map(x=>x.net_inflow_yi),backgroundColor:flows.map(x=>x.net_inflow_yi>=0?'rgba(248,81,73,.75)':'rgba(63,185,80,.75)')}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});
</script>
<script type="application/json" id="index-data">{escape(indices_json)}</script>
</body>
</html>"""
    return html, title


async def render_expanded_report(report_id: str, target: str) -> tuple[str, str]:
    ctx = await collect_expanded_context(target)
    return render_expanded_report_sync(report_id, target, ctx)
