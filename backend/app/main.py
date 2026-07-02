from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings


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
ReportType = Literal["market_replay", "quant_factor", "sector_stock", "agent_debate"]


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


def tag(label: str) -> str:
    colors = {"超预期":"red","符合预期":"orange","不及预期":"green","利多":"red","利空":"green","中性":"blue","冰点":"blue","低迷":"green","活跃":"orange","沸点":"red","背离":"red","共振":"blue"}
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
            MarketEvent(f"{sector}供需出清成为核心叙事", "利多", "正在定价", "Demo", "估值修复触发"),
            MarketEvent("海外贸易壁垒与价格下行仍是风险", "利空", "未充分定价", "Demo", "压制盈利弹性"),
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
    async def run(self, context: dict) -> list[AgentFinding]:
        # OPENAI_API_KEY 存在时可扩展为真实 LLM 协同；默认启用可解释规则智能体，保证离线可运行。
        return [
            self.macro(context),
            self.capital(context),
            self.quant(context),
            self.industry(context),
            self.risk(context),
        ]

    def macro(self, ctx: dict) -> AgentFinding:
        events = ctx.get("events") or ctx.get("market", {}).get("events") or ctx.get("quant", {}).get("events") or []
        fav = sum(1 for e in events if e.get("impact") == "利多")
        neg = sum(1 for e in events if e.get("impact") == "利空")
        return AgentFinding("宏观策略", "政策预期托底，但需要资金确认。", clamp(50 + 10*(fav-neg)), [f"利多{fav}条/利空{neg}条"], ["政策落地慢于预期"])

    def capital(self, ctx: dict) -> AgentFinding:
        idx = ctx.get("market", {}).get("indices", [])
        flow = sum(float(x.get("main_net_inflow", 0)) for x in idx)
        return AgentFinding("资金流", "指数涨但主力净流出，诱多背离需防。", clamp(50 + flow/20), [f"主力合计{flow:.2f}亿"], ["放量不延续"])

    def quant(self, ctx: dict) -> AgentFinding:
        q = ctx.get("quant", {})
        c = float(q.get("composite", 50))
        return AgentFinding("技术量化", "综合因子冰点，反弹需右侧确认。", c, [f"综合因子{c}"], ["冰点钝化"])

    def industry(self, ctx: dict) -> AgentFinding:
        leaders = ctx.get("market", {}).get("leaders", [])
        theme = leaders[0]["name"] if leaders else "核心主线"
        return AgentFinding("行业轮动", f"领涨集中于{theme}，主线比杂乱轮动更健康。", 65, ["领涨板块相似度较高"], ["单日高潮后分歧"])

    def risk(self, ctx: dict) -> AgentFinding:
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
    rows = []
    for st in ss.stocks:
        mode, score, decision = classify_stock(st)
        rows.append({"stock": st, "mode": mode, "score": score, "decision": decision})
    rows.sort(key=lambda x: x["score"], reverse=True)
    leader = rows[0]["stock"].name if rows else "无"
    positive = len([r for r in rows if (r["stock"].flow_3d or 0) > 0])
    allpos = len([r for r in rows if all(v is not None and v > 0 for v in [r["stock"].flow_3d, r["stock"].flow_5d, r["stock"].flow_20d])])
    stage = "吸筹初期" if positive > 0 else "分歧期/数据待验证"
    cards, table = "", ""
    for i, r in enumerate(rows, 1):
        s, mode, score, decision = r["stock"], r["mode"], r["score"], r["decision"]
        sttag = " " + tag("*ST/ST风险") if s.is_st else ""
        cards += f"""<div class="stock {'best' if score>=70 and not s.is_st else ''}"><h2>排名{i} · {escape(s.name)}（{escape(s.code)}）· 流通市值{s.float_mv}亿 {sttag}</h2><div class="kv"><span class="pill">资金模式：{escape(mode)}</span><span class="pill">资金质量分：{score}/100</span><span class="pill">3日 {s.flow_3d if s.flow_3d is not None else '-'}</span><span class="pill">5日 {s.flow_5d if s.flow_5d is not None else '-'}</span><span class="pill">20日 {s.flow_20d if s.flow_20d is not None else '-'}</span></div><table><tbody><tr><td>▶ 资金判断</td><td>{'资金数据缺失，暂按低置信度处理；接入真实超资后自动重排。' if s.flow_3d is None else '三周期资金显示'+escape(mode)}</td></tr><tr><td>▶ 基本面亮点</td><td>{escape(s.fundamentals)}；光伏设备链看盈利修复、订单和出海。</td></tr><tr><td>▶ 产业链定位</td><td>{escape(s.industry_position)}；需用年报营收结构确认。</td></tr><tr><td>▶ 交叉概念关联</td><td>新能源 + 储能/逆变器/设备国产替代，评级：{escape(s.concept_rating)}</td></tr><tr><td>▶ 短期判断</td><td>{escape(decision)}：资金置信度{'不足' if s.flow_3d is None else '可跟踪'}。</td></tr><tr><td>▶ 半年预期</td><td>催化：业绩预告、订单、政策；风险：价格战、海外壁垒、减持解禁。</td></tr>{'<tr><td>⚠️ 特有风险</td><td>风险警示/退市风险，推荐池排除。</td></tr>' if s.is_st else ''}</tbody></table></div>"""
        table += f"<tr><td>{i}</td><td>{escape(s.code)}</td><td>{escape(s.name)}</td><td>{escape(mode)}</td><td>{s.flow_3d if s.flow_3d is not None else '-'}</td><td>{s.flow_5d if s.flow_5d is not None else '-'}</td><td>{s.flow_20d if s.flow_20d is not None else '-'}</td><td>{score}</td><td>{escape(s.concept_rating)}</td><td>{escape(decision)}</td></tr>"
    recs = [r for r in rows if not r["stock"].is_st][:5]
    rec_html = "".join(f"<div class='stock {'best' if i==1 else ''}'><h2>推荐 #{i}：{escape(r['stock'].name)}（{escape(r['stock'].code)}）</h2><div class='kv'>{tag('首选' if i==1 else '次选' if i<=3 else '观察')}<span class='pill'>资金分 {r['score']}</span><span class='pill'>{escape(r['mode'])}</span></div><div class='sub'>资金面候选 + 新能源交叉主线 + 供需出清预期；真实资金缺失时仅作观察池。</div><table><tbody><tr><td>半年预期</td><td>看估值修复弹性；催化为业绩和订单；最大风险为价格战与贸易壁垒。</td></tr><tr><td>止损/止盈</td><td>止损看20日线或前低；止盈看前高与放量滞涨。</td></tr><tr><td>差异化</td><td>相对ST标的风险更低。</td></tr></tbody></table></div>" for i, r in enumerate(recs,1))
    labels = [r["stock"].name for r in rows]; values = [r["stock"].flow_3d or 0 for r in rows]
    html = head(f"{ss.sector}板块个股分析")
    html += f"""
<div class="banner section"><h1>{escape(ss.sector)}板块资金全景</h1><div class="grid g4 section"><div class="card"><div class="num">{positive}/{len(rows)}</div><div class="mini">资金净流入家数</div></div><div class="card"><div class="num">{escape(leader)}</div><div class="mini">板块资金龙头</div></div><div class="card"><div class="num">{allpos}</div><div class="mini">三周期全正</div></div><div class="card"><div class="num">{escape(stage)}</div><div class="mini">阶段标签</div></div></div><div class="sub section">当前样例资金缺失，系统先生成低置信度观察版；接入真实数据后自动重排。</div></div>
<div class="card section"><h2>个股资金排名柱状图</h2><div class="chart"><canvas id="stockFlow"></canvas></div></div>
<div class="section"><h2>所有个股逐一深度分析</h2>{cards}</div>
<div class="card section"><h2>资金模式分类汇总表</h2><table><thead><tr><th>排名</th><th>代码</th><th>名称</th><th>模式</th><th>3日</th><th>5日</th><th>20日</th><th>资金分</th><th>概念</th><th>判断</th></tr></thead><tbody>{table}</tbody></table></div>
<div class="card section"><h2>板块半年预期路线图</h2><div class="timeline"><div class="node"><b>当月 · 行业价格数据</b> {tag('中性')}<div class="sub">验证硅料/组件价格是否企稳。</div></div><div class="node"><b>下月 · 业绩预告窗口</b> {tag('利多')}<div class="sub">筛选盈利率先修复个股。</div></div><div class="node"><b>3个月内 · 产能出清</b> {tag('中性')}<div class="sub">关注落后产能退出。</div></div></div></div>
<div class="section"><h2>精选推荐 3-5 只</h2>{rec_html}</div>
<div class="card risk section"><h2>风险汇总</h2><div class="grid g4"><div class="card"><b>价格战</b><div class="sub">盈利修复被降价抵消。</div></div><div class="card"><b>海外壁垒</b><div class="sub">关税与反规避风险。</div></div><div class="card"><b>ST风险</b><div class="sub">风险警示股排除推荐。</div></div><div class="card"><b>资金缺失</b><div class="sub">需接入真实超资重排。</div></div></div></div>
"""
    script = f"""<script>const text='#8b949e';Chart.defaults.color=text;const labels={j(labels)},data={j(values)};new Chart(document.getElementById('stockFlow'),{{type:'bar',data:{{labels,datasets:[{{label:'超资入场3D',data,backgroundColor:data.map(x=>x>=0?'rgba(248,81,73,.78)':'rgba(63,185,80,.78)')}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}}}});</script>"""
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
    def __init__(self):
        self.data = DataHub()
        self.search = SearchHub()
        self.agents = AgentTeam()
        settings.report_path.mkdir(parents=True, exist_ok=True)

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
            ev = await self.search.search([f"{sector} 行业 价格 供需 产能 近30天", f"{sector} 上市公司 公告 业绩 订单 定增 减持", f"{sector} 机构研报 评级 近1月"], 30, 5)
            if ev: ss.events = ev
            f = await self.agents.run({"sector": json.loads(j(ss)), "events": [asdict(e) for e in ss.events]})
            html, title = render_sector(ss, f), f"{sector}板块个股分析"
        else:
            m, q = await self.data.market_snapshot(), await self.data.quant_snapshot()
            f = await self.agents.run({"market": json.loads(j(m)), "quant": json.loads(j(q))})
            html, title = render_agents(f), "A股多智能体投研报告"
        fn = self._save(report_type, html)
        return {"report_type": report_type, "filename": fn, "url": f"/reports/{fn}", "title": title, "generated_at": now_str()}

    async def generate_all(self, sector: str = "光伏设备") -> list[dict]:
        out = []
        for rt in ["market_replay", "quant_factor", "sector_stock", "agent_debate"]:
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
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A股投研页面中心</title><style>body{{margin:0;background:#0d1117;color:#e6edf3;font-family:PingFang SC,Microsoft YaHei,Arial,sans-serif}}.wrap{{max-width:1200px;margin:auto;padding:24px}}.top{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}}.btn{{background:#238636;color:#fff;border-radius:10px;padding:10px 14px;text-decoration:none}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:18px}}.card{{display:flex;flex-direction:column;gap:8px;color:#e6edf3;text-decoration:none;background:#161b22;border:1px solid #30363d;border-radius:16px;padding:16px}}span,p{{color:#8b949e}}</style></head><body><div class="wrap"><div class="top"><div><h1>A股投研 HTML 页面中心</h1><p>行情复盘｜量化因子｜板块个股｜多智能体投研</p></div><a class="btn" href="/api/reports/refresh-all">刷新全部页面</a></div><div class="grid">{cards}</div></div></body></html>"""

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
async def generate(report_type: ReportType, sector: str = Query("光伏设备")):
    return await Pipeline().generate(report_type, sector)

@app.get("/api/reports/refresh-all")
async def refresh_all(sector: str = Query("光伏设备")):
    return await Pipeline().generate_all(sector)

@app.get("/api/health")
async def health():
    return {"ok": True, "provider": settings.data_provider, "report_dir": str(settings.report_path)}
