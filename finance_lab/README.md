# finance_lab 结构说明

把「取数 / 计算 / 展示 / 入口」拆开，避免所有 `.py` 平铺在一起看不出关系。

## 三层依赖（只允许从上往下用）

```text
apps/        入口：你要跑的任务（可 argparse、打印、写文件）
   │
   ▼
reports/     报告：把结果渲染成 HTML
   │
   ▼
core/        核心：路径、知识体系、AKShare 取数、指标与尾部检验
```

`core` 不依赖 `apps` / `reports`。  
`reports` 不依赖 `apps`。  
`apps` 之间互不 import。

## 目录

| 路径 | 职责 |
|------|------|
| `core/paths.py` | 项目根、知识体系 JSON、output 目录 |
| `core/knowledge.py` | 读知识体系名词与公式 |
| `core/market_data.py` | AKShare 拉行情 / 利率 |
| `core/indicators.py` | 夏普、总收益、归一化净值等 |
| `core/tail_risk.py` | 肥尾 / VaR / 回撤检验 |
| `core/dcf.py` | 自由现金流折现（FCFF-DCF） |
| `core/irr_npv.py` | 净现值 NPV / 内部收益率 IRR |
| `core/per_capita.py` | 人均创利（归母净利润 / 员工人数） |
| `core/samples.py` | 各行业龙头股样本（`SECTOR_LEADERS` / `SECTOR_SAMPLES`） |
| `reports/*.py` | HTML 模板渲染 |
| `apps/*.py` | **唯一推荐的运行入口** |
| `output/` | 生成的 HTML（不入库） |

## 入口是干什么的

| 入口命令 | 干什么 |
|----------|--------|
| `python -m finance_lab.apps.sharpe_demo` | **单票入门**：读「夏普比率」公式 → 拉一只股票 → 算出夏普并打印 |
| `python -m finance_lab.apps.sector_compare` | **横向对比**：各行业龙头股，表格 + 夏普/波动/走势 HTML |
| `python -m finance_lab.apps.tail_risk_evidence` | **证明尾部风险**：超额峰度、极端日 vs 正态、VaR/回撤 + HTML |
| `python -m finance_lab.apps.dcf_sector_compare` | **DCF 现值**：各行业龙头股自由现金流折现，现值 vs 市值 + HTML |
| `python -m finance_lab.apps.irr_npv` | **NPV / IRR**：手输或 CSV 现金流，或按 A 股买卖价自动算 |
| `python -m finance_lab.apps.per_capita_profit` | **人均创利**：龙头股归母净利润 / 员工人数 + HTML |

示例：

```bash
uv run python -m finance_lab.apps.sharpe_demo
uv run python -m finance_lab.apps.sector_compare
uv run python -m finance_lab.apps.tail_risk_evidence
uv run python -m finance_lab.apps.dcf_sector_compare
uv run python -m finance_lab.apps.irr_npv
uv run python -m finance_lab.apps.irr_npv --invest 100 --cf 40,40,40 --r 0.10
uv run python -m finance_lab.apps.irr_npv --stock 300534 --start 20240101 --r 0.08
uv run python -m finance_lab.apps.per_capita_profit
uv run python -m finance_lab.apps.per_capita_profit --year 2025
```
