"""Source-grounded, deterministic morality candidate plans and response validation."""
import re
from pathlib import Path
from shared import common as c

DEFAULT_CONFIG = 'material_preparation/config/morality_generation.json'


def project_file(value):
    path = (c.ROOT / value).resolve()
    if not path.is_relative_to(c.ROOT.resolve()):
        raise ValueError('输入文件必须位于项目目录：' + str(value))
    return path


def load_inputs(config_path=None):
    config_path = Path(config_path) if config_path else c.ROOT / DEFAULT_CONFIG
    config = c.load_json(config_path)
    files = {name: project_file(config[name]) for name in ('protocol', 'catalog', 'prompt')}
    protocol, catalog = c.load_json(files['protocol']), c.load_json(files['catalog'])
    for name in ('variants_per_mfv', 'novel_per_foundation'):
        value = config[name]
        if type(value) is not int or not 0 <= value <= (99 if name == 'variants_per_mfv' else 999):
            raise ValueError(name + '必须是范围内的整数')
    if type(config['include_nonrecommended']) is not bool:
        raise ValueError('include_nonrecommended必须为布尔值')
    if set(protocol['foundations']) != set(c.FOUNDATIONS):
        raise ValueError('协议必须包含六类主题')
    ids = [item['source_id'] for item in catalog['items']]
    if len(ids) != len(set(ids)):
        raise ValueError('来源编号重复')
    fingerprints = {name + '_sha256': c.sha256(path.read_bytes()) for name, path in files.items()}
    return config, protocol, catalog, fingerprints


def build_specs(config, protocol, catalog):
    specs = []
    for item in catalog['items']:
        if not item['use_as_seed']:
            continue  # Original non-moral norm controls remain in the source catalog.
        if not item['recommended'] and not config['include_nonrecommended']:
            continue
        for variant in range(1, config['variants_per_mfv'] + 1):
            number = item['library_item_number'] * 100 + variant
            specs.append({'pair_id': f"{item['foundation'].upper()}_{number:05}",
                          'foundation': item['foundation'], 'source_kind': 'mfv_adaptation',
                          'source_id': item['source_id'], 'variant': variant, 'source': item,
                          'route': ('保留原条目的关系结构与违规机制，迁移为自然的成人私人事件。' if variant == 1 else
                                    f'变体{variant}：探索另一种具体日常活动或关系设定，保留违规机制；不得只换措辞。')})
    for foundation in c.FOUNDATIONS:
        axes = protocol['foundations'][foundation]['novel_axes']
        for index in range(config['novel_per_foundation']):
            specs.append({'pair_id': f'{foundation.upper()}_{90001 + index:05}',
                          'foundation': foundation, 'source_kind': 'principle_extension',
                          'source_id': None, 'variant': index + 1, 'source': None,
                          'axis': axes[index % len(axes)],
                          'route': f'依据定义与作者编写规则新编第{index + 1}个事件；不得声称是原MFV条目。'})
    if not specs or len({x['pair_id'] for x in specs}) != len(specs):
        raise ValueError('生成任务为空或编号重复')
    return specs


def build_tasks(config_path=None):
    config, protocol, catalog, fingerprints = load_inputs(config_path)
    tasks = []
    for spec in build_specs(config, protocol, catalog):
        foundation = spec['foundation']
        if spec['source']:
            source_material = c.canonical({'source': spec['source'],
                                          'identifier_note': catalog['provenance']['identifier_note'],
                                          'source_correction': catalog['provenance']['correction'],
                                          'evidence_note': catalog['provenance']['evidence_note']})
        else:
            source_material = c.canonical({'new_event_direction': spec['axis'],
                                          'source_note': '依作者规则新编；无对应原条目及原版评分。'})
        prompt = c.render(config['prompt'], pair_id=spec['pair_id'], foundation=foundation,
                          generation_route=spec['route'],
                          foundation_rules=c.canonical(protocol['foundations'][foundation]),
                          author_rules='\n'.join('- ' + x for x in protocol['author_general_rules']),
                          study_rules='\n'.join('- ' + x for x in protocol['study_rules']),
                          source_material=source_material)
        metadata = {'pair_id': spec['pair_id'], 'foundation': foundation,
                    'generation_protocol': protocol['protocol_version'], **fingerprints,
                    'spec': spec}
        tasks.append(c.new_task('moral-generate', spec['pair_id'], prompt, metadata, True))
    return config, protocol, catalog, tasks


def validate_generated(parsed, task):
    if parsed.get('pair_id') != task['task_id'] or parsed.get('foundation') != task['metadata']['foundation']:
        raise ValueError('返回的材料编号或主题与请求不符')
    if parsed.get('status') not in ('generated', 'not_adaptable'):
        raise ValueError('status必须为generated或not_adaptable')
    for key in ('other_foundations', 'review_flags'):
        if not isinstance(parsed.get(key), list) or any(not isinstance(x, str) for x in parsed[key]):
            raise ValueError(key + '必须为字符串列表')
    if any(x not in c.FOUNDATIONS for x in parsed['other_foundations']):
        raise ValueError('存在无效的其他主题代码')
    if parsed['status'] == 'not_adaptable':
        if not isinstance(parsed.get('rejection_reason'), str) or not parsed['rejection_reason'].strip():
            raise ValueError('不适配必须说明原因')
        if parsed.get('negative') or parsed.get('neutral'):
            raise ValueError('不适配记录不能包含伪正文')
        return
    for key in ('negative', 'neutral', 'scene_summary', 'dominant_violation', 'adaptation_note', 'neutral_rationale'):
        if not isinstance(parsed.get(key), str) or not parsed[key].strip():
            raise ValueError('生成材料缺少非空字段：' + key)
    if re.sub(r'\s+', '', parsed['neutral']) == re.sub(r'\s+', '', parsed['negative']):
        raise ValueError('中性和负面正文完全相同')

