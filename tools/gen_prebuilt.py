#!/usr/bin/env python3
"""Dev-time: regenerate tools/prebuilt/<feature>_<region>.json from src/ and your own retail main.dol dumps.

    STRIKERS_DOLS=/dir/with/R4QE01.dol,R4QJ01.dol,R4QP01_rev1.dol,R4QP01_rev2.dol python3 tools/gen_prebuilt.py

Needs devkitPPC for the GameCube controller hooks.  End users never run this: the patcher reads the JSON.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
import features
from dol import Dol
from regions import REGIONS

import gen_cc
import gen_gc


def dol_for(region):
    base = os.environ.get('STRIKERS_DOLS', os.path.join(HERE, '..', 'dumps', 'dols'))
    p = os.path.join(base, region + '.dol')
    if not os.path.exists(p):
        sys.exit('set STRIKERS_DOLS to a directory holding %s.dol' % region)
    return Dol(p)


def main():
    os.makedirs(features.PREBUILT, exist_ok=True)
    ref = dol_for('R4QE01')
    for region in REGIONS:
        dol = dol_for(region)
        if len(dol.data) != REGIONS[region]['dol_size']:
            sys.exit('%s: main.dol is %d bytes, expected %d' % (region, len(dol.data), REGIONS[region]['dol_size']))
        for name, feat in (('cc', gen_cc.build(region, dol)), ('gc', gen_gc.build(region, dol, ref))):
            path = os.path.join(features.PREBUILT, '%s_%s.json' % (name, region))
            with open(path, 'w') as f:
                json.dump(features.dump(feat), f, indent=1)
                f.write('\n')
            print('wrote', os.path.relpath(path), sum(len(o.payload) * 4 for o in feat.ops), 'bytes of code')


if __name__ == '__main__':
    main()
