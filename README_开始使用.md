# AI-HR 实验任务包

这个项目负责将固定提示词、材料、条件和模型参数组成独立 API 请求，再保存输入、原始回答和可分析的数据。它不自动判断材料是否合格，也不自动完成统计推断。

**每个试次都使用独立新对话：只发送本次一条完整 user 消息，不带任何历史。** 原则实验每次回答两题；四个条件是四次独立请求。安排发送先后不会把多个试次合并为一个对话。

## 1. 当前进度

截至 2026-11-17，仓库中的四个职业（软件开发、商业智能分析、客户服务、物流分析）只是候选登记，尚无保存的 O*NET 原始抓取、人工审核 profile、批准 JD 或简历。

已有原则流程预实验 `20261116_principles_pilot_02`：四个条件各一次，共四次成功。原始请求、响应和原时间均保留；目录整理不代表新运行。

此次更新没有执行新的 DeepSeek 实验，也没有新增职业抓取。

## 2. 安装与入口

本地建议放在 `D:\_Experiment\AI-HR`，避免同步盘占用。打开 PowerShell：

```powershell
Set-Location "D:\_Experiment\AI-HR"
py -m pip install -r requirements.txt
py src/hrpilot.py status
```

`src/hrpilot.py` 是保留的命令入口。默认仅预览，只有 `run ... --execute` 才发送模型请求并产生费用。`fetch-onet ... --execute` 下载 O*NET 网页，不调用模型。

## 3. 原则实验：一次启动100个独立试次

计划文件为 `config/batches/principles_100.json`：

```json
{
  "task": "principles",
  "run_id": "20261117_principles_main_01",
  "stage": "main",
  "repeat": 25,
  "occupations": []
}
```

`repeat=25` 表示每个条件25次，总共100次调用。每次包含 task1 专业能力判断和 task2 面试推荐判断，两题属于同一条回复。

| 条件 | 定义顺序 | 问题顺序 |
|---|---|---|
| M12 | 道德→能力 | 任务一→任务二 |
| M21 | 道德→能力 | 任务二→任务一 |
| A12 | 能力→道德 | 任务一→任务二 |
| A21 | 能力→道德 | 任务二→任务一 |

计划按25轮安排，每轮四个条件各一次，轮内顺序由 run-id 确定。每一项仍是独立新对话。原则调查不读取任何职业、JD、简历或道德故事。

预览（不发送 API，也不创建结果文件）：

```powershell
py src/hrpilot.py run --batch config/batches/principles_100.json
```

参数在 `config/settings.json` 的 `profiles.evaluation`，当前仍为 `deepseek-flash`、temperature=0、thinking=disabled、max_tokens=2200。尚未替研究者选定温度1。先确定参数，再正式收集；如要改成本批温度1，可在批次 JSON 中增加 `"profile_overrides": {"temperature": 1.0}`。生成材料和审核材料分别使用其他配置组。

决定执行后，在终端设置密钥，然后运行：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host "DeepSeek API Key"
py src/hrpilot.py run --batch config/batches/principles_100.json --execute
```

不需要按12次分组。程序会逐条发送全部未完成项；`max_requests_per_command=null` 表示不设置额外请求数量上限，数量由批次计划限定。若自己设置了整数上限，则程序检查本次实际新发送数。

如需暂停后继续，执行相同命令。成功项跳过；失败或中断项默认也不自动重发，避免不明确的再次收费。检查后可添加 `--retry-failed` 明确重试，保留旧尝试。可选 `--limit 10` 表示本次最多新发送10次，续跑会继续后面的未完成项；通常不必使用。

同批次的提示词、材料、参数、计划顺序及执行协议必须一致。更改这些内容使用新 run-id。只改 CSV 显示不会阻止续跑。不要同时启动多个进程写同一批次。

## 4. 输出：每个输入、输出分别一份JSON

```text
results/principles/20261117_principles_main_01/
  batch.json
  M12_T01_a01.input.json
  M12_T01_a01.output.json
  ...
  results.csv
```

- `batch.json`：本批参数、顺序、全部试次输入摘要和执行协议版本。
- `*.input.json`：完整提示词、条件、参数、编号、时间，不含密钥。
- `*.output.json`：完整 API 原始响应、逐字回答、校验后的答案、状态及错误、模型和用量。网络失败时原始响应为 null。
- `a01` 表示第一次尝试；手动重试另建 `a02`，不覆盖第一次。
- `results.csv`：每次调用尝试一行，原答案字段展开为普通列。成功100次且无重试时100行；有失败重试时会多出尝试行，分析按 status=ok 筛选并保留试次标识。

CSV保留批次、阶段、条件、重复、发送序号、请求/返回模型、温度、thinking、max_tokens、时间、状态、token用量和两题全部答案。哈希、SDK版本等审计细节放在 JSON。两个问题仍对应同一次调用，不应当作两次独立会话。

实验运行结束自动导出，也可手动：

```powershell
py src/hrpilot.py export --task principles
```

总表按任务分别保存，例如 `results/principles/principles_all_results.csv`、`results/baseline/baseline_all_results.csv`、`results/hiring_abc/hiring_abc_all_results.csv`。不同实验不会混进同一张总表；同一实验的不同职业和批次通过 occupation、run_id、stage 区分。总表包含历史失败尝试，不会因再次 export 追加重复行。

旧批次的 JSONL 和旧格式文件经逐条核对后保留在该批次的 `legacy/` 中；新的逐次 JSON 由原对象转换，不重新调用模型。尚未转换的本地旧数据运行：

```powershell
py src/hrpilot.py migrate-results
```

## 5. 职业资料与批次选择

`config/occupations.json` 是职业登记表，不是本批必须全部运行的名单。新增职业登记一次；本批不做某职业，无需删除其登记或历史材料。status 字段只是备注，不自动决定是否参与。

职业的材料放在 `materials/occupations/<职业ID>/`：

```text
onet/source_details.html        官方网页原文
onet/source_details.txt         提取后的网页文字
onet/source_metadata.json       来源URL、时间、摘要；不代表审核通过
onet/profile.txt               研究者从来源中审核、选择的职业资料
job_setup.json                 研究者提出的公司、细分岗位和层级设定
jd/draft.txt                   生成的JD草稿
jd/approved.txt                批准的岗位公告
resumes/drafts/R01.txt          简历草稿
resumes/approved/R01.txt        批准的简历
```

职业选择写在批次 JSON 的 occupations 列表中；`config/batches/hiring_example.json` 展示选择两个职业的 A/B/C 批次。它需要先准备批准材料，目前不能直接运行。也可用旧命令一次选择一个职业：`--occupation software_developer`。

准备流程：

1. 从 O*NET 下载原文；不把模型编造的信息当成职业来源。
2. 人工核对 Tasks、Detailed Work Activities、Knowledge、专业技能、Education、Job Zone 等，选入 profile.txt。
3. 填写并审核 job_setup.json，根据固定职业资料生成 JD 草稿。
4. 核对后只将岗位公告放入 jd/approved.txt。
5. 依据资料和批准 JD 独立生成简历，审核后放入 approved。
6. 准备并审核道德配对故事，再做基线、材料检验和 A/B/C。

示例命令默认预览，添加 --execute 才实际下载或调用：

```powershell
py src/hrpilot.py fetch-onet --occupation software_developer
py src/hrpilot.py run --task jd --occupation software_developer --run-id jd_dev01
py src/hrpilot.py run --task resume --occupation software_developer --count 4 --run-id resume_dev01
py src/hrpilot.py run --task resume-review --occupation software_developer --run-id review_dev01
py src/hrpilot.py run --task moral-generate --foundation fairness --count 2 --run-id moral_fairness01
py src/hrpilot.py run --task moral-check --run-id moralcheck01
py src/hrpilot.py run --task moral-relevance --occupation software_developer --run-id relevance_dev01
py src/hrpilot.py run --task baseline --occupation software_developer --run-id baseline_dev01 --repeat 2
py src/hrpilot.py run --task abc --occupation software_developer --run-id abc_dev01
```

道德故事放在 `materials/morality/drafts/`，审核后放入 `approved/`；每个 JSON 含 pair_id、foundation、neutral、negative。招聘评价只收到行为正文，不收到内部中性/负面/道德基础标签。材料生成、材料审核、原则、基线、A/B/C 分别建批次；不得用筛选数据代替正式数据。

## 6. 程序和测试

```text
src/hrpilot.py                     保留的命令入口
src/hrpilot_core/cli.py            命令与批次计划
src/hrpilot_core/experiments/      原则、招聘实验的任务构造
src/hrpilot_core/material_tasks/   材料生成、审核
src/hrpilot_core/api.py            独立API调用
src/hrpilot_core/storage.py        逐次JSON、失败与续跑
src/hrpilot_core/batch.py          固定本批输入及执行协议
src/hrpilot_core/exports.py        批次CSV和各实验总表
src/hrpilot_core/migration.py      旧数据转换与原文件保留
src/hrpilot_core/onet.py           职业来源抓取
src/hrpilot_core/validation.py     回答合法性检查
```

运行离线程序检查：

```powershell
py -m unittest discover -s tests -v
```

测试使用临时材料和模拟 API，验证新会话、条件、100次存档、续跑、失败重试、CSV、旧数据转换及来源文件保存，不访问外网、不产生模型费用。测试通过不等于材料合格或研究结论成立。

研究边界见 `docs/研究协议与限制.md`；字段详见 `docs/数据字段.md`。
