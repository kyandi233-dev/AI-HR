# 实验3 招聘评价

## 条件

- **A：** 岗位要求＋简历。
- **B：** 同一岗位要求＋同一简历＋私人非道德信息。
- **C：** 同一岗位要求＋同一简历＋私人道德信息。
- **当前故事方向：** 中性行为与负面私人道德行为配对。
- **主要比较：** C－B。
- **辅助比较：** B－A、C－A。
- **配对规则：** B/C共用标题和导语，替换同一故事配对的行为正文。
- **A的使用：** 每份简历的A供各故事配对共享，分析保留简历和配对编号。

## 配置与文件

- **入口：** `run.py`。
- **完整A/B/C任务名：** `abc`。
- **单独运行A的任务名：** `baseline`。
- **参数：** `config/settings.json`，temperature=1、thinking=disabled、max_tokens=2200。
- **提示词和评分标准：** `prompts/`。
- **固定材料：** `materials/<版本>/`。
- **A/B/C结果：** `results/abc/<职业ID>/<run-id>/`。
- **单独A结果：** `results/a_only/<职业ID>/<run-id>/`。
- **密钥：** 项目根目录 `.env`。

## 固定材料

- **从实验2选取已评价材料：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_3_hiring/snapshot_materials.py --version pilot_materials_v1 --occupations software_developer --include-morality --from-experiment exp_2_material_evaluation --from-version pilot_materials_v1
```

- **从批准目录选取：** 省略 `--from-experiment` 和 `--from-version`。
- **复制文件：** 命令末尾添加 `--execute`。
- **材料选择记录：** 记录职业、简历、故事的纳入与排除依据。

## 运行

- **预览：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_3_hiring/run.py --batch experiments/exp_3_hiring/config/hiring_example.json
```

- **采集：** 命令末尾添加 `--execute`。
- **并发：** 添加 `--concurrency 4`。
- **职业选择：** 修改计划中的 `occupations`。
- **单独运行A：** 使用 `--task baseline --occupation software_developer --materials-version pilot_materials_v1 --run-id hiring_a_pilot01`。
- **分析标识：** 保留职业、简历、故事配对、重复、批次和材料版本编号。
