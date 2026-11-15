# 提示词使用说明

根据“实验一材料规划”的最新讨论，采用“一个任务一份完整提示词”的结构。每个文件内包含角色、规则、输入材料占位符及输出要求；程序替换变量后，以单条 `role="user"` 消息发送，不携带上一条任务的对话历史。

```text
prompts/
├── README.md
├── generation/                 材料生成
│   ├── jd.txt                  生成岗位说明
│   ├── resume.txt              生成匿名专业简历
│   └── morality.txt            生成中性/负面私人行为配对
├── validation/                 材料检验
│   ├── resume_review.txt       简历质量审读
│   ├── moral_check.txt         行为的道德属性与自然性
│   └── moral_relevance.txt     行为与具体岗位的直接专业关联
└── experiments/                实验评价
    ├── principles.txt          不含具体职业的抽象原则调查
    ├── hiring_rating.txt       基线与 A/B/C 共用招聘评价
    └── score_rubric.txt        共用的六项评分标准，注入招聘评价
```

## 固定模板与变化材料

| 文件 | 由程序填入的内容 |
|---|---|
| generation/jd.txt | 职业名称与 O*NET 编码、目标职位、公司业务、岗位层级、额外条件、职业资料 |
| generation/resume.txt | O*NET 职业资料、已批准 JD、候选人编号、参考日期 |
| generation/morality.txt | 道德主题、材料配对编号 |
| validation/resume_review.txt | JD、待审读简历 |
| validation/moral_check.txt | 单条私人行为正文，不发送中性/负面或道德基础标签 |
| validation/moral_relevance.txt | JD、单条私人行为正文，不发送内部分类标签 |
| experiments/principles.txt | 两类信息定义的顺序、两项任务的顺序、对应 JSON 输出结构 |
| experiments/hiring_rating.txt | JD、简历、背景信息段、共用评分标准 |
| experiments/score_rubric.txt | 无变量；作为原文插入 hiring_rating.txt 的 `{score_rubric}` |

同类任务跨职业、跨材料复用同一模板。更换职业或故事时，增加或替换 `materials/` 中的材料即可，不需要另存一套提示词。

A 条件的 `{background_section}` 为空；B/C 使用相同的背景调查标题和导语，只替换同一配对的中性/负面行为正文。基线与正式 A/B/C 使用相同招聘评价模板及评分标准。抽象原则调查的四种顺序由程序组装，不复制四份模板。

## 查看与修改

- `{job_description}` 等是待替换变量，不需要逐次手工填入模板。
- 模板使用 Python `str.format`：模板中要原样输出的 JSON 大括号须写成 `{{` 和 `}}`。程序填入的 JSON 结构和评分标准不会被再次格式化。
- 材料开发和预实验期间可修订模板并记录版本；正式实验同批次固定模板、评分锚点、模型及调用参数。
- 本次只把原 system 原文、空行、原 user 原文按顺序合并，没有调整研究任务措辞和评分锚点。评分标准原文保留。
- 合并改变了请求的消息角色结构，不能假定模型输出与旧版完全相同。运行时使用新的 `--run-id`；旧结果保留并标记其原配置。
- 本次没有改变 `config/settings.json` 中的模型、温度、思考模式及重复次数；参数是否统一为 1 属于另一个需要明确的实验设置决定。

在项目根目录预览（不联网、不调用 API）：

```powershell
py src/hrpilot.py run --task principles --run-id principles_merged_preview --repeat 1
py src/hrpilot.py run --task moral-generate --foundation fairness --run-id morality_merged_preview --count 1
```

预览显示的是填入变量后的完整提示词。程序仍保存实际请求内容和摘要，以便复核同批次输入。

## 原版与回退

本次整理前的 17 份提示词、程序、测试及相关说明保存在 `backups/prompts-before-merge-20261115-124023/`，`sha256.json` 记录备份内容摘要。旧提示词备份在其 `prompts/` 中，移出的原文件另存于 `original-files/`。

如需回退，应将该备份中的程序、测试、说明和原 prompts 一并恢复，避免新旧路径混用。现有材料、结果和项目外的原 ZIP 未变动。
