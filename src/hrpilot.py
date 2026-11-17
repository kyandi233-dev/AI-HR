#!/usr/bin/env python3
"""Compatibility entry point; implementation lives in hrpilot_core."""
import sys
from hrpilot_core.cli import main

if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('失败：',exc,file=sys.stderr)
        sys.exit(2)
