# JD 与简历生成

本文档规定岗位说明（JD）与候选人简历的来源输入、提示词规范、**简历能力水平操控条件（简历操作）**、程序校验、人工审核与正式导入流程。生成风格与结构化控制参照 Kim 等（ACL 2025）与 PopResume（EMNLP 2026），并与下游实验 3 的评分维度保持严格对应。

---

## 1. 核心文件与提示词索引

点击下表链接可直接跳转对应提示词、配置与脚本：

| 类别 | 文件路径（点击跳转） | 作用说明 |
|---|---|---|
| **JD 生成提示词** | [material_preparation/prompts/jd.txt](../material_preparation/prompts/jd.txt) | 将 O*NET 职业资料转换为标准中文社招 JD（含 5 年门槛与加分项）及依据记录 |
| **简历生成提示词** | [material_preparation/prompts/resume.txt](../material_preparation/prompts/resume.txt) | 按给定槽位与能力档位生成极简词条风格的匿名求职简历 |
| **简历审读提示词** | [material_preparation/prompts/resume_review.txt](../material_preparation/prompts/resume_review.txt) | 检查简历自然度、时间线自洽性、占位词残留及无关品格标签 |
| **下游评分标准** | [experiments/exp_3_hiring/prompts/score_rubric.txt](../experiments/exp_3_hiring/prompts/score_rubric.txt) | 实验 3 的四项专业能力评分尺（1–5 分）与招聘推荐指标 |
| **简历操控配置** | [material_preparation/config/resume_levels.json](../material_preparation/config/resume_levels.json) | 全员统一校企集合、固定时间线、中/低两档操控规则及各职业技术栈槽位 |
| **JD 输入模块配置** | [material_preparation/config/jd_input_modules.json](../material_preparation/config/jd_input_modules.json) | 固定读取的 O*NET 九个模块清单 |
| **职业登记表** | [material_preparation/config/occupations.json](../material_preparation/config/occupations.json) | 候选职业的内部键、O*NET 编码与来源网址 |
| **模型运行配置** | [material_preparation/config/settings.json](../material_preparation/config/settings.json) | 默认模型（`deepseek-flash`）、温度（`1.0`）、`thinking=disabled` 与参考日期 |
| **人工审核配置** | [material_preparation/config/human_review.json](../material_preparation/config/human_review.json) | 四名独立审核成员名单（`gsc`、`lkx`、`lxy`、`wjy`）及工作簿文件名映射 |
| **生成与校验脚本** | [generation_inputs.py](../material_preparation/generation_inputs.py) · [generate_jd.py](../material_preparation/generate_jd.py) · [generate_resumes.py](../material_preparation/generate_resumes.py) · [resume_inputs.py](../material_preparation/resume_inputs.py) | O*NET 模块投影、JD 提取核验、简历槽位组装与硬性输出校验 |
| **批次与审核入口** | [run_material_generation.py](../material_preparation/run_material_generation.py) · [approve_materials.py](../material_preparation/approve_materials.py) · [review_material_links.py](../material_preparation/review_material_links.py) · [export_individual_reviews.py](../material_preparation/export_individual_reviews.py) | 请求预览与执行、批准材料提取导入、审核总表链接维护与四人审核表导出 |

---

## 2. 职业资料来源与输入预处理条件

1. **职业范围确定**：[run_material_generation.py](../material_preparation/run_material_generation.py) 读取 `material_preparation/review/职业与材料审核.xlsx` 的“职业汇总”页，以“是否选用”列填 `1`（或`选用`）确定生成范围。当前选定 4 个职业：
   - 信息安全分析师（`Information Security Analysts`，`15-1212.00`）
   - 软件开发工程师（`Software Developers`，`15-1252.00`）
   - 数据科学家（`Data Scientists`，`15-2051.00`）
   - 商业智能分析师（`Business Intelligence Analysts`，`15-2051.01`）
2. **原始存档校验**：读取各职业目录下的 `onet/structured_en.json`，先校验职业编码及 `stored_html_sha256` 与原始网页存档完全一致，不依赖手工 `profile.txt`。
3. **九个固定模块**：由 [jd_input_modules.json](../material_preparation/config/jd_input_modules.json) 指定读取 `Overview`、`Tasks`、`Detailed Work Activities`、`Job Zone`、`Software Skills`、`Knowledge`、`Education`、`Essential Skills`、`Transferable Skills`。
4. **JD 与简历的差异化输入投影**：
   - **JD 生成输入**：完整保留上述九个模块的全部记录与 `source_text`，仅剔除网页链接、控件及完全重复的展示字段，将逐条映射关系记入请求 `metadata.input_projection`。
   - **简历生成输入**：为消除约 1.5 万 Token 英文分类表对中文简历语体的干扰，[generate_resumes.py](../material_preparation/generate_resumes.py) 仅从同一结构化数据中提取前 10 条核心工作任务（`Tasks`）供业务真实性参考，同时在 `metadata` 中完整保留 `structured_sha256` 与 `jd` 摘要溯源。

---

## 3. 岗位说明（JD）操作条件

具体提示词见 [prompts/jd.txt](../material_preparation/prompts/jd.txt)，提取与初筛规则见 [generation_inputs.py](../material_preparation/generation_inputs.py)。

- **结构与篇幅**：岗位公告全文控制在 `240—350字`，固定包含 5 个栏目：
  1. `职位名称`：标准中文岗位名称，不添加初级/高级职级、公司名或细分行业背景。
  2. `岗位简介`：1—2 句话（`45—75字`）概括核心职能。
  3. `工作职责`：从 `Tasks` 与 `Detailed Work Activities` 提炼 `5—6条` 主要工作，统一以 `- ` 开头，每条 `14—24字`，一条只写一件事。
  4. `任职要求`：写 `5条` 以 `- ` 开头的词条（每条 `12—28字`），依次覆盖：学历与对口专业类别（取 `Education` 最高占比层次）、**`5年以上相关工作经验`**（统一设定）、常用语言/工具简称与专业方法（2 条）、问题分析与方案评估认知能力（1 条）。
  5. `加分项`：从进阶工具或细分技术中选取 `2—3条` 优先条件，以 `- ` 开头，每条 `10—22字`。
- **梯度留白设计**：将 JD 硬性年限设为 `5年以上` 并单列 `加分项`，使 `3—4年` 经验、掌握常规核心工具但不含高阶加分栈的中等水平候选人无需刻意自我贬低，即可自然落在“基本胜任但未触顶”区间。
- **术语转换与排除边界**：
  - 将英文分类名称转换为通用中文行业术语，不生硬直译学科分类名，不照抄过长的商业软件套件全称；若资料已含特定语言框架或数据库（如 `PyTorch/TensorFlow`、`PostgreSQL`），可并列写出对应基础语言简称（`Python`、`SQL`）并在依据记录注明。
  - **品格与社会性技能排除**：任职要求与加分项严禁写入诚信、沟通、合作、共情、协调、责任心等品格或人际要求；正文不出现 O*NET 栏目名或统计比例。
- **固定输出区块与无损提取**：模型依次输出 `【依据记录开始】…【依据记录结束】` 与 `【岗位公告开始】…【岗位公告结束】` 两个区块。批准导入时，`extract_jd` 原字节提取岗位公告区块（不润色、不改换行），`review_flags` 自动扫描任职要求及加分项是否混入排除词汇供人工核查。

---

## 4. 简历操作（能力水平操控与常量控制规则）

具体提示词见 [prompts/resume.txt](../material_preparation/prompts/resume.txt)，结构化参数见 [config/resume_levels.json](../material_preparation/config/resume_levels.json)（版本 `resume_levels_unified_pool_v4`），组装与校验见 [generate_resumes.py](../material_preparation/generate_resumes.py) 与 [resume_inputs.py](../material_preparation/resume_inputs.py)。

### 4.1 总体操控原则

每个选用职业生成 **4 份简历**：`R01`、`R02` 为**中等水平**目标，`R03`、`R04` 为**低水平**目标（4 个职业共 16 份）。单次模型调用独立生成 1 份简历。能力差异完全通过客观履历事实（专业对口度、相关工龄与职级、任务独立性、技术掌握深度）呈现：
- 不在简历正文出现任何水平标签（如“中等水平”“低水平”“普通合格”“能力较低”）；
- 不用错别字、版式混乱、时间矛盾、身份差异或道德缺陷来制造低水平；
- 校名、企业名、学历层次、经历段数、项目时长和目标字数在所有候选人之间严格保持恒定。

### 4.2 全员固定常量（消除非目标混淆）

| 控制项 | 全员统一设定 | 控制目的 |
|---|---|---|
| **身份与联系方式** | 仅保留编号 `R01—R04`，头部固定为 `邮箱：aaaaa@example.com｜电话：138-0000-0000` | 排除姓名、性别、年龄、地域及人口学代理线索 |
| **毕业院校** | 统一固定为 **`明远大学`**（本科学历；多学历扩展备选 `海川大学`） | 消除院校声望差异及“某某大学/××学院”占位词 |
| **任职企业集合** | 按工作段数统一从有序集合 **`["星河信息技术有限公司", "辰光科技有限公司", …]`** 顺序取用（第1段早年经历统一为`星河信息技术有限公司`，第2段近期经历统一为`辰光科技有限公司`） | 消除企业名声望、行业字面暗示差异及“某公司”占位词 |
| **版式与篇幅** | 全文 `260—360字`；固定顺序为倒序`工作经历`（2段×2条 `- ` 短句）→ `项目经历／代表性工作成果`（1项×2条 `- ` 短句）→ `教育背景` → `专业技能`（2—3条分类词条） | 消除排版质量与文本长度对能力评分的干扰 |
| **参考基准日期** | `2026-11-15`（所有经历使用明确起止年月，禁用“至今”） | 保证工龄核算精确一致 |

### 4.3 四维能力水平操控条件（对应实验 3 四项能力评分）

| 操控维度（对应 [score_rubric.txt](../experiments/exp_3_hiring/prompts/score_rubric.txt)） | 中等水平（`R01`、`R02`） | 低水平（`R03`、`R04`） |
|---|---|---|
| **一、教育与岗位匹配** | **核心对口本科专业** ＋ 列出 3—4 门核心专业课程名称 | **弱相关商管类本科专业** ＋ 仅列 2—3 门基础导论或通识工具课 |
| **二、相关工作经历**（对照 JD 5年门槛） | **累计 40 个月（`R01`）/ 46 个月（`R02`）**（约 3.3—3.8 年）；职级从`初级/助理工程师`正常晋升至`正式工程师/分析师`；独立完成日常模块开发、常规建模或标准运维，不承担架构主导或团队管理 | **累计 18 个月（`R03`）/ 12 个月（`R04`）**（1—1.5 年）；岗位为`实习生/文员` → `助理`；仅从事数据录入核对、按清单巡检、套用模板或辅助测试，不独立负责核心模块 |
| **三、专业技能** | 采用 `类别：工具或方法（掌握程度）` 格式；覆盖岗位常规核心工具（标`熟练`/`常规应用`），**留白 JD 中的加分项与高阶工具** | 采用同一格式；仅含办公软件与少量外围工具，明确标注`入门`/`基础语法`/`简单查询`/`套用模板`，缺少岗位核心技术栈 |
| **四、项目／代表性工作成果** | 固定期间 `2026.06—2026.08`；1 项常规业务项目，分 2 条说明具体技术实现动作与可用交付物（不编造百分比业绩） | 固定期间 `2026.06—2026.08`；1 项小范围辅助支持工作，分 2 条说明按指导完成的基础整理动作与辅助记录文档交付 |

### 4.4 固定时间线参数

- **`R01`（中等，累计 40 个月）**：教育 `2019.09—2023.06`；工作段1 `2023.07—2024.12`，工作段2 `2025.01—2026.10`；项目 `2026.06—2026.08`。
- **`R02`（中等，累计 46 个月）**：教育 `2018.09—2022.06`；工作段1 `2023.01—2024.06`，工作段2 `2024.07—2026.10`；项目 `2026.06—2026.08`。
- **`R03`（低水平，累计 18 个月）**：教育 `2020.09—2024.06`；工作段1 `2025.05—2025.12`，工作段2 `2026.01—2026.10`；项目 `2026.06—2026.08`。
- **`R04`（低水平，累计 12 个月）**：教育 `2020.09—2024.06`；工作段1 `2025.11—2026.04`，工作段2 `2026.05—2026.10`；项目 `2026.06—2026.08`。

### 4.5 四个试点职业的专业、岗位演进与差异化技术栈分配

为防止同一职业下的多份简历逐句照搬 JD 或彼此雷同，[resume_levels.json](../material_preparation/config/resume_levels.json) 按编号预绑定了岗位演进与技术范围：

| 职业 | 编号（水平） | 本科专业 | 岗位演进（早年 → 近期） | 指定技术范围 |
|---|---|---|---|---|
| **软件开发工程师** | `R01`（中） | 软件工程 | 初级后端开发工程师 → 软件开发工程师 | Python（熟练）、JavaScript（基础）、SQL；RESTful API、PostgreSQL、Git（熟练）、Docker（基础） |
| | `R02`（中） | 软件工程 | 助理软件开发工程师 → 软件开发工程师 | Java（常规应用）、SQL；Spring Boot、MySQL、Git（熟练）、Jenkins（基础部署） |
| | `R03`（低） | 工商管理 | IT技术支持实习生 → 软件开发助理 | Python（基础语法）、HTML/CSS（入门）；PostgreSQL（简单查询）、Git（基础提交） |
| | `R04`（低） | 工商管理 | 信息系统运维实习生 → 初级软件测试助理 | JavaScript（入门）、SQL（简单查询）；功能测试记录、Git（查看记录）、Excel |
| **数据科学家** | `R01`（中） | 统计学 | 助理数据分析师 → 数据科学家 | Python（熟练）、SQL（熟练）；Scikit-learn（回归与树模型）、Pandas、Tableau、Git |
| | `R02`（中） | 统计学 | 数据分析师 → 数据建模工程师 | Python（常规应用）、R（基础）、SQL；PyTorch（基础）、Power BI、PostgreSQL |
| | `R03`（低） | 市场营销 | 市场调研数据实习生 → 数据分析助理 | Excel（数据透视表）、SPSS（基础描述统计）；SQL（简单查询）、Power BI（套用模板） |
| | `R04`（低） | 市场营销 | 运营数据录入专员 → 初级数据支持助理 | Excel（常规函数与清洗）、Python（入门脚本）；SAS（基础操作） |
| **信息安全分析师** | `R01`（中） | 信息安全 | 助理安全运维工程师 → 信息安全分析师 | 防火墙访问策略维护、访问权限审计、Linux基础；Splunk（日志检索）、漏洞扫描工具（常规核查） |
| | `R02`（中） | 信息安全 | 网络安全专员 → 信息安全分析师 | TCP/IP基础、Wireshark（抓包分析）、入侵告警初筛；系统基线核查、应急演练记录 |
| | `R03`（低） | 电子商务 | IT机房巡检实习生 → 信息安全运维助理 | 终端杀毒软件状态巡检、账号权限台账整理；Wireshark（基础查看）、Excel |
| | `R04`（低） | 电子商务 | 信息系统行政助理 → 初级安全合规助理 | 访问申请工单流转、安全培训记录归档；Splunk（按固定模板导出）、Office套件 |
| **商业智能分析师** | `R01`（中） | 信息管理与信息系统 | 初级数据报表专员 → 商业智能分析师 | SQL（熟练编写查询与视图）、Excel（高级函数）；Power BI（常规仪表板开发与维护）、业务指标梳理 |
| | `R02`（中） | 信息管理与信息系统 | 运营数据分析员 → 商业智能分析师 | SQL（常规提取与聚合）、Python（基础数据清洗）；Tableau（可视化看板制作）、月度财务与市场报表 |
| | `R03`（低） | 公共事业管理 | 商务统计实习生 → 数据报表助理 | Excel（常规图表与汇总）、Power BI（日常数据源刷新）；SQL（基础单表查询） |
| | `R04`（低） | 公共事业管理 | 销售运营数据文员 → 初级业务数据助理 | Excel（基础函数与台账核对）、ERP业务报表常规导出、字段口径登记 |

> 未在 `occupation_slots` 单独列出的其余候选职业，自动继承同一套统一校企集合、时间线及通用职级演进（中等：`初级专员 → 业务专员`；低水平：`业务实习生 → 基础支持助理`）。

### 4.6 输出强校验条件

模型返回文本后，先原样保存原始响应，再由 [resume_inputs.py](../material_preparation/resume_inputs.py) 的 `validate_resume_text` 执行硬性检查：
1. 必须包含 `教育背景`、`工作经历`、`项目经历`、`专业技能` 四个栏目，且前 100 字符内包含正确的 `{resume_id}`；
2. 不得出现 `中等水平`、`低水平`、`普通合格`、`能力较低` 等水平控制词；
3. 不得出现 `某某`、`××`、`某公司`、`某大学`、`某学院`、`某信息`、`某网络`、`某科技`、`XX公司`、`XX大学` 等模糊占位词；
4. 独立提取各栏目后，校验教育起止年月与本科专业、两段工作起止年月（兼容倒序排列，且不含“至今”）、项目起止年月与配置完全一致。任一条件不满足则记为生成失败，不写入草稿文件。

---

## 5. 运行命令、审核工作流与材料导入

所有命令均在**项目根目录**下执行。默认不加 `--execute` 时仅生成完整提示词与请求预览，不调用模型、不改动任何现有草稿或审核表。

### 5.1 生成 JD 与简历

```powershell
# 1. 预览 JD 请求（不调用模型）
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task jd --run-id <新JD批次号>

# 2. 执行 JD 生成（若已有旧版草稿，须先用 remove_jd_drafts.py 归档清理）
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task jd --run-id <新JD批次号> --execute --stream --api-timeout 600

# 3. 预览 16 份分级简历请求（可绑定指定 JD 批次，或省略 --jd-run-id 直接使用已批准导入的 JD）
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --levels medium low --count 2 --jd-run-id <JD批次号> --run-id <新简历批次号>

# 4. 执行 16 份简历生成（4 并发独立无状态调用；若已有旧草稿，须先用 archive_resume_drafts.py 归档）
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/run_material_generation.py --task resume --levels medium low --count 2 --jd-run-id <JD批次号> --run-id <新简历批次号> --execute --stream --api-timeout 180 --concurrency 4
```

- **不可变与断点续跑**：同一 `run_id` 重复执行自动跳过已成功项；失败项须显式加 `--retry-failed` 重试；更改提示词、配置或参数必须更换新的 `--run-id`。
- **存档位置**：草稿位于 `material_preparation/drafts/occupations/<英文名_编码>/`（`jd.txt` 与 `resumes/R01.txt—R04.txt`）；完整提示词、请求与流式原始响应位于 `material_preparation/results/jd_generation/`、`resume_generation/` 及 `material_preparation/results/material_generation/<run-id>/`。

### 5.2 审核总表与四人独立审核表

```powershell
# 更新总表（职业与材料审核.xlsx）的材料文件链接
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/review_material_links.py --run-id <简历批次号> --jd-run-id <JD批次号> --execute

# 刷新四名成员（gsc、lkx、lxy、wjy）的个人审核表（按材料编号与原稿版本保留已有意见）
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/export_individual_reviews.py --execute
```

- **个人审核表**：位于 `material_preparation/review/occupation/`（`JD+resume_gsc.xlsx`、`lJD+resume_kx.xlsx`、`JD+resume_lxy.xlsx`、`JD+resume_wjy.xlsx`），盲去预设水平标签，仅审读自然性、职业合理性与内部一致性（低档简历经验浅属于设计目标，不计作质量错误）。
- **总表最终决定**：位于 `material_preparation/review/职业与材料审核.xlsx`，“JD是否纳入”“简历1是否纳入—简历4是否纳入”填 `1` 表示批准纳入，`0` 表示不纳入。

### 5.3 批准导入与离线测试

```powershell
# 预览并导入总表中已标记纳入（=1）的 JD 或简历至 approved/
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/approve_materials.py --run-id <对应生成批次号>
.\.venv\Scripts\python.exe -X utf8 -B material_preparation/approve_materials.py --run-id <对应生成批次号> --execute

# 运行全套离线回归与校验测试（不消耗 API）
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

导入时先核验草稿字节摘要与成功调用原始响应一致：JD 精确提取 `【岗位公告开始】` 与 `【岗位公告结束】` 之间的正文写入 `material_preparation/approved/occupations/<英文名_编码>/jd.txt`，简历逐字节原样复制至 `approved/occupations/<英文名_编码>/resumes/`，并在旁生成 `*_approval.json` 溯源收据。历史批次（如 `jd_modules_20261124`、`resumes_medium_low_dates_20261124`）的原始请求、响应及归档记录均完整保留在 `results/` 对应目录备查。
