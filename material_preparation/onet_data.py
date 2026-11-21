"""Shared source paths and source bookkeeping; no model calls."""
import hashlib
import json
import re
from pathlib import Path
from shared import common as c


def directory_name(info):
    name = re.sub(r'[^A-Za-z0-9]+', '_', info['onet_name']).strip('_')
    return f"{name}_{info['onet_code']}"


def source_folder(info):
    return c.ROOT / 'material_preparation/sources/occupations' / directory_name(info) / 'onet'


def read_registry():
    registry = c.load_json(c.occupations_file())
    codes = [v['onet_code'] for v in registry.values()]
    if len(codes) != len(set(codes)):
        raise ValueError('Duplicate O*NET occupation code')
    return registry


def select_occupations(registry, occupation=None, all_occupations=False):
    if all_occupations:
        return list(registry.items())
    if occupation not in registry:
        raise ValueError('Unknown occupation; select --occupation or --all')
    return [(occupation, registry[occupation])]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(folder):
    meta = c.load_json(folder / 'source_metadata.json')
    verification = {}
    for name, key in [('source_details.html', 'sha256_html'), ('source_details.txt', 'sha256_text')]:
        path = folder / name
        actual = digest(path)
        if actual == meta[key]:
            verification[name] = 'bytes'
        elif 'scope' not in meta and c.sha256(path.read_text(encoding='utf-8')) == meta[key]:
            # Legacy Windows write_text translated LF to CRLF after calculating digests.
            # Verify that exact legacy behavior, without changing source bytes/metadata.
            verification[name] = 'legacy_windows_newline_normalization'
        else:
            raise ValueError(f'Source digest mismatch: {path}')
    meta = {**meta, 'verification': verification,
            'stored_html_sha256': digest(folder / 'source_details.html')}
    return meta
