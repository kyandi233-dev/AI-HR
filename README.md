# AI-HR 招聘评价研究

比较模型自陈的招聘原则，与它在具体候选人材料上的招聘评价是否存在差异。

## 文档导航

- **本 README：** 项目各部分功能、配置和文件位置。
- **完整操作流程：** [docs/实验流程.md](docs/实验流程.md)。
- **研究设计：** [docs/研究协议与限制.md](docs/研究协议与限制.md)。
- **数据字段：** [docs/数据字段.md](docs/数据字段.md)。
- **运行检查表：** [docs/实验运行前检查表.md](docs/实验运行前检查表.md)。
- **更新记录：** [docs/更新记录.md](docs/更新记录.md)。

## 项目各部分功能

| 目录                                       | 功能                                                                    | 当前状态                             |
| ------------------------------------------ | ----------------------------------------------------------------------- | ------------------------------------ |
| `experiments/exp_1_principles/`          | 实验1：不提供具体材料，询问专业能力与私人道德信息的优先性、权重和重要性 | 代码和计划完整，可运行               |
| `material_preparation/`                  | 职业来源下载、JD/简历/私人行为故事生成、质量审核、人工批准              | 四个职业已登记，待整理来源和批准材料 |
| `experiments/exp_2_material_evaluation/` | 实验2：故事属性、岗位关联性独立评价                                     | 脚本可用，需要先固定材料             |
| `experiments/exp_3_hiring/`              | 实验3：A/B/C 招聘评价，三个条件共用同一份简历                           | 脚本可用，需要先固定材料             |
| `shared/`                                | 请求、存档、批次一致性、材料版本、CSV 导出的公共工具                    | 修改实验时通常不用动                 |
| `tests/`                                 | 使用临时目录和模拟 API 的离线测试                                       | 不调用真实模型、不花钱               |
| `docs/`                                  | 研究协议、字段说明、实验流程、检查表、更新记录                          | —                                   |
| `src/hrpilot.py`                         | 兼容入口，转发到 `shared/cli.py`                                      | 日常操作优先用各阶段脚本             |

## 一次实验的三层配置

- **实验代码：** 定义条件、材料和提示词，例如 `experiments/exp_1_principles/run.py`。
- **模型参数：** 各阶段 `config/settings.json`，保存模型、温度、thinking、`max_tokens`、超时、并发。
- **批次计划：** 各阶段 `config/*.json`，保存 `task`、`run_id`、`stage`、`repeat`、职业和材料版本。
- **三层的关系：** 运行器读取实验代码和两份配置，组装请求、调用 API、保存结果。

## 批次计划、run_id 与 stage

- **批次计划 JSON 是普通文本文件：** 用编辑器复制修改，不需要改代码。
- **同一份计划可以反复用：** 每批运行时用 `--run-id` 指定新批次名。
- **不同规模或条件：** 复制一份新的 JSON，改 `repeat` 等字段，运行时用 `--batch` 指定。
- **新的实验类型：** 建新实验目录和新计划 JSON。
- **`run_id`：** 批次名，也是结果文件夹名；必须是新名字，否则已完成的试次会跳过。
- **`stage`：** 批次用途标签，`development` 调试、`pilot` 预实验、`main` 正式数据；只记录，不改变参数。
- **参数优先级：** 命令行显式参数 > 批次计划 JSON > 程序默认值。

## 运行命令

- **以下命令都在项目根目录执行。**

预览（不调用 API、不花钱、不写文件）：

```powershell
python experiments/exp_1_principles/run.py
```

正式执行（调用 API、写结果、产生费用）：

```powershell
python experiments/exp_1_principles/run.py --execute
```

新批次换名：

```powershell
python experiments/exp_1_principles/run.py --run-id 20261118_principles_pilot_02 --execute
```

- **虚拟环境：** 激活后直接用 `python`；未激活时用 `.\.venv\Scripts\python.exe`。
- **并发：** 默认读 `settings.json`；`--concurrency 100` 表示最多同时 100 个请求。
- **本次上限：** `--limit 10` 本次最多新跑 10 个待运行试次。
- **失败重试：** 在原命令后加 `--retry-failed`。
- **其他计划：** `--batch <计划JSON路径>`。

## `--execute` 的注意事项

- **默认是预览，这是有意的安全设计：** 防止误触一次产生大量付费调用。
- **预览会显示：** 阶段、计划数、待运行数、模型、温度、`max_tokens`、并发、批次名和第一条完整提示词。
- **正式跑之前先核对预览输出。**
- **同一 run_id 再跑：** 成功项跳过；失败项要加 `--retry-failed`。
- **改了提示词、材料或参数后：** 必须用新 run_id。
- **不要手工修改 `results/` 里的文件。**

## 当前参数

| 用途                | temperature | thinking | max_tokens |
| ------------------- | ----------: | -------- | ---------: |
| JD、简历、故事生成  |           1 | disabled |       3000 |
| 材料质量审核        |           1 | disabled |       1600 |
| 实验1：原则判断     |           1 | disabled |       2200 |
| 实验2：材料独立评价 |           1 | disabled |       1600 |
| 实验3：招聘评价     |           1 | disabled |       2200 |

- **配置位置：** 各阶段的 `config/settings.json`。
- **批次覆盖：** 计划中的 `profile_overrides` 可覆盖模型、温度、thinking 和输出上限。

## 密钥

- **填写位置：** 项目根目录 `.env`，格式为 `DEEPSEEK_API_KEY=你的密钥`。
- **使用周期：** 保存一次，后续各次实验共用；更换密钥时修改该文件。
- **读取顺序：** 当前终端的 `DEEPSEEK_API_KEY` → 项目 `.env`。
- **Git 规则：** `.env` 已加入忽略列表；模板为 `.env.example`。

## 输出与续跑

- **结果位置：** 对应阶段的 `results/`。
- **批次根目录：** `batch.json` 和 `results.csv`。
- **逐次记录：** `records/` 子目录，每次尝试一对 `*.input.json` 和 `*.output.json`。
- **历史批次：** 已有迁移批次保留扁平文件布局，读取和导出一致。
- **续跑：** 执行相同命令，跳过成功试次；失败和中断试次通过 `--retry-failed` 重试。
- **参数变更：** 修改提示词、材料或模型参数后使用新 run_id。
- **质量字段：** 空白理由计为校验失败；任务键顺序差异写入 `validation_warnings`。
- **数据备份：** 新批次目录由 Git 忽略，上传时用 `git add -f` 强制添加。

## GitHub 上传与大小限制

- **单文件 50 MiB：** Git 警告，但仍可推送。
- **单文件 100 MiB：** GitHub 阻止。
- **网页上传：** 单文件最大 25 MiB。
- **仓库大小：** 建议小于 1 GB，强烈建议小于 5 GB。
- **实测体积：** 原则实验 100 次约 1 MB（202 个文件）。
- **官方说明：** [GitHub Docs — About large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

## 材料流程

- **来源：** `material_preparation/sources/` 保存职业原文和岗位设定。
- **草稿：** `material_preparation/drafts/` 保存生成结果。
- **批准材料：** 人工审查后保存到 `material_preparation/approved/`。
- **实验材料：** 实验2、3各自的 `snapshot_materials.py` 将选定材料复制到 `materials/<版本>/`。
- **版本记录：** `manifest.json` 保存来源、文件清单和内容摘要。
- **用途记录：** 生成、质量审核、实验2测量、实验3招聘评价分别存档。

## 环境与检查

- **新设备建立环境：** `python -m venv .venv`。
- **安装依赖：** `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。
- **离线测试：** `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`。
- **职业状态：** `.\.venv\Scripts\python.exe -B src/hrpilot.py status`。
- **结果导出：** `.\.venv\Scripts\python.exe -B -m shared.cli export --task principles`。

## 当前阶段状态

- **实验1：** 可运行；已有四次历史预实验 `results/20261116_principles_pilot_02/`，以及一批 100 次 pilot 结果 `results/20261117_principles_pilot_temp1_01/`（100 次全部成功）。
- **材料准备：** 四个职业只在 `config/occupations.json` 登记，尚无抓取记录和批准材料。
- **实验2：** 故事属性和岗位关联性脚本可用，但需要先准备并固定材料。
- **实验3：** A/B/C 脚本可用，但需要先准备并固定材料。
