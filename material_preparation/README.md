# 实验材料准备

## 脚本

- **职业来源：** `fetch_occupations.py`。
- **JD生成：** `generate_jd.py`。
- **简历生成：** `generate_resumes.py`。
- **故事生成：** `generate_morality.py`。
- **简历质量审核：** `review_resumes.py`。
- **故事质量审核：** `review_morality.py`。

## 参数

- **生成：** `temperature=1`、`thinking=disabled`、`max_tokens=3000`。
- **质量审核：** `temperature=1`、`thinking=disabled`、`max_tokens=1600`。
- **数量：** `--count` 指定生成份数。
- **并发：** `--concurrency` 指定同时执行的请求数，默认1。
- **密钥：** 项目根目录 `.env`。

## 材料位置

- **职业登记：** `config/occupations.json`。
- **来源和岗位设定：** `sources/occupations/<职业ID>/`。
- **审核后的职业资料：** `approved/occupations/<职业ID>/onet/profile.txt`。
- **JD草稿：** `drafts/occupations/<职业ID>/jd.txt`。
- **批准JD：** `approved/occupations/<职业ID>/jd.txt`。
- **简历草稿：** `drafts/occupations/<职业ID>/resumes/`。
- **批准简历：** `approved/occupations/<职业ID>/resumes/`。
- **故事草稿：** `drafts/morality/`。
- **批准故事：** `approved/morality/`，每个JSON包含pair_id、foundation、neutral、negative。
- **完整提示词：** `prompts/`。
- **生成和审核记录：** `results/`。

## 操作顺序

- **获取来源：** 下载O*NET原文，人工整理职业资料。
- **设定岗位：** 填写来源目录中的 `job_setup.json`。
- **准备JD：** 生成草稿，人工审核后存入批准目录。
- **准备简历：** 根据批准JD生成，审核后存入批准目录。
- **准备故事：** 生成私人非道德与负面道德行为配对，审核后存入批准目录。
- **固定实验材料：** 运行实验2或实验3的 `snapshot_materials.py`。

## 项目根目录命令示例

- **来源预览：**

```powershell
.\.venv\Scripts\python.exe -B material_preparation/fetch_occupations.py --occupation software_developer
```

- **生成JD预览：**

```powershell
.\.venv\Scripts\python.exe -B material_preparation/generate_jd.py --occupation software_developer --run-id jd_pilot01
```

- **100份简历生成预览：**

```powershell
.\.venv\Scripts\python.exe -B material_preparation/generate_resumes.py --occupation software_developer --count 100 --run-id resumes_pilot01
```

- **故事生成预览：**

```powershell
.\.venv\Scripts\python.exe -B material_preparation/generate_morality.py --foundation fairness --count 100 --run-id stories_pilot01
```

- **质量审核：** 审核脚本使用 `--source drafts` 或 `--source approved` 选择材料。
- **实际执行：** 命令末尾添加 `--execute`；可同时添加 `--concurrency 4`。
- **内容检查：** 程序检查文件存在、文字非空和必需字段；人工审核内容质量。
- **当前准备状态：** 四个职业已登记，待整理来源、填写岗位设定和批准材料。
