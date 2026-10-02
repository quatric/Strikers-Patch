"""Build the Classic Controller feature for one release from Vague Rant's code (src/cc/<region>.txt).

His Gecko codes are used word for word: every C2 becomes a Hook (a trampoline in the injected section that runs
his code and branches back), so the three outputs (patched DOL, Gecko, Riivolution) all carry exactly his code.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
from layout import CC_BASE, CC_END
from ops import Feature, Hook


def parse(path):
    return parse_text(open(path).read(), path)


def parse_text(text, path='<text>'):
    lines = [l.split() for l in text.splitlines()[1:] if l.strip()]
    out, i = [], 0
    while i < len(lines):
        head, n = lines[i]
        if not head.startswith('C2'):
            raise SystemExit('%s: only C2 codes are expected, found %s' % (path, head))
        n = int(n, 16)
        words = []
        for row in lines[i + 1:i + 1 + n]:
            words += [int(x, 16) for x in row]
        out.append((0x80000000 | (int(head[2:], 16) & 0x01FFFFFF), words))
        i += 1 + n
    return out


def build(region, dol):
    ops, cur = [], CC_BASE
    for site, words in parse(os.path.join(HERE, 'cc', region + '.txt')):
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        if words[-1] != 0:
            raise SystemExit('%s: C2 at %08X does not end with the branch-back slot' % (region, site))
        ops.append(Hook(site, orig, words, cur, note='Classic Controller (Vague Rant)'))
        cur += (len(words) * 4 + 15) & ~15
    if cur > CC_END:
        raise SystemExit('%s: cc code overflows its window: 0x%X > 0x%X' % (region, cur, CC_END))
    return Feature('cc', 'Classic Controller', region, ops)
