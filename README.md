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

## 已设计扩展报告类型

提示词库已补充：板块资金轮动、聪明资金攻击面、板块估值诊股、趋势共振、自选股终端、指数/ETF 监控、流动性仪表盘、财报催化日历、单股事件风险、产业链图谱、海外映射等功能。当前后端仍需继续扩展 `Pipeline` 才能一键运行这些新类型。

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
- Sina：指数实时行情兜底。
- 同花顺：行业涨跌幅、行业成交额、行业净流入、行业上涨/下跌家数。
- Equal Data：通过 `EQUAL_DATA_API_KEY` 预留，适合公告、机构、龙虎榜、解禁、增减持等事件源。
- 搜索链：Tavily -> Serper -> SerpAPI -> Brave -> SearxNG。

新增数据源路由说明见：

- `skill/references/provider_registry.md`
- `skill/references/data_sources.md`

注意：不要提交 Token。`.env` 和 `xtick/scripts/Config.py` 已在 `.gitignore` 中忽略。

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
