"""Shared column names and inclusion semantics for reviewer files."""
LINK_COLUMNS=['JD','简历1（中等）','简历2（中等）','简历3（低）','简历4（低）']
APPROVAL_COLUMNS=['JD是否纳入']+[f'简历{i}是否纳入' for i in range(1,5)]
HEADERS=['大类编码','Job Family','Occupation','O*NET Code','职业资料文件','是否选用',
         *[name for pair in zip(LINK_COLUMNS,APPROVAL_COLUMNS) for name in pair],
         '审核备注','审核人','审核日期','资料状态','来源网址']


def is_approved(value):
    return str(value).strip() in ('1','1.0','通过','纳入','是','True')


def approval_value(row,material):
    key=material+'是否纳入'
    return row.get(key) if key in row else row.get(material)
