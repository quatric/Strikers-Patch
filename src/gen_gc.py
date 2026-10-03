"""Build the GameCube controller feature for one release: compile src/gc/gcpad.c for it.

Dev-time only (needs devkitPPC and your own main.dol dumps); tools/gen_prebuilt.py runs it and stores the
result in tools/prebuilt/gc_<region>.json, which is all the patcher needs.
"""
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import anchors
from layout import GC_BASE, GC_END, STATE
from ops import Feature, Hook

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
CC = DEVKIT + '/bin/powerpc-eabi-'
PLACEHOLDER = 0xD15B1ACE

# (hook name, SDK function the hook goes in, what it does)
HOOKS = (
    ('PROBE', 'WPADProbe', 'WPADProbe: SI poller, the pad as a Classic Controller'),
    ('READ', 'WPADRead', 'WPADRead: Classic Controller record from the pad'),
    ('SETFMT', 'WPADSetDataFormat', 'WPADSetDataFormat: accept a format with no Wii Remote'),
    ('FRAME', 'PadFrame', 'input manager frame update: connect a pad as a Wii Remote'),
)


def compile_hook(name, defs):
    tmp = tempfile.mkdtemp(prefix='gcpad')
    D = ['-D%s=%s' % kv for kv in defs.items()] + ['-DHOOK_' + name]
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding', '-fno-pic',
              '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall', '-Wno-unused-function', '-Werror']
    src = os.path.join(HERE, 'gc')
    subprocess.check_call([CC + 'gcc'] + cflags + D + ['-c', src + '/gcpad.c', '-o', tmp + '/g.o'])
    subprocess.check_call([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + D +
                          [src + '/hooks.S', '-o', tmp + '/h.o'])
    subprocess.check_call([CC + 'ld', '-T', src + '/link.ld', '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([CC + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    # nothing but code may be left behind: any data section would be dropped by the linker script
    sec = subprocess.run([CC + 'objdump', '-h', tmp + '/g.o'], capture_output=True, text=True).stdout
    for line in sec.splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[1].startswith(('.rodata', '.data', '.bss', '.sdata', '.sbss')) and int(parts[2], 16):
            raise SystemExit('%s: the C code needs a %s section, which cannot be injected' % (name, parts[1]))
    b = open(tmp + '/b.bin', 'rb').read()
    return list(struct.unpack('>%dI' % (len(b) // 4), b))


def input_manager(region):
    """(per-frame update, WPAD connect callback) of the game's input manager.

    The frame update polls only the channels its connect callback has enabled, and nothing enables a channel
    without a Wii Remote.  Both functions sit at a fixed distance from the first Classic Controller hook site
    (inside the pad reader that the frame update calls) in every release.
    """
    import gen_cc
    first = gen_cc.parse(os.path.join(HERE, 'cc', region + '.txt'))[0][0]
    frame = first - 0x6C - 0x5C
    return frame, frame - 0x188


def build(region, dol, ref):
    a = anchors.resolve(ref, dol)
    a['PadFrame'], connect = input_manager(region)
    defs = {
        'STATE': '0x%08Xu' % STATE,
        'SI_TYPES': '0x%08Xu' % a['SiTypes'],
        'SI_BUSY': '0x%08Xu' % a['SiBusy'],
        'SI_SHADOW': '0x%08Xu' % a['SiShadow'],
        'FN_SIGETTYPE': '0x%08Xu' % a['SIGetType'],
        'FN_OSDISABLE': '0x%08Xu' % a['OSDisableInterrupts'],
        'FN_OSRESTORE': '0x%08Xu' % a['OSRestoreInterrupts'],
        'WPAD_TBL': '0x%08Xu' % a['WpadTbl'],
        'WPAD_SHIFT': '0x%Xu' % a['WpadShift'],
        'FN_CONNECT': '0x%08Xu' % connect,
    }
    ops, cur = [], GC_BASE
    for name, fn, note in HOOKS:
        site = a[fn]
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        if orig >> 26 != 37:                                    # stwu: the SDK functions all start with one
            raise SystemExit('%s: %s starts with 0x%08X, not a stwu' % (region, fn, orig))
        w = compile_hook(name, defs)
        assert w[-1] == 0x60000000 and w[-2] == PLACEHOLDER, 'stub shape changed'
        w[-2] = orig                                            # run the displaced instruction
        w[-1] = 0                                               # the branch back, filled in on output
        ops.append(Hook(site, orig, w, cur, note=note))
        cur += (len(w) * 4 + 15) & ~15
    if cur > GC_END:
        raise SystemExit('%s: gc code overflows its window: 0x%X > 0x%X' % (region, cur, GC_END))
    return Feature('gc', 'GameCube controller', region, ops)
