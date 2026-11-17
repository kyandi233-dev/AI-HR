# 参数、职业库和批次

- settings.json：共用API参数；generation生成材料，evaluation用于原则/基线/A/B/C，material_review用于材料检验。
- occupations.json：职业登记与O*NET来源。新增职业登记一次；本批不选的职业不必删除。status只是备注。
- batches/*.json：本次做什么、选哪些职业、重复多少次。principles_100.json可直接预览；hiring_example.json需要先准备批准材料。

批次计划支持 task、run_id、stage、repeat、count、start_index、source、foundation、occupations、profile_overrides。命令行显式给出的同名选项优先。profile_overrides可覆盖本批model/temperature/thinking/max_tokens；不会修改共用settings。

max_requests_per_command=null：不另设12次上限，发送数量由明确的实验计划限定。可选--limit限制本次新发送数。thinking=enabled时需从共用配置中删除该配置组的temperature字段。

批次开始后修改输入/参数/顺序/执行协议需另建run-id；批次保存实际使用的快照，不随以后职业库增减而改写旧记录。
