"""Shared reviewer identities and explicitly configured workbook filenames."""
from pathlib import Path
import re
from shared import common as c


def safe_name(name):
    if (not isinstance(name, str) or not name.strip() or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or name.strip() != name or name.endswith('.')):
        raise ValueError('审核员文件名无效')
    return name


def load_team(config):
    if config.get('review_config'):
        path = (c.ROOT / config['review_config']).resolve()
        if not path.is_relative_to(c.ROOT.resolve()):
            raise ValueError('审核配置路径超出项目目录')
        config = c.load_json(path)
    people = config.get('reviewers')
    if not isinstance(people, list) or not people or any(not isinstance(x, str) for x in people):
        raise ValueError('审核员名单必须为非空字符串列表')
    if len({x.casefold() for x in people}) != len(people):
        raise ValueError('审核员名称不能重复')
    for person in people:
        safe_name(person)
    for group, mapping in config.get('review_files', {}).items():
        if group not in ('occupation', 'mority') or not isinstance(mapping, dict) or set(mapping) != set(people):
            raise ValueError('审核文件映射必须完整对应名单：' + str(group))
        names = []
        for name in mapping.values():
            safe_name(name)
            if Path(name).suffix.lower() != '.xlsx' or Path(name).name != name:
                raise ValueError('审核文件必须为xlsx文件名')
            names.append(name.casefold())
        if len(names) != len(set(names)):
            raise ValueError('不同审核员不能共用同一文件：' + group)
    return config


def reviewer_file(team, group, person, folder):
    name = team.get('review_files', {}).get(group, {}).get(person, person + '.xlsx')
    return Path(folder) / name
