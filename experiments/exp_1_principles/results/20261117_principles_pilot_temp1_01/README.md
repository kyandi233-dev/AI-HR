# 原则实验 pilot 01

- **批次：** `20261117_principles_pilot_temp1_01`
- **阶段：** `pilot`
- **日期：** 2026-11-17
- **数量：** 4 个条件 × 25 次 = 100 次独立请求
- **模型：** `deepseek-flash`
- **参数：** `temperature=1`、`thinking=disabled`、`max_tokens=2200`、JSON 输出模式
- **消息结构：** 每次请求只有一条 `user` 消息；没有 `system` 消息；没有历史对话。
- **条件：** M12、M21、A12、A21；条件之间只改变两类定义的顺序和两道问题的顺序。
- **执行：** 并发 100；单请求超时 120 秒；SDK 自动重试关闭。
- **结果：** 成功 100，失败 0。
- **用量：** 输入 38,800 tokens，输出 19,925 tokens，合计 58,725 tokens。
- **体积：** 202 个数据文件，约 1.03 MiB。

## 文件

- `batch.json`：批次参数、试次清单和输入哈希。
- `results.csv`：100 行，每次调用一行，两道题的答案在同一行。
- `records/`：100 对 `*.input.json` 和 `*.output.json`，保留完整提示词、原始响应、解析结果、用量和校验信息。

## 说明

- 本批所有请求均为单条 user 消息，未使用 system 消息。
- 每道题返回 `priority`、`weight_ability`、`weight_morality`、`importance_ability`、`importance_morality`、`reason` 六个字段。
- 本目录只保存原始数据和导出表，不包含统计推断。
