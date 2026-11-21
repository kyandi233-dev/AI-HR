"""CLI for initial O*NET Details pages only; no more-link requests."""
if __name__ == '__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from material_preparation.onet_download import fetch_onet, main

if __name__ == '__main__':
    raise SystemExit(main())
