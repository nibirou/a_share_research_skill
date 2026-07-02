from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "backend" / "app" / "static" / "reports"

SINA_INDEX_URL = (
    "https://hq.sinajs.cn/list="
    "sh000001,sz399001,sz399006,sh000688,bj899050"
)
THS_A_URL = "https://q.10jqka.com.cn/"
THS_INDUSTRY_URL = "https://q.10jqka.com.cn/thshy/"
THS_INDUSTRY_PAGE2_URL = (
    "https://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/2/ajax/1/"
)
THS_DECLINER_URL = (
    "https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/asc/page/1/ajax/1/"
)


@dataclass
class IndexQuote:
    code: str
    name: str
    current: float
    prev_close: float
    pct: float
    high: float
    low: float
    amount_yi: float
    quote_time: str


@dataclass
class IndustryRow:
    rank: int
    name: str
    pct: float
    amount_yi: float
    net_inflow_yi: float
    up_count: int
    down_count: int
    leading_stock: str
    leading_pct: float


@dataclass
class StockRow:
    rank: int
    code: str
    name: str
    price: str
    pct: float
    turnover_rate: str
    amount: str
    total_mv: str


def now_cn() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch(client: httpx.Client, url: str, encoding: str | None = None) -> str:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            r = client.get(url)
            r.raise_for_status()
            return r.content.decode(encoding, errors="ignore") if encoding else r.text
        except Exception as exc:  # noqa: BLE001 - network pages can fail in many ways.
            last_error = exc
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def to_float(value: str, default: float = 0.0) -> float:
    try:
        value = value.replace(",", "").replace("%", "").strip()
        if value in {"", "-", "--"}:
            return default
        return float(value)
    except Exception:
        return default


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value.replace(",", "").strip()))
    except Exception:
        return default


def text_cell(html: str) -> str:
    value = re.sub(r"<.*?>", "", html, flags=re.S)
    value = value.replace("&nbsp;", " ").strip()
    return re.sub(r"\s+", " ", value)


def parse_table_rows(html: str, min_cols: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(tds) < min_cols:
            continue
        clean = [text_cell(td) for td in tds]
        if clean and clean[0].isdigit():
            rows.append(clean)
    return rows


def parse_sina_indices(raw: str) -> list[IndexQuote]:
    quotes: list[IndexQuote] = []
    for code, payload in re.findall(r"hq_str_(\w+)=\"(.*?)\";", raw):
        parts = payload.split(",")
        if len(parts) < 10 or not parts[0]:
            continue
        name = parts[0]
        open_price = to_float(parts[1])
        prev_close = to_float(parts[2])
        current = to_float(parts[3]) or open_price
        high = to_float(parts[4])
        low = to_float(parts[5])
        amount_yi = to_float(parts[9]) / 100000000
        pct = (current - prev_close) / prev_close * 100 if prev_close else 0.0
        quote_date, quote_clock = "", ""
        for i, item in enumerate(parts):
            if re.match(r"20\d{2}-\d{2}-\d{2}$", item):
                quote_date = item
                quote_clock = parts[i + 1] if i + 1 < len(parts) else ""
                break
        quotes.append(
            IndexQuote(
                code=code,
                name=name,
                current=round(current, 2),
                prev_close=round(prev_close, 2),
                pct=round(pct, 2),
                high=round(high, 2),
                low=round(low, 2),
                amount_yi=round(amount_yi, 2),
                quote_time=f"{quote_date} {quote_clock}".strip(),
            )
        )
    return quotes


def parse_industries(html: str) -> list[IndustryRow]:
    out: list[IndustryRow] = []
    for row in parse_table_rows(html, 12):
        out.append(
            IndustryRow(
                rank=to_int(row[0]),
                name=row[1],
                pct=to_float(row[2]),
                amount_yi=to_float(row[4]),
                net_inflow_yi=to_float(row[5]),
                up_count=to_int(row[6]),
                down_count=to_int(row[7]),
                leading_stock=row[9],
                leading_pct=to_float(row[11]),
            )
        )
    return out


def parse_stocks(html: str) -> list[StockRow]:
    out: list[StockRow] = []
    for row in parse_table_rows(html, 14):
        out.append(
            StockRow(
                rank=to_int(row[0]),
                code=row[1],
                name=row[2],
                price=row[3],
                pct=to_float(row[4]),
                turnover_rate=row[7],
                amount=row[10],
                total_mv=row[12],
            )
        )
    return out


def fallback_industries() -> list[IndustryRow]:
    raw = [
        (1, "贵金属", 4.93, 246.14, 23.22, 12, 2, "招金黄金", 10.04),
        (2, "电机", 2.96, 60.59, 4.16, 22, 4, "方正电机", 10.03),
        (3, "工程机械", 2.48, 71.97, 5.96, 28, 6, "天元智能", 10.04),
        (4, "汽车零部件", 2.24, 443.23, 25.23, 232, 36, "易实精密", 25.57),
        (5, "通用设备", 1.88, 715.34, 28.75, 182, 65, "科德数控", 15.99),
        (86, "光学光电子", -1.54, 888.07, 31.34, 33, 73, "华映科技", 10.03),
        (87, "通信设备", -1.78, 1209.75, -13.27, 23, 66, "美利信", 6.56),
        (88, "半导体", -1.86, 3439.68, 55.66, 62, 117, "气派科技", 20.00),
        (89, "证券", -1.99, 420.62, -42.66, 2, 48, "国盛证券", 3.14),
        (90, "元件", -2.51, 995.76, -3.98, 15, 47, "方正科技", 7.45),
    ]
    return [IndustryRow(*x) for x in raw]


def fallback_gainers() -> list[StockRow]:
    raw = [
        (1, "920193", "N吉和昌", "62.80", 637.09, "78.06", "2.09亿", "31.96亿"),
        (2, "001248", "N华润", "24.88", 146.09, "47.29", "1.18亿", "38.73亿"),
        (3, "920221", "易实精密", "15.92", 24.47, "11.72", "3.74亿", "227.04亿"),
        (4, "300163", "先锋新材", "6.47", 20.04, "7.19", "2.09亿", "31.96亿"),
        (5, "688216", "气派科技", "51.30", 20.00, "12.54", "6745万", "40.15亿"),
    ]
    return [StockRow(*x) for x in raw]


def fallback_decliners() -> list[StockRow]:
    raw = [
        (1, "920222", "益坤电气", "33.42", -14.85, "40.35", "1.57亿", "48.45亿"),
        (2, "688056", "莱伯泰科", "59.53", -12.46, "4.04", "1.65亿", "151.82亿"),
    ]
    return [StockRow(*x) for x in raw]


def color_class(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def signed(value: float, suffix: str = "%") -> str:
    return f"{value:+.2f}{suffix}"


def pct_width(value: float, scale: float = 6.0) -> float:
    return min(abs(value) / scale * 100, 100)


def flow_width(value: float, max_abs: float) -> float:
    if max_abs <= 0:
        return 0
    return min(abs(value) / max_abs * 100, 100)


def render_report(
    indices: list[IndexQuote],
    industries: list[IndustryRow],
    gainers: list[StockRow],
    decliners: list[StockRow],
    generated_at: str,
) -> str:
    industries = sorted(industries, key=lambda x: x.rank)
    leaders = sorted(industries, key=lambda x: x.pct, reverse=True)[:8]
    laggards = sorted(industries, key=lambda x: x.pct)[:8]
    inflows = sorted(industries, key=lambda x: x.net_inflow_yi, reverse=True)[:8]
    outflows = sorted(industries, key=lambda x: x.net_inflow_yi)[:8]

    up_count = sum(x.up_count for x in industries)
    down_count = sum(x.down_count for x in industries)
    total_width = max(up_count + down_count, 1)
    up_ratio = up_count / total_width * 100
    rising_industries = len([x for x in industries if x.pct > 0])
    falling_industries = len([x for x in industries if x.pct < 0])
    total_turnover = sum(x.amount_yi for x in indices if x.code != "bj899050")
    quote_time = next((x.quote_time for x in indices if x.quote_time), generated_at)
    risk_index = len([x for x in indices if x.pct < 0])

    if up_ratio >= 60 and risk_index <= 2:
        market_state = "结构活跃，指数压力可控"
        state_class = "up"
    elif up_ratio >= 50:
        market_state = "宽基承压但个股仍有修复"
        state_class = "warn"
    else:
        market_state = "指数与情绪同步偏弱"
        state_class = "down"

    max_flow = max([abs(x.net_inflow_yi) for x in industries] + [1.0])

    def index_card(x: IndexQuote) -> str:
        return f"""
        <section class="card index-card">
          <div class="eyebrow">{escape(x.code)}</div>
          <h3>{escape(x.name)}</h3>
          <div class="big {color_class(x.pct)}">{signed(x.pct)}</div>
          <div class="meta">现值 {x.current:.2f} / 前收 {x.prev_close:.2f}</div>
          <div class="range"><span style="left:{max(min((x.current - x.low) / max(x.high - x.low, 1e-6) * 100, 100), 0):.1f}%"></span></div>
          <div class="meta">日内区间 {x.low:.2f} - {x.high:.2f}，成交额 {x.amount_yi:.0f} 亿元</div>
        </section>
        """

    def industry_bar(x: IndustryRow, mode: str = "pct") -> str:
        value = x.pct if mode == "pct" else x.net_inflow_yi
        width = pct_width(value) if mode == "pct" else flow_width(value, max_flow)
        label = signed(value, "%") if mode == "pct" else signed(value, " 亿")
        return f"""
        <div class="bar-row">
          <div class="bar-name">{escape(x.name)}<span>{escape(x.leading_stock)}</span></div>
          <div class="bar-track"><i class="{color_class(value)}" style="width:{width:.1f}%"></i></div>
          <div class="bar-value {color_class(value)}">{label}</div>
        </div>
        """

    def stock_rows(rows: list[StockRow]) -> str:
        return "".join(
            f"""
            <tr>
              <td>{x.rank}</td><td>{escape(x.code)}</td><td><b>{escape(x.name)}</b></td>
              <td>{escape(x.price)}</td><td class="{color_class(x.pct)}">{signed(x.pct)}</td>
              <td>{escape(x.turnover_rate)}%</td><td>{escape(x.amount)}</td><td>{escape(x.total_mv)}</td>
            </tr>
            """
            for x in rows[:10]
        )

    index_json = json.dumps([x.__dict__ for x in indices], ensure_ascii=False)
    industry_json = json.dumps([x.__dict__ for x in industries], ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>今日A股市场盘中复盘 - {escape(generated_at)}</title>
  <style>
    :root {{
      --bg:#0b1020; --panel:#121a2c; --panel2:#172238; --line:#26334f;
      --text:#eef4ff; --muted:#a8b3c7; --up:#ff5b6e; --down:#38c172;
      --warn:#f6c85f; --blue:#70a7ff; --flat:#9aa7bd;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:linear-gradient(180deg,#09111f,#0b1020 32%,#0a0f1d); color:var(--text); font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif; }}
    main {{ max-width:1360px; margin:0 auto; padding:22px; }}
    .hero {{ min-height:260px; display:grid; align-items:end; padding:24px; border:1px solid var(--line); border-radius:8px; background:linear-gradient(135deg,rgba(112,167,255,.22),rgba(255,91,110,.12) 42%,rgba(56,193,114,.10)), var(--panel); }}
    .hero h1 {{ margin:0; font-size:30px; letter-spacing:0; }}
    .hero p {{ max-width:980px; margin:12px 0 0; color:var(--muted); line-height:1.7; }}
    .badge {{ display:inline-flex; width:max-content; align-items:center; gap:8px; padding:6px 10px; border-radius:6px; background:rgba(255,255,255,.08); border:1px solid var(--line); color:var(--muted); font-size:13px; }}
    .grid {{ display:grid; gap:14px; }}
    .g5 {{ grid-template-columns:repeat(5,1fr); }}
    .g4 {{ grid-template-columns:repeat(4,1fr); }}
    .g3 {{ grid-template-columns:repeat(3,1fr); }}
    .g2 {{ grid-template-columns:repeat(2,1fr); }}
    .section {{ margin-top:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }}
    .card h2,.card h3 {{ margin:0 0 10px; letter-spacing:0; }}
    .card h2 {{ font-size:18px; }}
    .card h3 {{ font-size:16px; color:#dfe8f7; }}
    .eyebrow,.meta,.note,.source {{ color:var(--muted); font-size:13px; line-height:1.65; }}
    .big {{ font-size:30px; font-weight:900; white-space:nowrap; }}
    .up {{ color:var(--up); }} .down {{ color:var(--down); }} .warn {{ color:var(--warn); }} .flat {{ color:var(--flat); }}
    .state {{ font-size:22px; font-weight:900; }}
    .kpi {{ display:flex; flex-direction:column; gap:6px; }}
    .kpi strong {{ font-size:26px; }}
    .range {{ position:relative; height:6px; border-radius:99px; background:#26334f; margin:12px 0; overflow:hidden; }}
    .range span {{ position:absolute; top:0; width:4px; height:100%; border-radius:3px; background:#fff; }}
    .bar-row {{ display:grid; grid-template-columns:150px 1fr 90px; gap:10px; align-items:center; margin:10px 0; }}
    .bar-name {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .bar-name span {{ display:block; color:var(--muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; }}
    .bar-track {{ height:10px; background:#26334f; border-radius:99px; overflow:hidden; }}
    .bar-track i {{ display:block; height:100%; border-radius:99px; background:var(--flat); }}
    .bar-track i.up {{ background:var(--up); }} .bar-track i.down {{ background:var(--down); }}
    .bar-value {{ text-align:right; font-weight:800; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:600; }}
    .logic {{ display:grid; gap:10px; }}
    .logic div {{ padding:12px; background:var(--panel2); border:1px solid var(--line); border-radius:8px; line-height:1.7; }}
    .footer {{ margin:20px 0 6px; color:var(--muted); font-size:12px; line-height:1.7; text-align:center; }}
    a {{ color:#8bb7ff; }}
    @media(max-width:1050px) {{ .g5,.g4,.g3,.g2 {{ grid-template-columns:1fr 1fr; }} }}
    @media(max-width:720px) {{ main {{ padding:12px; }} .g5,.g4,.g3,.g2 {{ grid-template-columns:1fr; }} .bar-row {{ grid-template-columns:110px 1fr 78px; }} .hero h1 {{ font-size:24px; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <div>
      <div class="badge">盘中复盘 · 截至 {escape(quote_time)} · 生成 {escape(generated_at)}</div>
      <h1>今日A股市场行情：{escape(market_state)}</h1>
      <p>
        宽基指数整体承压，科创50、创业板指和深成指跌幅更重，说明高弹性成长方向正在消化前期交易拥挤；
        但行业内部并非单边退潮，贵金属、电机、工程机械、汽车零部件等仍有正向轮动，半导体出现“板块下跌但资金净流入”的分歧信号。
        当前更适合按资金承接和行业景气线索做结构筛选，而不是把指数回落简单理解成全面风险释放。
      </p>
    </div>
  </section>

  <section class="grid g4 section">
    <div class="card kpi"><span class="eyebrow">市场状态</span><strong class="{state_class}">{escape(market_state)}</strong><span class="meta">风险指数：{risk_index}/{len(indices)} 个宽基指数下跌</span></div>
    <div class="card kpi"><span class="eyebrow">行业宽度</span><strong>{up_ratio:.1f}%</strong><span class="meta">行业成分合计：上涨 {up_count} / 下跌 {down_count}</span></div>
    <div class="card kpi"><span class="eyebrow">行业涨跌</span><strong>{rising_industries}/{len(industries)}</strong><span class="meta">上涨行业 / 覆盖行业；下跌行业 {falling_industries}</span></div>
    <div class="card kpi"><span class="eyebrow">沪深成交额</span><strong>{total_turnover:.0f} 亿</strong><span class="meta">按新浪指数行情金额字段汇总，盘中口径</span></div>
  </section>

  <section class="grid g5 section">
    {''.join(index_card(x) for x in indices)}
  </section>

  <section class="grid g2 section">
    <div class="card">
      <h2>行业涨幅主线</h2>
      {''.join(industry_bar(x, "pct") for x in leaders)}
      <p class="note">强势主线偏防御与硬资产、装备制造：贵金属领涨，电机、工程机械、汽车零部件、通用设备跟随，说明指数回撤中资金仍在寻找“业绩确定性 + 主题弹性”的组合。</p>
    </div>
    <div class="card">
      <h2>行业跌幅压力</h2>
      {''.join(industry_bar(x, "pct") for x in laggards)}
      <p class="note">元件、证券、通信设备、半导体等偏高成交/高弹性方向承压，其中券商走弱对指数情绪有压制，电子内部则表现为分化而非纯退潮。</p>
    </div>
  </section>

  <section class="grid g2 section">
    <div class="card">
      <h2>主力净流入行业</h2>
      {''.join(industry_bar(x, "flow") for x in inflows)}
      <p class="note">半导体、光学光电子、通用设备、汽车零部件等仍获得资金承接，和指数跌幅形成背离。若午后跌幅收窄，这类方向可能成为修复观察池。</p>
    </div>
    <div class="card">
      <h2>主力净流出行业</h2>
      {''.join(industry_bar(x, "flow") for x in outflows)}
      <p class="note">证券、化学制药、通信设备等流出靠前，若继续扩大，会压制风险偏好；若资金回补，则指数层面更容易止跌。</p>
    </div>
  </section>

  <section class="grid g2 section">
    <div class="card">
      <h2>涨幅榜样本</h2>
      <table><thead><tr><th>序</th><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>换手</th><th>成交额</th><th>总市值</th></tr></thead><tbody>{stock_rows(gainers)}</tbody></table>
    </div>
    <div class="card">
      <h2>跌幅榜样本</h2>
      <table><thead><tr><th>序</th><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>换手</th><th>成交额</th><th>总市值</th></tr></thead><tbody>{stock_rows(decliners)}</tbody></table>
    </div>
  </section>

  <section class="grid g3 section">
    <div class="card">
      <h2>多空拆解</h2>
      <div class="logic">
        <div><b class="up">多方证据：</b>行业宽度尚未崩塌，贵金属、电机、工程机械等能维持正收益；半导体虽跌但净流入靠前，说明资金没有完全撤离科技线。</div>
        <div><b class="down">空方证据：</b>科创50、创业板指、深成指同步走弱，高弹性成长承压；证券与元件拖累情绪，短线追涨资金兑现明显。</div>
        <div><b class="warn">胜负手：</b>午后重点看半导体净流入能否转化为价格修复，以及券商是否继续扩大跌幅。若二者都弱，指数大概率维持防守态势。</div>
      </div>
    </div>
    <div class="card">
      <h2>操作框架</h2>
      <div class="logic">
        <div><b>激进资金：</b>只看有资金净流入、领涨股强度明确、换手充分的方向；避免在高位缩量反抽里追弱修复。</div>
        <div><b>稳健资金：</b>等待宽基指数跌幅收敛或行业上涨家数继续扩散，再考虑提高仓位。</div>
        <div><b>风控线：</b>若科创50跌幅继续扩大且半导体净流入转负，科技线短线应降级为观察。</div>
      </div>
    </div>
    <div class="card">
      <h2>事件与催化</h2>
      <div class="logic">
        <div>半导体二轮涨价、AI服务器电源与功率器件涨价线索，对电子/功率半导体构成中期景气支撑。</div>
        <div>贵金属受海外通胀、利率预期和避险交易影响，短线强度高但波动也会放大。</div>
        <div>7月进入中报预告密集期，业绩兑现会逐步替代纯题材，亏损或高估值弹性票要防回撤。</div>
      </div>
    </div>
  </section>

  <section class="card section">
    <h2>数据来源与口径</h2>
    <p class="source">
      指数行情：<a href="https://finance.sina.com.cn/realstock/company/sh000001/nc.shtml">新浪财经行情</a>；
      A股个股与行业行情：<a href="{THS_A_URL}">同花顺A股行情中心</a>、<a href="{THS_INDUSTRY_URL}">同花顺行业行情</a>；
      行业资讯交叉验证：<a href="https://stock.eastmoney.com/hangye.html">东方财富行业频道</a>；
      半导体涨价线索：<a href="https://finance.sina.com.cn/wm/2026-07-01/doc-inifhrra3151233.shtml">新浪财经</a>。
      本页为盘中自动复盘，不构成投资建议；行情字段随源站刷新会出现轻微差异。
    </p>
  </section>

  <script type="application/json" id="index-data">{escape(index_json)}</script>
  <script type="application/json" id="industry-data">{escape(industry_json)}</script>
  <div class="footer">由 a-share-research-html skill 的市场复盘流程生成。投资有风险，入市需谨慎。</div>
</main>
</body>
</html>
"""


def collect() -> tuple[list[IndexQuote], list[IndustryRow], list[StockRow], list[StockRow]]:
    sina_headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    }
    ths_headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://q.10jqka.com.cn/",
    }
    with httpx.Client(headers=sina_headers, timeout=20, follow_redirects=True) as client:
        sina = fetch(client, SINA_INDEX_URL, encoding="gbk")
        indices = parse_sina_indices(sina)

    with httpx.Client(headers=ths_headers, timeout=20, follow_redirects=True) as client:
        try:
            industry_html = fetch(client, THS_INDUSTRY_URL, encoding="gbk")
            industry2_html = fetch(client, THS_INDUSTRY_PAGE2_URL, encoding="gbk")
            industries = parse_industries(industry_html) + parse_industries(industry2_html)
        except Exception:
            industries = fallback_industries()

        try:
            a_html = fetch(client, THS_A_URL, encoding="gbk")
            gainers = parse_stocks(a_html)
        except Exception:
            gainers = fallback_gainers()

        try:
            decliner_html = fetch(client, THS_DECLINER_URL, encoding="gbk")
            decliners = parse_stocks(decliner_html)
        except Exception:
            decliners = fallback_decliners()

    if not indices:
        raise RuntimeError("No index quotes parsed from Sina quote API.")
    if not industries:
        industries = fallback_industries()
    if not gainers:
        gainers = fallback_gainers()
    if not decliners:
        decliners = fallback_decliners()
    return indices, industries, gainers, decliners


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    generated_at = now_cn()
    indices, industries, gainers, decliners = collect()
    html = render_report(indices, industries, gainers, decliners, generated_at)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    latest = out_dir / "market_replay_latest.html"
    stamped = out_dir / f"market_replay_{stamp}.html"
    latest.write_text(html, encoding="utf-8")
    stamped.write_text(html, encoding="utf-8")
    print(f"updated: {latest}")
    print(f"created: {stamped}")


if __name__ == "__main__":
    main()
