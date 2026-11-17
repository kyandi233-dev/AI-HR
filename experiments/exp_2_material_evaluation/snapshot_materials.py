"""Save this experiment's fixed material version; preview by default."""
import sys
from pathlib import Path
if __name__=='__main__' and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from shared.materials import snapshot_main

if __name__=='__main__':
    sys.exit(snapshot_main('exp_2_material_evaluation'))
