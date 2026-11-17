# AI-HR 招聘评价研究

## 研究结构

- **实验1：原则判断。** 位置：`experiments/exp_1_principles/`。
- **材料准备：职业来源、JD、简历、私人行为故事的生成与审核。** 位置：`material_preparation/`。
- **实验2：材料属性独立评价。** 位置：`experiments/exp_2_material_evaluation/`。评价故事属性与岗位关联性。
- **实验3：A/B/C招聘评价。** 位置：`experiments/exp_3_hiring/`。三个条件共用同一份简历。
- **公共工具：请求、存档、材料版本和导出。** 位置：`shared/`。
- **实验文件：** 各阶段集中保存脚本、`prompts/`、`config/`、`results/`；实验2、3另有 `materials/`。

## 当前参数

| 用途 | temperature | thinking | max_tokens |
|---|---:|---|---:|
| JD、简历、故事生成 | 1 | disabled | 3000 |
| 材料质量审核 | 1 | disabled | 1600 |
| 实验1：原则判断 | 1 | disabled | 2200 |
| 实验2：材料独立评价 | 1 | disabled | 1600 |
| 实验3：招聘评价 | 1 | disabled | 2200 |

- **配置位置：** 各阶段的 `config/settings.json`。
- **批次覆盖：** 计划中的 `profile_overrides` 可覆盖模型、温度、thinking和输出上限。
- **并发数：** 默认1；`--concurrency 4` 表示最多同时执行4个请求。
- **请求数量：** 由批次计划确定；`--limit 10` 表示本次最多执行10个待运行试次。

## 密钥

- **填写位置：** 项目根目录 `.env`，格式为 `DEEPSEEK_API_KEY=你的密钥`。
- **使用周期：** 保存一次，后续各次实验共用；更换密钥时修改该文件。
- **读取顺序：** 当前终端的 `DEEPSEEK_API_KEY` → 项目 `.env`。
- **Git规则：** `.env` 已加入忽略列表；模板为 `.env.example`。

## 运行100次原则pilot

- **工作目录：** `D:\_Experiment\AI-HR`。
- **计划：** `experiments/exp_1_principles/config/principles_100.json`。
- **数量：** 四个条件各25次，总共100次。
- **阶段：** `pilot`。
- **批次：** `20261117_principles_pilot_temp1_01`。
- **预览命令：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_1_principles/run.py --limit 1
```

- **四并发执行命令：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_1_principles/run.py --concurrency 4 --execute
```

- **对话结构：** 每个试次发送一条完整user消息，两道题在同一条回复中回答。
- **运行顺序：** 计划顺序由run-id确定；并发时记录各请求的实际开始和完成时间。

## 材料流程

- **来源：** `material_preparation/sources/` 保存职业原文和岗位设定。
- **草稿：** `material_preparation/drafts/` 保存生成结果。
- **批准材料：** 人工审查后保存到 `material_preparation/approved/`。
- **实验材料：** 实验2、3各自的 `snapshot_materials.py` 将选定材料复制到 `materials/<版本>/`。
- **版本记录：** `manifest.json` 保存来源、文件清单和内容摘要。
- **用途记录：** 生成、质量审核、实验2测量、实验3招聘评价分别存档。

## 输出与续跑

- **结果位置：** 对应阶段的 `results/`。
- **批次根目录：** `batch.json` 和 `results.csv`。
- **逐次记录：** 每次调用的 `*.input.json` 和 `*.output.json`，位于批次目录的 `records/` 子目录。
- **历史批次：** 已有迁移批次保留扁平文件布局，读取和导出一致。
- **批次表：** `results.csv` 按试次编号、尝试编号排列。
- **历史试次：** 实验1的四次预实验保存在 `results/20261116_principles_pilot_02/`，保留原时间、参数和回答。
- **续跑：** 执行相同命令，跳过成功试次；失败和中断试次通过 `--retry-failed` 重试。
- **参数变更：** 修改提示词、材料或模型参数后使用新run-id。
- **代码改动：** 源码摘要作为追溯信息保存，修改注释或代码后可继续相同输入的批次。
- **质量字段：** 空白理由计为校验失败；任务键顺序差异写入 `validation_warnings`。
- **数据备份：** 新批次目录由Git忽略，按实验批次另行备份。

## 环境与检查

- **新设备建立环境：** `python -m venv .venv`。
- **安装依赖：** `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。
- **离线测试：** `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`。
- **职业状态：** `.\.venv\Scripts\python.exe -B src/hrpilot.py status`。
- **结果导出：** `.\.venv\Scripts\python.exe -B -m shared.cli export --task principles`。
- **详细说明：** 各阶段README、`docs/研究协议与限制.md`、`docs/数据字段.md`。
