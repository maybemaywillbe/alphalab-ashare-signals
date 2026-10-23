# AlphaLab 复现指南

本指南说明如何在 macOS 上运行已冻结的 AlphaLab 研究流程。研究计划和 100 只股票样本是复现输入；缺少冻结文件时，流程会报错，不会重新获取名单或抽样。

## 环境要求

- macOS，Python 3.10 或更高版本
- 可访问 Sina 行情服务的网络连接
- 项目根目录中的 `pyproject.toml`、`alphalab/`、`scripts/`、`configs/` 和 `inputs/`

## 数据来源

- **冻结候选池：** BaoStock `query_stock_basic()` 的当前沪深股票名单快照，按冻结计划选择 100 只。原始候选名单 CSV 未随公开仓库分发，因此不能独立复核其来源哈希或重建原始抽样过程；仓库提供冻结的 100 只样本，可用于复现后续分析。该第三方名单不是交易所完整性认证，也不是历史时点（PIT）股票池；当前上市样本存在幸存者偏差。
- **历史行情与交易日历：** AKShare/Sina 提供 raw、QFQ 日线及交易日历。Sina 行情不会用于重建或重抽股票名单。
- **可复现性：** 行情提供方可能修订历史日线、复权因子或补录记录，因此相同股票样本与研究计划不保证重新下载后得到逐位相同的数值。公开仓库不包含原始 Sina 行情文件。

## 复现步骤

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,viz,fetch]'
bash scripts/run_end_to_end_mac.sh
```

运行前必须存在以下配套冻结文件：

- `configs/study_plan.json`
- `configs/study_plan.json.sha256`
- `inputs/universe_selected.csv`

脚本会校验计划哈希、样本哈希、100 只目标数量及原定板块配额。任一文件缺失或校验失败时流程停止；应从同一正式 AlphaLab 发布包恢复对应文件，不得重新下载候选名单或重新抽样。

## 预期输出

- `outputs/study_2026/`：本次运行的研究结果及输入校验记录
- `outputs/study_2026/public_report/research_report.pdf`：英文研究报告
- `outputs/study_2026/public_report/figures/`：六张图表
- `outputs/public_release_ready/AlphaLab/`：不含原始行情文件的公开发布目录

完整研究流程需要访问 Sina 行情接口；本地既有有效行情快照可按采集器缓存校验规则复用。完整研究输出目录已存在时，研究运行器会拒绝覆盖。

## 研究限制

股票池是当前上市沪深样本，不是历史 PIT 股票池；2023–2025 为复用历史期间，2026 为历史扩展而非真正独立的前瞻样本外检验。QFQ 调整版本、总收益口径、可交易执行与完整交易成本均未独立认证。第三方行情许可不扩展为原始数据公开再分发许可。
