# 材料准备

## 1. 任务范围

当前全职业抓取、原文规范化及Excel/CSV审核表的命令与边界见 [O*NET职业资料整理](../docs/O-NET职业资料整理.md)。此阶段不需要API密钥，也不执行下述材料生成阶段。

本模块负责为招聘评价实验建立可追溯的岗位、简历和私人行为材料，不直接执行 A/B/C 招聘评分。

- **职业来源**：基于 O*NET 职业资料，保留下载原文、来源信息及人工审核后的专业资料。
- **岗位描述（JD）**：读取约定的职业模块，按已确认的学历、经验和写作规则生成，人工审核后固定；不额外设定公司背景或岗位层级。
- **匿名简历**：围绕同一 JD 生成中等、低水平两类候选人材料，以教育、经验、技能和成果范围控制生成目标，不预置已验证的能力分数。
- **私人行为故事**：按六类道德基础生成中性/负面配对摘要，避免直接描述职业技能和工作绩效。
- **质量审核**：检查专业材料的自然性、合理性与一致性，以及行为材料的道德属性与可理解性；结果供人工筛选。

研究变量、预设材料范围与 A 条件预评估的关系见[研究设计](../docs/研究设计.md)。

## 2. 材料流程

1. **登记与整理职业**：确认 `config/occupations.json`，保存原始页面并解析为完整的 `structured_en.json`。
2. **选择职业与预览输入**：在审核表“是否选用”填写1或“选用”，通过 `run_material_generation.py` 保存各职业完整输入预览。不再要求 `profile.txt` 或 `job_setup.json`。
3. **生成与批准 JD**：生成包含依据记录的完整草稿；人工在审核总表“JD是否纳入”列填 `1`，再由 `approve_materials.py --run-id <批次号> --task jd` 精确提取岗位公告至批准目录。
4. **生成与审核简历**：读取对应职业的核心任务与批准 JD（或通过 `--jd-run-id` 明确绑定已生成的 JD 批次原稿，不代填批准记录），按预设时间线与能力档位生成匿名简历。在审核总表“简历1是否纳入—简历4是否纳入”列填 `1` 后，由 `approve_materials.py --run-id <批次号> --task resume` 原字节导入批准目录。
5. **生成与审核行为故事**：建立包含 `pair_id`、`foundation`、`neutral`、`negative` 的故事对，审查后批准。
6. **交付实验材料**：由实验2、3各自的 `snapshot_materials.py` 复制固定版本；不直接将草稿作为正式实验输入。

当前候选清单保留23个职业大类、70个职业；不按沟通、照护等要求提前排除职业。其状态以 `config/occupations.json` 和实际材料为准。

新版 JD/简历的规则、保存路径及执行命令见 [JD与简历生成](../docs/JD与简历生成.md)。新版材料目录使用英文职业名加 O*NET 编码；既有实验快照仍兼容原来的内部键，不迁移或改写历史材料。

当前审核总表只有“职业汇总”一页，JD和四份简历各配独立“是否纳入”列（1纳入、0不纳入、留空待审），不再设置人工分类。材料列直接打开drafts中的原始文本；简历1/2为中等，3/4为低水平。刷新入口为 `review_material_links.py`，原 `review_navigation.py` 亦转向此入口。只更新链接时使用 `--links-only --execute`，不改总表单元格内容或审核意见。

四名成员为gsc、lkx、lxy、wjy，名单和实际文件名统一在`config/human_review.json`维护。职业个人表位于`review/occupation/`，沿用`JD+resume_gsc.xlsx`、`lJD+resume_kx.xlsx`、`JD+resume_lxy.xlsx`、`JD+resume_wjy.xlsx`；道德个人表位于`review/mority/`，沿用`moral_<成员>.xlsx`。职业个人表当前每人20项（4份JD、16份简历）；道德表当前每人268个待生成任务，正文和评分为空。

运行`export_individual_reviews.py --execute`刷新四份职业个人表，不加参数只预览；道德四份个人表及道德总表由`export_morality_review.py`刷新，两者均不调用模型。每人只改自己的黄色审核列。程序按材料编号和版本保留意见；已审核材料换版或移除时停止覆盖。职业个人表范围、版本、链接和标题未变时不重写；道德总表刷新时读取四人结论，最终纳入仍由负责人确认。

`review`只存审核表和审核记录，正文统一来自drafts。已按用户授权删除16份额外排版副本，相关导出、刷新及批准脚本不再创建或加工副本。简历批准时逐字节复制原稿；JD批准时只执行约定的岗位公告边界提取。短横线等格式要求由提示词约束后续生成，已有原始回答不改动。清理脚本为 `cleanup_review_copies.py`，收据记录在 `review/review_copy_cleanup.json`。

个人表的“职业资料”复用总表的 `workbook_jump_formula`，通过 `CELL("filename",A1)` 动态拼接相对于当前工作簿所在目录的本地路径，直接打开目标 `职业资料.xlsx` 的 `Overview!A1`；JD／简历文本使用正斜杠 `/` 相对文件链接；道德汇总表与道德个人表直接在表内并列展示`负面版本`与`中性版本`正文，不另建外部阅读文件。移动仓库或组员 `git clone` 到其他电脑后无需重跑脚本即可直接查看或跳转；如需对旧职业表做局部链接升级，可运行 `export_individual_reviews.py --links-only --execute`，保留现有排版和审核值。

当前四份JD与十六份分级简历位于 `results/occupation_generation/20261125_012`，按职业配套。道德当前批次位于 `results/morality_generation/20261124_004`，268项尚未执行。每批只有一份“批次信息.json”和“调用清单.csv”，单次调用只保存input／output；具体读取方法和历史迁移说明见[材料生成记录](../docs/材料生成记录.md)。历史原始回答和已有草稿保持原文，不代填审核结论、不自动放入approved。

职业个人表固定显示A至E列，包括“材料类型”和“材料文件”；横向滚动只移动F列及其后的内容，避免JD／简历链接被遮住。`--links-only --execute`也可局部修正旧文件的冻结位置。

## 3. 程序入口

| 文件 | 任务 |
|---|---|
| `fetch_occupations.py` | 下载 O*NET 职业网页并记录来源；不自动批准 |
| `generate_jd.py` | 生成目标岗位描述 |
| `generate_resumes.py` | 生成与 JD 匹配的匿名简历 |
| `run_morality_generation.py` | 按MFV来源与固定协议构造全量输入，显式执行后生成配对摘要 |
| `export_morality_review.py` | 按共享名单汇总来源、生成状态及四名成员的独立审查资料 |
| `generate_morality.py` | 旧版按主题自由起草的兼容入口；新材料使用上述来源驱动流程 |
| `review_resumes.py` | 审核简历自然性、专业合理性及时间线 |
| `review_morality.py` | 辅助审核道德故事文本 |

- **职业登记**：`config/occupations.json`。
- **默认模型参数**：`config/settings.json`。
- **提示词**：`prompts/jd.txt`、`resume.txt`、新版 `morality_pool.txt` 及相应审核模板。
- **草稿**：`drafts/occupations/<职业ID>/`、`drafts/morality/`。
- **批准材料**：`approved/occupations/<职业ID>/`、`approved/morality/`。
- **生成与审核记录**：`results/`。

## 4. 当前实现的边界

道德材料的定义、MFV编制标准、固定prompt、命令与审核文件见[道德情境编制方案](../docs/道德情境编制方案.md)。新版默认包含116条MFV道德情境×2种改写及36项规则新编，共268个待生成任务（当前冻结于 `results/morality_generation/20261124_004`，支持按 `--foundation` 分维度执行生成）。个人道德表由 `export_morality_review.py` 维护，职业个人表导出器不会覆盖这些文件。

- **简历质量评分**：`naturalness` 和 `professional_plausibility` 属于材料审核指标，不等同于模型的专业能力评价。能力预评估可调用实验3的 `baseline`。
- **审核与测量**：`review_morality.py` 与实验2的道德属性评价目前采用相同的测量提示词；两份结果不能视为独立评价方法。
- **材料批准**：程序校验基本文件与字段，材料的职业适切性和最终纳入仍需人工决定。
- **编号管理**：重复生成相同材料编号可能触发草稿冲突；不得覆盖或混用旧版本。
- **运行方式**：通用命令、批次参数及异常处理统一参见[运行指南](../docs/运行指南.md)。
