# DeepSeek HR：可复用实验任务包 v1.0

本项目是**程序与 Prompt 框架**，不是已经完成的数据集。四个职业只是旧方案里的候选项（可删换）；**没有导入历史生成的 Python 后端 JD 和 R01–R04**，也没有任何默认通过审核的道德故事。运行前必须从 O*NET 重新准备职业资料。

## 0. 研究流程

职业材料：`O*NET 源页面 → 人工检查并存储职业资料 → 生成 JD 草稿 → 审核批准 JD → 独立生成简历草稿 → 审核批准简历 → A 基线筛选`。

私人材料：`六大道德主题 → 生成中性/负面配对草稿 → 人工审核 → 道德属性评定 → 各职业的直接专业关联评定 → 冻结材料`。

独立的抽象原则调查：`两类信息定义 + 两个一般招聘任务 → 四种顺序平衡 × 独立重复`。**此任务没有职业、没有 JD、没有简历。**

正式招聘：`每职业 × 每份批准简历 × A / 配对B / 配对C → 六项评分 + 自发的简短理由`。B/C 的差异只来自背景行为正文。

## 1. 任务文件夹

```text
config/
  occupations.json               四个候选职业及 O*NET 编码（可以调整）
  settings.json                  唯一 API 参数配置源
prompts/
  README.md                       提示词入口、变量与使用规则
  generation/                     材料生成：jd.txt / resume.txt / morality.txt
  validation/                     材料检验：resume_review.txt / moral_check.txt / moral_relevance.txt
  experiments/                    实验评价：principles.txt / hiring_rating.txt / score_rubric.txt
materials/
  occupations/
    software_developer/
      onet/                       原始 O*NET 抓取、人工核对的 profile.txt
      job_setup.json              公司业务和岗位层级设定（需要填写）
      jd/                         draft.txt / approved.txt
      resumes/drafts/             自动生成草案 R01.txt ...
      resumes/approved/           研究者确认的正式简历
    business_intelligence/        同上
    customer_service/             同上，是否适合排除社会性技能需进一步审议
    logistics_analyst/            同上
  morality/
    drafts/                       尚未审核的配对背景故事 JSON
    approved/                     研究者审核后方可进入材料检验及 A/B/C
results/
  principles/         4种顺序平衡的独立结果
  morality/moral-generate/       道德故事生成记录
  morality/moral-check/          道德效价、基础分类、自然性、可理解性
  software_developer/
    jd_generation/                JD 生成记录
    resume_generation/            简历生成记录
    resume_review/                简历文本审核记录
    moral_relevance/              与本职业 JD 的专业关联检查
    baseline/                     A 评分（材料筛选）
    abc/                          A/B/C 正式评价（各职业分开）
  ...                             其他职业同结构
src/hrpilot.py                    唯一运行入口
```

对不同任务使用独立 `run-id`；每批保存到一个 `<run-id>/` 目录，所有独立对话集中写入 `requests.jsonl`、`responses.jsonl`、`records.jsonl`，通过 `task_id` 和 `attempt` 关联。保留完整请求、原始回复、解析结果、模型与配置元数据；不为每次对话创建文件夹。

每项任务的角色、规则、材料占位符和输出要求均在同一份模板内。模板跨职业复用，具体材料由 Python 填入；评分标准单独保存，由程序注入招聘评价模板。详见 `prompts/README.md`。

## 2. Windows / PowerShell 初次安装

1. 解压 ZIP 到一个路径尽量简短的目录，如 `D:\Research\DeepSeek_HR_Framework`。
2. 在该文件夹地址栏输入 `powershell` 回车。
3. 检查 Python：

```powershell
py --version
```

4. 安装依赖（只需要一次）：

```powershell
py -m pip install -r requirements.txt
```

5. 从 https://platform.deepseek.com/ 获取 API Key。每次打开新的 PowerShell 会话时输入（密钥不会出现在已保存的代码文件里）：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host "DeepSeek API Key"
```

**不要发送 API Key 给他人，不要将其写入 Word 或 CSV，不要上传到代码仓库。**

程序**默认仅预览，不发送请求，也不计费**；只有命令最后有 `--execute` 时，才会真实访问 DeepSeek API（`fetch-onet` 的 `--execute` 仅抓取 O*NET）。

## 3. 第一个可以立即测试的功能：抽象原则调查

原则调查不需要任何岗位材料。打开终端，运行：

```powershell
py src/hrpilot.py status
py src/hrpilot.py run --task principles --run-id principles_pilot01 --repeat 1
```

第二行只打印准备发送的四个独立 Prompt 的摘要和第一条 Prompt；没有费用。

实际执行（四条 API 请求）：

```powershell
py src/hrpilot.py run --task principles --run-id principles_pilot01 --repeat 1 --execute
```

若先测试其中一条，可先用 `--limit 1 --execute`，再执行不带 limit 的相同命令；成功记录会跳过，不重复计费。

四个条件：M12、M21、A12、A21（M=道德信息先定义；A=能力信息先定义；12=任务一先；21=任务二先）。都包含两个任务。每个任务使用一份完整提示词，所有调用只发当前一条 user 消息，绝不回传上一次会话历史。

结果位于 `results/principles/principles_pilot01/`。

这里的 `run-id` 表示整批实验，`M12_T01` 是 JSONL/CSV 中的单次测量编号。每条回复同时包含两个问题的答案。新批次推荐命名为 `20261116_principles_pilot_02`（UTC 日期、任务、阶段、同日批次序号）；CSV 文件名为 `20261116_principles_pilot_02.csv`。详细规则见 `docs/数据字段.md`。`--repeat N` 对每个条件独立重复 N 次，共 4N 次请求；同一批次续跑跳过成功记录。旧逐次目录用 `python src/hrpilot.py migrate-results` 备份并迁移，不会重新调用模型。

## 4. 四职业资料准备（每个职业独立执行）

职业候选项在 `config/occupations.json`。默认有：

- `software_developer`：15-1252.00
- `business_intelligence`：15-2051.01
- `customer_service`：43-4051.00
- `logistics_analyst`：13-1081.02

先只测试一个职业时，使用：

```powershell
py src/hrpilot.py fetch-onet --occupation software_developer
py src/hrpilot.py fetch-onet --occupation software_developer --execute
```

程序仅访问 `https://www.onetonline.org/link/details/15-1252.00`，下载页面原始 HTML、文字及来源时间/摘要。若网站限制自动请求，则从该**官方网站**人工复制职业条目。

**必须人工查看** `materials/occupations/software_developer/onet/source_details.txt`，将与职业有关的 Tasks、Detailed Work Activities、Knowledge、专业技能、Education、Job Zone 等选入 `onet/profile.txt`。`profile.txt` 为人工认可的职业信息，程序不会自动把整个网页当成已验证材料。

在 `materials/occupations/software_developer/job_setup.json` 填入 `company_profile` 和 `job_level`，并审查 `job_title`。

预览 JD 生成 Prompt：

```powershell
py src/hrpilot.py run --task jd --occupation software_developer --run-id jd_dev01
```

实际生成 1 份 JD 草稿：

```powershell
py src/hrpilot.py run --task jd --occupation software_developer --run-id jd_dev01 --execute
```

在 `jd/draft.txt` 中会看到含「依据记录」和「岗位公告」的结果。人工核对后**只把岗位公告部分**复制到 `jd/approved.txt`。其他资料不能直接进入招聘评价。

## 5. 生成简历（每次调用仅生成一份，独立会话）

```powershell
py src/hrpilot.py run --task resume --occupation software_developer --count 4 --run-id resume_dev01
py src/hrpilot.py run --task resume --occupation software_developer --count 4 --run-id resume_dev01 --limit 2 --execute
py src/hrpilot.py run --task resume --occupation software_developer --count 4 --run-id resume_dev01 --limit 4 --execute
```

生成的文本在 `resumes/drafts/R01.txt` ...。第二次会跳过已成功的 R01/R02；`--limit` 指按固定清单取前 N 项，不是额外增加 N 项。

可先审读草稿：

```powershell
py src/hrpilot.py run --task resume-review --occupation software_developer --run-id review_dev01
py src/hrpilot.py run --task resume-review --occupation software_developer --run-id review_dev01 --limit 4 --execute
```

人工审核后将符合条件的草稿复制到 `resumes/approved/`。如不改变内容即可原样复制。**不要先按评分调节简历以诱导 3 分。**

## 6. 生成并审核私人道德材料

以公平/欺骗主题为例：

```powershell
py src/hrpilot.py run --task moral-generate --foundation fairness --count 2 --run-id moral_fairness01
py src/hrpilot.py run --task moral-generate --foundation fairness --count 2 --run-id moral_fairness01 --execute
```

输出草稿存于 `materials/morality/drafts/FAIRNESS_001.json` 等；每个 JSON 有 `pair_id`、`foundation`、`neutral`、`negative`。人工检查、修订后复制到 `materials/morality/approved/`。后台的标签不发送给招聘评价模型。

道德效价/基础分类/自然性等通用预检：

```powershell
py src/hrpilot.py run --task moral-check --run-id moralcheck01
py src/hrpilot.py run --task moral-check --run-id moralcheck01 --limit 4 --execute
```

如已有批准 JD，可分职业判断背景行为是否直接提供该职位的专业能力证据：

```powershell
py src/hrpilot.py run --task moral-relevance --occupation software_developer --run-id relevance_dev01 --limit 4 --execute
```

两种预检均只发送行为原文，不发送它的 `neutral`/`negative`/道德基础标签。

## 7. 简历 A 基线评分与 A/B/C

基线评分需要通过审核的 `jd/approved.txt` 和 `resumes/approved/RXX.txt`：

```powershell
py src/hrpilot.py run --task baseline --occupation software_developer --run-id baseline_dev01 --repeat 2
py src/hrpilot.py run --task baseline --occupation software_developer --run-id baseline_dev01 --repeat 2 --limit 4 --execute
```

先导结果合格、材料冻结后，正式 A/B/C：

```powershell
py src/hrpilot.py run --task abc --occupation software_developer --run-id abc_dev01 --repeat 1
py src/hrpilot.py run --task abc --occupation software_developer --run-id abc_dev01 --limit 6 --execute
```

默认每条命令最多允许 12 次真实请求，以防误操作造成大额账单。完成一部分后可以使用更大的 `--limit` 续跑。需要做更多任务请在明确预算和批次数量后修改 `config/settings.json` 的 `max_requests_per_command`，最好仍保持小批次执行。

> **重要**：如果同一 run-id 中曾经执行过任务，再修改 Prompt、参数、JD、简历、道德故事或程序，重新运行会因 SHA256 不一致而拒绝继续。应该新建一个 run-id。不要删除旧数据或覆盖旧记录。

## 8. 导出数据与排查

```powershell
py src/hrpilot.py export
```

得到 `results/all_results.csv`（全部批次，供 Excel 查看），以及各批次目录下的 `<run-id>.csv`（仅该批次，一次独立调用尝试一行）。同批次分次续跑的记录仍汇入同一份批次表；同时保留各职业、各任务的独立原始记录。

常见失败：
- 提示“缺少必要文件”：相应材料尚未由研究者审核并放入 `approved`。
- HTTP 401：API Key 无效；402：API 余额不足；429：达到速率限制。
- 输出不是 JSON 或字段不合法：原始回复和失败状态均保存，不会视为有效数据。需单独检查 Prompt 或手动发起明确的重试，保留失败记录。
- 访问 O*NET 失败：手工从官方网站整理资料，不让模型自行捏造来源。

## 9. 官方依据与技术边界

- DeepSeek API：https://api-docs.deepseek.com/api/create-chat-completion/
- 思考模式：https://api-docs.deepseek.com/guides/thinking_mode/
- JSON Output：https://api-docs.deepseek.com/guides/json_mode/
- O*NET：https://www.onetonline.org/

当前模型名示例：`deepseek-flash`；参数配置明确 `thinking=disabled`、评价任务 `temperature=0`。**即使温度为 0，也不能保证重复调用逐字一致**。DeepSeek 思考模式默认启用，思考模式中的 temperature 不生效，因此在请求中显式关闭思考模式。API 返回 `system_fingerprint` 时连同模型名、Prompt、时间、配置和原始响应一起保存。

运行前请阅读 `docs/研究协议与限制.md` 和 `docs/数据字段.md`。实际调用会消耗 API 余额，项目打包时没有执行任何真实 DeepSeek 请求。
