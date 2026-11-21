# O*NET 职业资料抓取与审核表

本阶段保留全部候选职业，只下载每个职业的初始 Details 响应。不访问 `more`、表格下载链接、关联职业、州或地区查询及外部网站，不调用模型，不翻译、筛选、摘要或改写来源内容，不修改 JD 和简历 prompt。

## 环境

在项目根目录使用 Python 3.10 或更新版本。当前验证环境为 Python 3.14.6。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

`requirements.txt` 声明依赖范围；`requirements-lock.txt` 固定本次验证版本。下载使用 requests 和 BeautifulSoup；审核表导出使用项目自己的 openpyxl 依赖，不需要 Codex 的内置环境。

## 输入

`material_preparation/config/occupations.json` 是固定候选清单：23个 Job Family，每类3个职业，再保留原仓库的商业智能分析师，按职业编码去重，共70个职业。每项保存官方英文名称、O*NET编码、大类编码和英文大类名。保留原有内部键以兼容其他实验，来源目录以官方英文名和编码命名。

公司、岗位层级、JD和简历不属于本阶段输入。军事职业也保留；官方页面没有的资料不编造。

## 执行命令

```powershell
# 只预览，不请求网页
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/fetch_occupations.py --all

# 抓取初始页；默认每职业间隔0.5秒
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/fetch_occupations.py --all --execute --run-id occupation_sources_20261121

# 只解析已保存的文件，不联网
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/parse_occupations.py --all

# 导出总表、各职业表和CSV，不联网
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/export_occupation_review.py

# 核验来源摘要、表格值、CSV和原文完整性
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/verify_occupation_exports.py
```

单个职业使用 `--occupation software_developer` 代替 `--all`。失败后重跑下载命令会复用已经成功且摘要核验通过的来源，只请求尚未下载的职业。每次下载执行均单独保存结果记录，不覆盖上次记录。当前没有覆盖或刷新原始下载的选项。

## 输出

每个职业目录例如：

```text
material_preparation/sources/occupations/Software_Developers_15-1252.00/onet/
    source_details.html
    source_details.txt
    source_metadata.json
    structured_en.json
    职业资料.xlsx
    csv/
```

- HTML按响应字节保存；TXT是正文文字提取，原始HTML始终保留。
- 已下载的旧版软件开发来源会逐字节复制到新命名目录，旧文件不移动。旧下载脚本在Windows转换换行符，因此来源验证明确区分旧换行处理与字节摘要。
- 解析所有 `reportsection`，不使用栏目白名单；未归入这些栏目区域的内容另存为Overview。原始栏目文字、条目、字段、链接、表单控件全部留在JSON或原文中。
- 表格和列表的隐藏行也解析。`N more`仅保留文字和链接，不访问。来源页原有顺序保持不变，不重新计算排名。
- 一个工作情境条目可能包含多个回答比例；67个软件技能类别不等于67个工具名。培训和招聘入口不等于查询结果。
- 学历只记录页面实际提供的项目，不补齐未显示的学历分布。
- 审核资料按原生条目和完整段落展示，不再按固定字符数切开单词。
- Excel导出使用XML字符引用保留原文中的CR/LF换行，避免Windows写入和XML读取自动转换内容；验证脚本逐项比较Excel、CSV及结构化原文。

总审核文件：`material_preparation/review/职业与材料审核.xlsx`，只含“职业汇总”一张表，每个职业一行，按大类和编码排列，人工审核列紧邻职业身份和资料链接。

每个职业的`职业资料.xlsx`按网页原栏目分sheet，例如Overview、Tasks、Knowledge、Work Styles；表格使用该栏目的原生字段。分数、条目名称和说明分列显示，不将导航按钮当成职业数据。Overview提供原始概述及栏目跳转目录。技术字段、JSON、网页导航和原始链接不再占据人工审核页面，完整HTML和JSON保留不改。

仅保留新版：总表的CSV是`review/职业汇总.csv`，导出记录是`review/export_manifest.json`；每个职业新版栏目CSV位于各自的`onet/csv/`。旧版通用明细CSV、旧导出记录和Excel旧备份已按用户要求删除，不再生成双版本目录。

总表使用Excel原生`HYPERLINK("[完整路径]Overview!A1","打开职业资料")`公式，指定目标工作簿及概览页，不使用`file:///`及百分号编码。核验脚本检查70个公式及其目标文件。移动仓库或换电脑后，重新运行`--summary-only`即可按当前路径生成公式。CSV保存显示文字，不包含跳转功能；请用Excel总表审核。

仅在各职业来源和解析结果不变、独立表已经使用新版栏目布局时，可用 `export_occupation_review.py --summary-only` 只更新总表。三个军事职业的初始页面声明不采集军职详细数据，保留概述和职业信息入口，总表标注“资料有限”，不生成不存在的Tasks等清单。

黄色人工列包括“是否选用、人工分类、JD、简历1、简历2、审核人、审核日期、审核备注”，首次为空。只在“职业汇总”的人工列填写审核记录；其他sheet由来源重新生成。再次导出按O*NET编码保留人工列及额外自定义列；采用临时文件写入并成功替换，按用户要求不保留旧版本备份。来源内容变化时增加复核提示，不擅自撤销已有结论。关闭Excel后再运行导出。

## 验证和历史试稿清理

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

离线测试包括：不访问more、原始字节保持、隐藏行和未知栏目保留、声明数量不一致提示、审核记录及自定义列保留、长文本完整分段，以及CR/LF和类似公式的原文字串在Excel中原样读回。

`cleanup_previous_trial.py` 只用于用户明确要求删除的上一轮软件开发试稿。默认预览，`--execute`才删除；仅删除与已保存摘要或API输出完全一致的明确文件。原始O*NET文件、原始API输入输出和其他实验记录保留。如果文件已被修改则停止，不自行删除。
