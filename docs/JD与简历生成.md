# JD 与简历生成

## 输入和规则

职业登记仍用 `material_preparation/config/occupations.json` 中的内部键；新草稿和批准材料目录用英文职业名加 O*NET 编码。

`run_material_generation.py` 只读 `material_preparation/review/职业与材料审核.xlsx` 的“职业汇总”sheet，按 O*NET 编码对应职业。“是否选用”填1或“选用”决定职业范围；新版“JD是否纳入”“简历N是否纳入”填1决定纳入，兼容旧表材料列填“通过”。材料链接和审核决定分列。生成脚本不会代填审核结论，也不会重新保存审核表；运行前应保存 Excel 的最新审核结果。

生成读取每个职业现有的 `onet/structured_en.json`，核对职业编码及原始网页摘要，不创建 profile.txt，不依赖公司业务或额外岗位层级。原始存档不改动。

2026-11-24 的 JD 输入由 `config/jd_input_modules.json` 固定九个模块：Overview、Tasks、Detailed Work Activities、Job Zone、Software Skills、Knowledge、Education，以及补充用的 Essential Skills、Transferable Skills。九个模块的条目全部保留，不取前N项，不按分数删除条目，不进行语义去重。去掉链接、控件、来源文件路径等技术字段；字段value与text_original完全相同时只呈现一次，整行文字完全等于已有字段原文拼接时不再重复。名称以外的长说明仍保留；每个模块的source_text也保留，特别是Overview的records不包含完整职业概述，不能只读取其records。

每份request记录的metadata.input_projection保存配置和代码摘要、原栏目位置、逐条映射、条目数量及确切重复字段省略情况。筛选设计及以后如何调整属于脚本配置和运行记录，不写入模型提示词。模型看到所提供的职业内容，按写作规则组织JD。

简历现也读取同一组九个模块，保留原文和来源映射，不再输入整份存档JSON。按用户本轮要求，增加中等、低两种履历目标，规则见下方“分级简历生成”。

提示词是 `material_preparation/prompts/jd.txt`、`resume.txt`，本轮经验门槛统一3年以上；其余生成规则以已确认的提示词正文为准。模型与参数读取 `material_preparation/config/settings.json`。本轮仍使用 deepseek-flash、temperature=1、thinking=disabled、max_tokens=3000；规则和输入可复刻，采样回答不保证逐字重复，原始档案用于回查。

## JD 生成

在项目根目录运行：

```powershell
# 本轮完整输入预览，不调用模型
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task jd --run-id jd_modules_20261124

# 本轮实际执行方式，保存全部原始返回片段
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task jd --run-id jd_modules_20261124 --execute --stream --api-timeout 600
```

2026-11-24 用户明确要求删除上一版JD并生成新版。本轮使用新批次 `jd_modules_20261124`，原始调用档案仍保留。旧批次 `jd_four_occupations_20261123` 的四份草稿已经通过 `remove_jd_drafts.py --run-id jd_four_occupations_20261123 --execute` 删除：先校验生成结果记录、每份草稿摘要及旧响应原文，只删除明确对应的jd.txt，不递归删除。删除记录保存在旧批次的 `draft_removal.json`。

此删除操作仅用于本次明确授权，不能作为重新生成时的默认步骤；如果旧路径已经写入新版或人工修改过的内容，删除脚本会停止。新草稿仍写入原有职业目录，完整旧回答保留在旧批次响应档案中。

本轮草稿位于 `material_preparation/drafts/occupations/<英文名_编码>/jd.txt`，包含“依据记录”和“岗位公告”的完整原始回答。新版JD提示词要求一句简介、3—4条职责、4—5条任职要求、少量工具和一条概括1—2项认知能力的要求，正文以约300—450字为目标，依据记录逐条简述。社会性技能及人格品德排除规则继续保留。

本轮四份已成功生成并核验原文一致。岗位公告字符数（含标点、换行）分别为：信息安全分析师517、软件开发人员422、数据科学家375、商业智能分析师473。信息安全与商业智能两份超过提示词的篇幅目标，保留原始输出供人工审核，不手工删改。实际输入token分别为15518、17202、14129、15625。信息安全首次连接失败，显式重试后成功，全部尝试及流式片段保留。

每职业调用目录为 `material_preparation/results/jd_generation/<英文名_编码>/<run-id>/`，包含：

- `JD01.prompt.txt`：实际发送的完整提示词。
- `JD01.request.json`：完整任务及模型配置。
- `batch.json`、`records/*.input.json`、`records/*.output.json`、`results.csv`：批次、请求、原始响应、用量、状态等公共档案。

总体记录位于 `material_preparation/results/material_generation/<run-id>/`，包括固定计划 `plan.json`、输入预览记录 `preview_manifest.json` 和生成结果 `generated_manifest.json`。

同一批次重复运行跳过成功调用；输入或参数变化要求新批次。失败调用不自动重试，确需重试时添加 `--retry-failed`。已有不同草稿和已批准材料不会覆盖。原始回答即使被截断或未通过格式检查也保留在响应档案中，不人工修补。

大输入若发生传输超时，可在显式重试时添加 `--api-timeout 600` 延长等待，不改变输入或模型参数；实际等待设置写入各次输出记录。生成结果记录中的 `review_flags` 仅定位需要人工核查的措辞，不改原稿，不代替审核结论。

若非流式连接仍被中途断开，可添加 `--stream`。该方式保留每个原始响应片段在 `raw_response.stream_chunks` 中，按返回顺序连接content得到原始正文，并明确标记为流式拼接响应。发生中途异常时也保留已收到的片段及正文；不会自行补写。各次输入记录的transport字段记录是否流式接收及等待时限。

## 人工审核与导入

审核完整原稿，在 Excel 的“JD是否纳入”列填写1并保存（旧表为“JD”列填“通过”）。然后运行：

```powershell
# 先预览；未通过的材料不会进入导入计划
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/approve_materials.py --run-id jd_modules_20261124

.\.venv\Scripts\python.exe -X utf8 -B material_preparation/approve_materials.py --run-id jd_modules_20261124 --execute
```

导入核验草稿摘要、成功调用记录和模型原始回答一致，然后精确提取“【岗位公告开始】”和“【岗位公告结束】”之间的文字，包括原有换行，不strip、不润色。边界缺失、重复、顺序错误或区块外存在额外文字时停止。完整依据记录仍在原稿和响应中。

正式 JD 位于 `material_preparation/approved/occupations/<英文名_编码>/jd.txt`，旁边的 `jd_approval.json` 记录原稿及批准正文摘要和调用来源。未通过、不同内容冲突及被改动的材料均不擅自导入或覆盖。

## 简历生成

仅在已选职业的 JD 均在 Excel 标记通过且已完成导入后执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --count 2 --run-id resumes_four_occupations_20261123
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --count 2 --run-id resumes_four_occupations_20261123 --execute
```

使用同一结构化来源、批准的纯 JD、简历提示词和固定参考日期。每次调用一份简历。完整草稿在 `drafts/occupations/<英文名_编码>/resumes/R01.txt` 等文件，原始响应仍完整保存。

在“简历N是否纳入”列填写1并保存，再运行 `approve_materials.py --run-id <对应简历批次>` 预览或添加 `--execute` 导入。新版总表已有四份简历及独立纳入列；批准版只按下方已授权的短横线规则统一排版，原始回答完整保留。

## 离线核验

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

测试覆盖JSON完整性、来源核验、预览不调用API及不改Excel、原始换行保留、固定边界提取、审核门槛、原稿变动拒绝导入和批准内容冲突保护。既有实验和快照继续进行回归检查。

## 分级简历生成（2026-11-24）

用户明确要求：四个职业分别生成中等、低水平，每职业每水平两份，共16份。此处水平是生成目标，尚未经独立能力评分验证，不自动视作已获得3分或2分的材料。

固定规则在 `material_preparation/config/resume_levels.json`，固定模板在 `material_preparation/prompts/resume.txt`：

- 中等：本科且专业相关，3—4年相关经验，可独立完成常规任务，具备核心技能的常规应用能力，一项常规项目及基本交付。
- 低：同样本科但专业训练仅部分相关，1—2年相关经历，主要承担基础或辅助任务，仅体现部分核心技能，一项较小范围的基础贡献。保持自然、完整的简历语体，不用格式混乱、身份差异或道德缺陷制造低水平。
- 两组使用同一JD、同一栏目和相近篇幅，认知能力通过专业经历体现；正文不输出水平、评分或研究标签。R01、R02为中等目标，R03、R04为低水平目标，编号与目标水平关系保留在清单及metadata中。

本轮配置版本为 `resume_levels_fixed_dates_v2`。每份简历明确给定本科专业、教育起止年月、两段任职年月及项目年月：R01、R02分别累计40、46个月相关工作；R03、R04分别累计18、12个月。中等本科专业分别为信息安全、软件工程、统计学、信息管理与信息系统；低水平分别为电子商务、工商管理、市场营销、公共事业管理。实际发送时只加入该份简历对应的日期方案，完整配置及模板摘要记入metadata。

模型原始回答先存档，再检查编号、栏目、水平标签、专业及全部日期是否符合配置；不符合则记录失败，不写入当前草稿，也不改写回答。该校验保证明确事实的执行，不能代替对专业内容、自然性或能力水平的人工/独立评估。字数为写作目标，不以截断文本实现。

本轮直接使用用户认可的 `jd_modules_20261124` 批次原始JD。`resume_inputs.py` 核对原稿、成功响应、请求摘要后，按原有边界提取岗位公告，原样填入简历提示词。不修改Excel的“通过”记录，不写入approved；此来源模式明确记录为generated_batch，后续正式批准仍需人工审核。未显式指定 `--jd-run-id` 时，原有Excel通过及approved文件核验仍然生效。

```powershell
# 16份完整输入预览
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --levels medium low --count 2 --jd-run-id jd_modules_20261124 --run-id resumes_medium_low_dates_20261124

# 正式生成；4个独立请求并发，不共享对话历史
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --levels medium low --count 2 --jd-run-id jd_modules_20261124 --run-id resumes_medium_low_dates_20261124 --execute --stream --api-timeout 180 --concurrency 4
```

同一批次重复执行跳过成功项，失败项需显式添加 `--retry-failed`。`--count` 在指定多水平时指每水平份数；模型参数仍为deepseek-flash、temperature=1、thinking=disabled、max_tokens=3000，参考日期仍固定为2026-11-15。

原始简历存于 `drafts/occupations/<英文名_编码>/resumes/R01.txt` 至 `R04.txt`。本轮输入、原始响应及流式片段在 `results/resume_generation/<英文名_编码>/resumes_medium_low_dates_20261124/`；总体manifest和 `简历生成清单.csv` 在 `results/material_generation/resumes_medium_low_dates_20261124/`。16份均成功生成并通过原文一致性与日期规则检查。清单是程序导出索引，重跑会按记录重建，不用于填写人工审核结论。生成脚本本身不改动审核总表；四份材料的文件入口与独立纳入列见下节。

人工查看发现：当前文本为592—863字符（含英文、标点和换行），部分超过篇幅目标；少数学校或机构仍使用“某某”“××”及“虚构财经类院校”等占位表达，信息安全R01没有列出学校名称。这些原始输出均未修补，应在自然性审核时记录，而不能把日期校验成功理解为全部写作要求已通过。后续若需改善，应修改仓库提示词并另开批次重生成。

首轮 `resumes_medium_low_20261124` 产生13份成功文本、3次连接或超时失败；其中部分履历累计年限未符合生成目标。13份首轮原稿已用 `archive_resume_drafts.py --run-id resumes_medium_low_20261124 --execute` 按原始摘要核验后完整移入各职业首轮调用目录的 `raw_text/`，未手工改写或删除。对应关系与摘要保存在首轮总体目录的 `draft_archival.json`；全部首轮请求与原始响应仍在原处。当前草稿和本轮清单指向固定日期后的16份。

## 总表文件跳转与纳入列（2026-11-24）

当前审核文件仍为 `material_preparation/review/职业与材料审核.xlsx`，只保留“职业汇总”一页。按用户要求移除“人工分类”和嵌入的“简历审核”“JD原文”页。栏目顺序为职业身份、职业资料文件、是否选用，然后依次为：

- JD、JD是否纳入。
- 简历1（中等，R01）、简历1是否纳入。
- 简历2（中等，R02）、简历2是否纳入。
- 简历3（低，R03）、简历3是否纳入。
- 简历4（低，R04）、简历4是否纳入。
- 审核备注、审核人、审核日期、资料状态、来源网址；已有自定义栏保留。

材料列是文件链接，点击在默认文本编辑器中打开。相邻的“是否纳入”列独立填写：1为纳入，0为不纳入，留空为尚未审核，也可以选择待定；兼容既有“通过”值。程序不会从链接文字推断批准，也不会自动填写纳入结论。已有职业选用和人工审核值按O*NET编码迁移。职业资料文件继续使用现有工作簿跳转公式。

```powershell
# 预览，不调用模型、不修改文件
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/review_material_links.py --run-id resumes_medium_low_dates_20261124 --jd-run-id jd_modules_20261124
# 更新同一审核总表与同源CSV
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/review_material_links.py --run-id resumes_medium_low_dates_20261124 --jd-run-id jd_modules_20261124 --execute
# 核验全部文件目标、审核值和原始档案
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/review_material_links.py --run-id resumes_medium_low_dates_20261124 --jd-run-id jd_modules_20261124 --verify-only
```

原有 `review_navigation.py` 命令已转向上述入口。`export_occupation_review.py --summary-only` 识别新版总表并沿用新版布局，不恢复旧的人工分类和审核栏。

JD和简历的文件链接统一指向 `drafts/occupations/<英文名_编码>/` 中的原始生成文本。JD草稿包含依据记录；简历草稿保留模型返回的文字、序号和换行。review目录只保存审核表及审核记录，不保存、加工或另存材料正文。

`approve_materials.py` 与生成入口读取独立的“是否纳入”列，仍需显式运行导入。批准简历先核验原稿与原始响应，再逐字节复制至approved，不调整序号、不拆分段落、不重新排版；JD仍按原有固定边界提取岗位公告。旧格式表的“JD/简历N=通过”继续兼容。本轮没有批准任何材料。

后续生成的 `prompts/resume.txt` 已明确短横线规则及具体模板。16份对应的历史提示词仍完整保存在调用目录；模板变化后应另开批次生成。此次只调整排版和审核表，没有重新调用模型。`review_navigation_manifest.json` 记录源文件摘要、链接、排版副本摘要、脚本摘要和当前布局版本3。

## 三人独立审核文件

2026-11-24追加确认：现有汇总Excel完整保留，只新增个人审核文件。`review/occupation/` 和 `review/mority/` 各放审核员A、B、C三份Excel；每份只有一个“材料审核”sheet，链接使用相对文件路径，仓库换电脑后沿用同一目录关系。三人暂用A/B/C，名单和来源批次固定在 `config/human_review.json`。

```powershell
# 只预览所选材料，不写任何Excel
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/export_individual_reviews.py
# 生成或按编号/版本保留意见后刷新，不调用模型、不更新总表
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/export_individual_reviews.py --execute
```

职业范围由总表“是否选用”确定，材料须在指定批次有成功记录且与原始回答一致。个人表当前每人20项：4份JD和16份简历；不列未选中的66个职业，也不提前要求最终材料纳入字段为1。个人表不标示中等/低的预设标签，质量审核关注自然性、职业合理性、内部一致性；经验不足本身不是材料质量错误。

道德范围由配置中的 `morality_pairs` 明确选择，草稿必须有配对编号、主题和完整中性/负面正文。本轮该清单为空，草稿和批准目录均无生成正文；三份mority文件只保留模板，不把研究大纲当作生成材料。

黄色列为个人输入：审核结论（可用、需重新生成、不采用）、问题类型、问题说明、审核日期。材料身份、批次和原稿摘要保存在隐藏列。刷新按材料身份保留意见；已审核材料换版或取消选择时停止，制作期间发生的个人修改也不会被覆盖。相同材料范围、版本与链接不重复保存Excel。每个人只维护自己的两份文件，现有总表由负责人保留最终决定；此脚本不汇总意见、不批准材料、不修改任何原稿或排版副本。

职业个人表已去掉重复的“对应JD”列；同一职业的JD仍作为独立材料行，通过“材料文件”打开。旧版个人表刷新时按原字段名称迁移并保留已有审核意见，仅去掉这一列；总表与道德个人表保持不变。

`individual_review_manifest.json` 保存本次所用总表摘要、配置/脚本摘要及六份个人表的原稿来源记录。个人表链接也直接指向drafts原稿，不再依赖额外排版版本。旧表迁移时，以材料编号、批次和原稿摘要保留人工意见，移除重复的“审核文本SHA256”记录。


## 清理历史审核副本（2026-11-24）

按用户明确授权，`cleanup_review_copies.py --execute` 先把总表及个人表链接改为drafts原稿，再按生成登记逐份核验并删除16份额外的审核副本及空目录。删除范围固定为原 `material_preparation/review/resumes/`；遇到未登记文件、副本被人工改动或仍有工作簿链接依赖时停止，不递归删除其他内容。原始JD、简历、提示词、原始响应与各次调用档案全部保留。清理收据为 `review/review_copy_cleanup.json`，只记录历史删除位置和摘要，不作为运行时正文来源。

本次只修正总表的文件链接，保留其所有单元格内容、审核字段和原生设置。职业个人表保留已有人工意见，道德个人表不改动。`review_material_links.py --links-only --execute` 支持只改链接；以后正常导出、刷新和批准流程均不再创建或格式化正文副本。统一短横线应由提示词约束后续生成；已有原稿格式原样保留，需要重生成时另开批次。
