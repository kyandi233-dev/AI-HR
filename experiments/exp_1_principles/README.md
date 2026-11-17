# 实验1 原则判断

## 任务

- **评价内容：** 专业能力信息与私人道德信息的优先性、权重和重要性。
- **任务一：** 专业能力判断规则。
- **任务二：** 面试推荐判断规则。
- **每次输入：** 定义、两道问题、输出格式，合为一条user消息。
- **每次输出：** 两道问题各自的数值和理由。

## 条件

| 条件 | 定义顺序 | 问题顺序 |
|---|---|---|
| M12 | 道德→能力 | 任务一→任务二 |
| M21 | 道德→能力 | 任务二→任务一 |
| A12 | 能力→道德 | 任务一→任务二 |
| A21 | 能力→道德 | 任务二→任务一 |

## 当前pilot

- **计划文件：** `config/principles_100.json`。
- **阶段：** `pilot`。
- **批次：** `20261117_principles_pilot_temp1_01`。
- **数量：** `repeat=25`，每条件25次，共100次调用。
- **轮次：** 一轮包含四个条件各一次；每条件100次对应总共400次。
- **参数：** `temperature=1`、`thinking=disabled`、`max_tokens=2200`。
- **并发：** 默认1；命令行 `--concurrency 4` 设置为4。
- **密钥：** 填入项目根目录 `.env`，后续运行自动读取。

## 命令

- **项目根目录预览：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_1_principles/run.py --limit 1
```

- **四并发执行：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_1_principles/run.py --concurrency 4 --execute
```

- **自定义计划：** `--batch <路径>`。
- **本次数量上限：** `--limit <次数>`。
- **失败重试：** 原命令添加 `--retry-failed`。

## 文件与输出

- **条件和任务：** `run.py`。
- **完整模板：** `prompts/principles.txt`。
- **模型参数：** `config/settings.json`。
- **批次结果：** `results/<run-id>/`。
- **逐次记录：** 输入JSON、原始回答、解析结果、时间、模型和用量。
- **结果表：** 每次尝试一行，包含两道题的答案；100次全部成功时为100行。
- **并发记录：** `sequence` 为计划编号，时间字段为实际运行时间。
- **理由检查：** 空白理由计为校验失败，原始回答保留。
- **顺序检查：** JSON任务键顺序差异写入 `validation_warnings`，保留模型返回的顺序。
- **历史预实验：** `results/20261116_principles_pilot_02/`。
