"""Dev-time: load retail main.dol files into a private Ghidra project and analyse them.

    GHIDRA_INSTALL_DIR=/Applications/ghidra_12.1.2_PUBLIC python3 tools/dev/ghidra_import.py dumps/dols/R4QE01.dol ...

Builds the program from the DOL section table (so no GUI loader dialog), using
the Gekko/Broadway language, then runs the auto-analysis and saves it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dol import Dol

import pyghidra

pyghidra.start()

from ghidra.program.database import ProgramDB
from ghidra.program.model.lang import LanguageID
from ghidra.util.task import TaskMonitor
from java.io import ByteArrayInputStream
from ghidra.program.util import DefaultLanguageService

PROJ_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'dumps', 'ghidra'))
LANG = 'PowerPC:BE:32:Gekko_Broadway:default'


def main(paths):
    from ghidra.base.project import GhidraProject
    os.makedirs(PROJ_DIR, exist_ok=True)
    try:
        proj = GhidraProject.openProject(PROJ_DIR, os.environ.get('GHIDRA_PROJ', 'StrikersDols'), True)
    except Exception:
        proj = GhidraProject.createProject(PROJ_DIR, os.environ.get('GHIDRA_PROJ', 'StrikersDols'), False)
    from ghidra.program.util import DefaultLanguageService
    lang = DefaultLanguageService.getLanguageService().getLanguage(LanguageID('PowerPC:BE:32:Gekko_Broadway'))
    cspec = lang.getDefaultCompilerSpec()
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        d = Dol(p)
        prog = ProgramDB(name, lang, cspec, proj)
        tx = prog.startTransaction('load')
        mem = prog.getMemory()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        for off, addr, size, idx in d.secs:
            blk = mem.createInitializedBlock('%s_%d' % ('text' if idx < 7 else 'data', idx),
                                             space.getAddress(addr), ByteArrayInputStream(bytes(d.data[off:off + size])),
                                             size, TaskMonitor.DUMMY, False)
            blk.setExecute(idx < 7)
            blk.setWrite(True)
        # the header's bss range also covers the SDA data sections: fill only the gaps
        cur, end, n = d.bss_addr, d.bss_addr + d.bss_size, 0
        for _o, a, sz, _i in sorted(d.secs, key=lambda s: s[1]):
            if a + sz <= cur or a >= end:
                continue
            if a > cur:
                mem.createUninitializedBlock('bss_%d' % n, space.getAddress(cur), a - cur, False); n += 1
            cur = max(cur, a + sz)
        if cur < end:
            mem.createUninitializedBlock('bss_%d' % n, space.getAddress(cur), end - cur, False)
        prog.getSymbolTable().addExternalEntryPoint(space.getAddress(d.entry))
        prog.endTransaction(tx, True)
        print('analysing', name, flush=True)
        pyghidra.analyze(prog)
        proj.saveAs(prog, '/', name, True)
        print('saved', name, flush=True)
        proj.close(prog)
    proj.close()


if __name__ == '__main__':
    main(sys.argv[1:])
