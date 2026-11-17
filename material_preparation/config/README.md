# 参数与职业登记

- **生成参数：** generation，temperature=1、thinking=disabled、max_tokens=3000。
- **审核参数：** material_review，temperature=1、thinking=disabled、max_tokens=1600。
- **并发数：** settings.json中的concurrency，默认1；命令行可用 `--concurrency` 覆盖。
- **职业登记：** occupations.json；每批通过occupations选择职业。
- **批次计划：** task、run_id、stage、repeat、count、start_index、source、foundation、occupations、profile_overrides、concurrency。
- **材料版本：** 实验2、3的计划另含materials_version。
- **参数优先级：** 命令行选项 → 批次计划 → settings默认值。
- **模型覆盖：** profile_overrides可覆盖model、temperature、thinking、max_tokens。
- **本次执行数量：** `--limit` 指定待运行试次中的本次份数。
- **请求超时：** api_timeout_seconds，当前120秒。
