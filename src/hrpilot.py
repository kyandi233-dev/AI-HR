#!/usr/bin/env python3
"""Compatibility entry point; experiment scripts use the shared runtime."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.cli import main

if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('失败：',exc,file=sys.stderr)
        sys.exit(2)
