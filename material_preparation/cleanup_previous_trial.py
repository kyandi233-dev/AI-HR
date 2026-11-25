"""Remove only the explicitly rejected earlier software trial, preserving API logs."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path
from shared import common as c
from material_preparation.onet_data import digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    prep = c.ROOT/'material_preparation'
    note_path = prep/'sources/occupations/software_developer/onet/material_preparation_record.json'
    if not note_path.exists():
        print('旧试稿已清理，或不存在对应记录。')
        return
    note = c.load_json(note_path)
    expected = {
        prep/'approved/occupations/software_developer/onet/profile.txt': note['profile_sha256'],
        prep/'approved/occupations/software_developer/jd.txt': note['jd_preparation']['jd_sha256'],
    }
    for rid, info in note['resume_preparation']['outputs'].items():
        expected[c.ROOT/info['path']] = info['sha256']
    candidates = []
    for path, sha in expected.items():
        if path.exists():
            if digest(path) != sha:
                raise ValueError(f'旧试稿已被修改，不自动删除：{path}')
            candidates.append(path)
    for name, task, run in [('jd.txt', 'jd_generation', 'software_jd_draft_20261121'),
                             ('resumes/R01.txt', 'resume_generation', 'software_resumes_draft_20261121'),
                             ('resumes/R02.txt', 'resume_generation', 'software_resumes_draft_20261121')]:
        path = prep/'drafts/occupations/software_developer'/name
        if not path.exists():
            continue
        tid = 'JD01' if name == 'jd.txt' else Path(name).stem
        output = c.load_json(prep/'results'/task/'software_developer'/run/'records'/(tid+'_a01.output.json'))
        if path.read_text(encoding='utf-8') != output['answer']:
            raise ValueError(f'原草稿已被修改，不自动删除：{path}')
        candidates.append(path)
    candidates.append(note_path)
    # Validate every exact file target before any deletion; no recursive delete or directory move.
    for path in candidates:
        path.resolve().relative_to(prep.resolve())
        if not path.is_file():
            raise ValueError(f'Not a file: {path}')
    for path in candidates:
        print('删除：' if args.execute else '预览删除：', path.relative_to(c.ROOT))
    if args.execute:
        manifest = {'deleted_utc': c.now(), 'files': [str(p.relative_to(c.ROOT)) for p in candidates],
                    'preserved': ['original source HTML/TXT/metadata', 'original API inputs and outputs'],
                    'reason': 'User explicitly rejected the prior trial materials'}
        for path in candidates:
            path.unlink()
        from shared import material_results as mr
        base=mr.batch_root('jd','software_jd_draft_20261121')
        data=mr.info(base);data['previous_trial_cleanup']=manifest;mr.write(base/mr.INFO,data)


if __name__ == '__main__':
    main()
