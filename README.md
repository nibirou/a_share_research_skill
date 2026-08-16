# A-Share Research HTML Skill

一个可运行的 A 股综合投研 Skill 工程骨架：行情数据获取、联网事件搜索、多智能体分析、HTML 页面生成、FastAPI 后端和 Vue 前端页面中心。

## 快速启动

```bash
cd a_share_research_skill
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_once.py --all
uvicorn backend.app.main:app --host 0.0.0.0 --port 8787 --reload
```

打开 `http://127.0.0.1:8787`。

## Skill 资料结构

- `skill/SKILL.md`：轻量入口与报告路由。
- `skill/references/data_sources.md`：行情、资金、财务、公告、新闻数据源分层与审计规则。
- `skill/references/agent_team.md`：多智能体投研角色、辩论流程与评分规则。
- `skill/references/html_prompt_library.md`：HTML 功能提示词索引，指向 Skill 内置提示词文件。
- `skill/references/html_prompts/`：安装后可独立使用的 HTML 页面长提示词。
- `skill/references/report_data_matrix.md`：每个 HTML 页面需要的数据、主渠道、备用渠道和缺口矩阵。
- `docs/Prompt/HTMLFunctionPrompts/`：每个 HTML 页面功能一份独立长提示词 md 文件。
- `docs/Prompt/FunctionPrompt.ipynb`：原始 notebook 提示词模板，保留作为对照来源。

## 当前可运行报告类型

- `market_replay`：行情多维度复盘 HTML
- `quant_factor`：大盘量化因子 HTML
- `sector_stock`：板块个股逐一分析 HTML
- `agent_debate`：多智能体投研 HTML

## 本地测试

先安装依赖：

```bash
python -m pip install -r requirements.txt
```

检查 Python 语法：

```bash
python -m py_compile backend/app/main.py scripts/generate_once.py
```

生成单个页面：

```bash
python scripts/generate_once.py --report market_replay
python scripts/generate_once.py --report sector_stock --sector 光伏设备
```

生成当前已接入后端的全部页面：

```bash
python scripts/generate_once.py --all
```

启动页面中心：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8787 --reload
```

打开 `http://127.0.0.1:8787` 查看报告列表。

校验 Skill 结构时，如果 Windows 控制台遇到编码问题，先启用 UTF-8：

```powershell
$env:PYTHONUTF8='1'
python C:\Users\74142\.codex\skills\.system\skill-creator\scripts\quick_validate.py skill
```

## 已上线扩展报告类型

提示词库已补充并接入后端 `Pipeline`：板块资金轮动、聪明资金攻击面、板块估值诊股、趋势共振、自选股终端、指数/ETF 监控、流动性仪表盘、财报催化日历、单股事件风险、产业链图谱、海外映射等功能。CLI、FastAPI 和前端按钮均可直接生成这些 HTML 页面。

新增可运行 `report_type`：

- `sector_flow_rotation`
- `smart_money_clusters`
- `sector_valuation_diagnosis`
- `trend_resonance`
- `watchlist_terminal`
- `index_etf_monitor`
- `liquidity_dashboard`
- `earnings_catalyst_calendar`
- `single_stock_event_risk`
- `industry_chain_map`
- `global_mapping`

## 可选环境变量

- `DATA_PROVIDER=demo|akshare`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `TAVILY_API_KEY` / `SERPER_API_KEY` / `SEARXNG_URL`
- `TUSHARE_TOKEN` / `XTICK_TOKEN`

## 数据源扩展

本项目已增加统一数据源注册表与探测脚本：

```powershell
python scripts\probe_data_sources.py
python scripts\probe_data_sources.py --samples
```

当前纳入的渠道：

- XTick：本地目录 `xtick/`，配置文件 `xtick/scripts/Config.py`，优先读取 `XTICK_TOKEN`。
- Sina：A 股指数、港美/全球/汇率/商品行情片段，以及 A 股资产负债表、利润表、现金流量表三表摘要。
- 同花顺：行业涨跌幅、行业成交额、行业净流入、行业上涨/下跌家数、行业详情页成分股备用。
- Eastmoney：全 A 行情、行业/概念排行、ETF 排行、板块代码搜索和成分股；另接入 datacenter 公共兜底，覆盖龙虎榜、机构席位、两融、北向成交、限售解禁、高管增减持、基金/QFII/社保/券商/保险/信托持仓；`clist` 和 datacenter 均有本地缓存。
- 交易所官方：SSE/SZSE 融资融券汇总兜底，SZSE 会自动回退到最近已发布交易日。
- CNINFO：公告搜索，行业关键词为空时自动回退到头部成分股公告。
- Tushare：预留 direct HTTP client，配置 `TUSHARE_TOKEN` 后可继续接入日线、财务、披露日历、质押、估值分位、ETF 份额等接口。
- Equal Data：通过 `EQUAL_DATA_API_KEY` 预留，适合公告、机构、龙虎榜、解禁、增减持、诉讼质押、收入结构等事件源。
- 搜索链：Tavily -> Serper -> SerpAPI -> Brave -> SearxNG。

新增数据源路由说明见：

- `skill/references/provider_registry.md`
- `skill/references/data_sources.md`
- `skill/references/report_data_matrix.md`

注意：不要提交 Token。`.env` 和 `xtick/scripts/Config.py` 已在 `.gitignore` 中忽略。

### 2026-07-02 数据源补强

本轮补强把“页面需要的数据”拆到字段级，详见 `skill/references/report_data_matrix.md`。建议每次扩展或排查空页面时先运行：

```powershell
$env:PYTHONUTF8='1'
python scripts\probe_data_sources.py --samples
python scripts\generate_once.py --report smart_money_clusters --sector 光伏设备
python scripts\generate_once.py --report global_mapping --sector 光伏设备
```

## 自定义大模型

多智能体分析支持 OpenAI-compatible 模型服务。用户指定模型时优先使用用户传入配置；未指定时，脚本和 FastAPI 使用 `.env` 中的 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`；仍未配置时使用本地规则智能体，保证离线可运行。本地无鉴权模型可以不填 `OPENAI_API_KEY`，只要 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 可用即可。

CLI 示例：

```powershell
python scripts\generate_once.py --report market_replay `
  --llm-base-url https://api.openai.com/v1 `
  --llm-api-key YOUR_KEY `
  --llm-model gpt-4.1-mini
```

FastAPI 示例（推荐用请求头传 key）：

```text
POST /api/reports/generate?report_type=market_replay&llm_base_url=https://api.openai.com/v1&llm_model=gpt-4.1-mini
X-LLM-API-Key: YOUR_KEY
```

安全约束：API key 只用于当次请求或 `.env` 配置，不会写入生成的 HTML、返回 JSON 或同步到安装目录文档中。兼容 query 参数 `llm_api_key`，但不推荐用于生产。

## Skill 安装目录同步

项目内源 skill 路径：

```text
D:\PythonProject\Quant\a_share_research_skill\skill
```

Codex 实际调用的安装目录：

```text
C:\Users\74142\.codex\skills\a-share-research-html
```

手动同步：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_skill.ps1
```

安装自动同步 Git hooks：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_skill_sync_hooks.ps1
```

已安装后，仓库执行 `git checkout`、`git merge`、`git rebase`/`git reset` 触发的 rewrite、`git commit`、`git am` 后，会自动调用 `scripts\sync_skill.ps1`，将 `skill/` 镜像到 Codex skill 安装目录。Hook 日志在 `.git/skill-sync.log`。

## 安全说明

本项目仅用于研究和页面生成，不自动下单，不承诺收益。第三方 Skill/ClawHub 仓库只建议做架构参考；生产环境必须做代码审计、版本锁定、哈希校验和沙箱隔离。
