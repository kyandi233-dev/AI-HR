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
            route = (
                '改编变体1（贴近原场景迁移）：保留原条目的核心人际关系与活动类型，直接转换为成年候选人的日常私人场景（若原条目为校园或职场，仅将人物身份与场所替换为对等的业余或私人生活场景）。'
                if variant == 1 else
                f'改编变体{variant}（跨场域迁移）：保留原条目的核心违规机制，但不得沿用原条目的具体活动与场所，必须切换到另一类日常私人生活场域（如亲友聚餐、社区邻里、日常消费、业余社团或结伴出游）。'
            )
            specs.append({'pair_id': f"{item['foundation'].upper()}_{number:05}",
                          'foundation': item['foundation'], 'source_kind': 'mfv_adaptation',
                          'source_id': item['source_id'], 'variant': variant, 'source': item,
                          'route': route})
    for foundation in c.FOUNDATIONS:
        axes = protocol['foundations'][foundation]['novel_axes']
        for index in range(config['novel_per_foundation']):
            specs.append({'pair_id': f'{foundation.upper()}_{90001 + index:05}',
                          'foundation': foundation, 'source_kind': 'principle_extension',
                          'source_id': None, 'variant': index + 1, 'source': None,
                          'axis': axes[index % len(axes)],
                          'route': f'规则新编（第{index + 1}项）：围绕指定场景方向，独立构造一件成年候选人的日常私人事件。'})
    if not specs or len({x['pair_id'] for x in specs}) != len(specs):
        raise ValueError('生成任务为空或编号重复')
    return specs


def format_foundation_rules(info):
    return '\n'.join([
        f"- 主题：{info['label']}",
        f"- 概念定义：{info['definition']}",
        f"- MFV操作化边界：{info['author_operationalization']}",
        f"- 本研究迁移要求：{info['project_adaptation']}",
    ])


def format_source_material(spec):
    if spec['source']:
        src = spec['source']
        return '\n'.join([
            f"- 原条目子类别：{src['source_category_label']}",
            f"- 英文原文：{src['original_en']}",
            f"- 中文参考译文：{src['translation_zh']}",
            f"- 原版错误程度均值（0–4）：{src['wrongness_mean_0_4']}",
        ])
    return f"- 新编场景方向：{spec['axis']}"


def build_tasks(config_path=None):
    config, protocol, catalog, fingerprints = load_inputs(config_path)
    tasks = []
    for spec in build_specs(config, protocol, catalog):
        foundation = spec['foundation']
        prompt = c.render(config['prompt'], pair_id=spec['pair_id'], foundation=foundation,
                          generation_route=spec['route'],
                          foundation_rules=format_foundation_rules(protocol['foundations'][foundation]),
                          author_rules='\n'.join('- ' + x for x in protocol['author_general_rules']),
                          study_rules='\n'.join('- ' + x for x in protocol['study_rules']),
                          source_material=format_source_material(spec))
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
