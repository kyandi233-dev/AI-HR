# 实验1 原则判断

完整操作流程见 [docs/实验流程.md](../../docs/实验流程.md)。

## 任务

- **评价内容：** 专业能力信息与私人道德信息的优先性、权重和重要性。
- **任务一：** 专业能力判断规则。
- **任务二：** 面试推荐判断规则。
- **每次输入：** 定义、两道问题、输出格式，合为一条user消息。
- **消息结构：** 每条请求只有一条 user 消息；没有 system 消息，没有历史对话。
- **每次输出：** 两道问题各自的数值和理由。

## 条件

| 条件 | 定义顺序 | 问题顺序 |
|---|---|---|
| M12 | 道德→能力 | 任务一→任务二 |
| M21 | 道德→能力 | 任务二→任务一 |
| A12 | 能力→道德 | 任务一→任务二 |
| A21 | 能力→道德 | 任务二→任务一 |

## 批次计划与运行

- **计划文件：** `config/principles_100.json`。
- **数量：** `repeat=25`，每条件25次，共100次调用。
- **轮次：** 一轮包含四个条件各一次；每条件100次对应总共400次。
- **批次名：** 由 `run_id` 指定，也是结果目录名；每个新批次换新名字。
- **阶段：** 计划中默认 `pilot`；正式数据改为 `main`。
- **参数：** `temperature=1`、`thinking=disabled`、`max_tokens=2200`。
- **并发：** 默认1；命令行 `--concurrency` 指定。
- **密钥：** 填入项目根目录 `.env`，后续运行自动读取。

## 命令

- **项目根目录预览（不调用 API）：**

```powershell
.\.venv\Scripts\python.exe experiments/exp_1_principles/run.py
```

- **正式执行：**

```powershell
.\.venv\Scripts\python.exe experiments/exp_1_principles/run.py --execute
```

- **指定新批次名：** 加 `--run-id <新名字>`。
- **自定义计划：** 加 `--batch <路径>`。
- **本次数量上限：** 加 `--limit <次数>`。
- **失败重试：** 加 `--retry-failed`。
- **并发：** 加 `--concurrency <数量>`。

## 文件与输出

- **条件和任务：** `run.py`。
- **完整模板：** `prompts/principles.txt`。
- **模型参数：** `config/settings.json`。
- **批次根目录：** `results/<run-id>/`，含 `batch.json` 和 `results.csv`。
- **逐次记录：** `results/<run-id>/records/`，每次尝试一对 `*.input.json` 和 `*.output.json`，包含原始回答、解析结果、时间、模型和用量。
- **结果表：** 每次尝试一行，包含两道题的答案；100次全部成功时为100行。
- **并发记录：** `sequence` 为计划编号，时间字段为实际运行时间。
- **理由检查：** 空白理由计为校验失败，原始回答保留。
- **顺序检查：** JSON任务键顺序差异写入 `validation_warnings`，保留模型返回的顺序。
- **历史预实验：** `results/20261116_principles_pilot_02/`。
- **已运行pilot：** `results/20261117_principles_pilot_temp1_01/`，100次全部成功；每次请求仅一条 user 消息，无 system 消息。
