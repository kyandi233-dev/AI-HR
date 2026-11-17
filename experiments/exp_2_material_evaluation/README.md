# 实验2 材料独立评价

## 评价内容

- **故事属性：** `evaluate_morality.py`，评价道德效价、道德基础归属、可理解性、自然性。
- **岗位关联性：** `evaluate_relevance.py`，评价故事提供的岗位专业能力证据。
- **补充指标：** 严重程度、可信程度的题目与量表待确定。

## 配置与材料

- **模型参数：** `config/settings.json`，temperature=1、thinking=disabled、max_tokens=1600。
- **完整提示词：** `prompts/`。
- **固定材料：** `materials/<版本>/`。
- **来源记录：** 材料版本内的 `manifest.json`。
- **评价记录：** `results/`。
- **密钥：** 项目根目录 `.env`，各次运行共用。

## 固定材料

- **复制计划预览：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_2_material_evaluation/snapshot_materials.py --version pilot_materials_v1 --occupations software_developer --include-morality
```

- **复制文件：** 在命令末尾添加 `--execute`。
- **修改材料：** 建立新版本，并在运行计划中更新 `materials_version`。

## 运行评价

- **故事属性预览：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_2_material_evaluation/evaluate_morality.py --batch experiments/exp_2_material_evaluation/config/morality_example.json
```

- **岗位关联性预览：**

```powershell
.\.venv\Scripts\python.exe -B experiments/exp_2_material_evaluation/evaluate_relevance.py --batch experiments/exp_2_material_evaluation/config/relevance_example.json
```

- **采集：** 命令末尾添加 `--execute`。
- **并发：** 添加 `--concurrency 4` 同时处理最多4个请求。
- **评价次数：** 当前两个任务对每份故事各测一次。
- **数据用途：** 本目录保存实验2评价；材料准备目录保存生成与质量审核记录。
