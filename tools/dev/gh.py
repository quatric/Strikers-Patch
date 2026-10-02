"""Dev-time: query the analysed Ghidra projects built by ghidra_import.py.

    python3 tools/dev/gh.py R4QE01 dec 0x803D4F80          decompile the function containing an address
    python3 tools/dev/gh.py R4QE01 dis 0x803D4F80 [n]      disassemble n instructions from an address
    python3 tools/dev/gh.py R4QE01 xref 0x803D4F80         references to an address
    python3 tools/dev/gh.py R4QE01 str "WPAD"              defined strings containing text
    python3 tools/dev/gh.py R4QE01 fn "name"               functions whose name contains text
    python3 tools/dev/gh.py R4QE01 scalar 0xCD00          instructions loading a constant (functions listed)
    python3 tools/dev/gh.py R4QE01 rename 0x803D4F80 name  rename the function containing an address (saved)
"""
import os, sys
os.environ.setdefault('GHIDRA_INSTALL_DIR', '/Applications/ghidra_12.1.2_PUBLIC')
import pyghidra
pyghidra.start()

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'dumps', 'ghidra'))
PROJECTS = {'R4QE01': 'StrikersDols'}          # everything else lives in StrikersOthers


def main(argv):
    name, cmd, args = argv[0], argv[1], argv[2:]
    proj_name = PROJECTS.get(name, 'StrikersOthers')
    with pyghidra.open_project(ROOT, proj_name) as proj:
        with pyghidra.program_context(proj, '/' + name) as prog:
            run(prog, cmd, args)


def run(prog, cmd, args):
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor
    fm = prog.getFunctionManager()
    af = prog.getAddressFactory()
    A = lambda s: af.getAddress('%08x' % int(s, 0))
    if cmd == 'dec':
        f = fm.getFunctionContaining(A(args[0]))
        if f is None:
            print('no function at', args[0]); return
        di = DecompInterface(); di.openProgram(prog)
        r = di.decompileFunction(f, 180, ConsoleTaskMonitor())
        print('// %s @ %s' % (f.getName(), f.getEntryPoint()))
        print(r.getDecompiledFunction().getC() if r.decompileCompleted() else r.getErrorMessage())
    elif cmd == 'dis':
        n = int(args[1]) if len(args) > 1 else 40
        ins = prog.getListing().getInstructions(A(args[0]), True)
        for _ in range(n):
            if not ins.hasNext(): break
            i = ins.next(); print('%s  %s' % (i.getAddress(), i))
    elif cmd == 'xref':
        for r in prog.getReferenceManager().getReferencesTo(A(args[0])):
            f = fm.getFunctionContaining(r.getFromAddress())
            print('%s  %s  in %s' % (r.getFromAddress(), r.getReferenceType(), f.getName() if f else '?'))
    elif cmd == 'str':
        it = prog.getListing().getDefinedData(True)
        for d in it:
            if d.hasStringValue():
                v = str(d.getValue())
                if args[0].lower() in v.lower():
                    print('%s  %r' % (d.getAddress(), v))
    elif cmd == 'fn':
        for f in fm.getFunctions(True):
            if args[0].lower() in f.getName().lower():
                print('%s  %s' % (f.getEntryPoint(), f.getName()))
    elif cmd == 'scalar':
        want = int(args[0], 0)
        seen = {}
        for ins in prog.getListing().getInstructions(True):
            for i in range(ins.getNumOperands()):
                for o in ins.getOpObjects(i):
                    if hasattr(o, 'getValue') and ((o.getValue() & 0xFFFFFFFF) == want or (o.getValue() & 0xFFFF) == want):
                        f = fm.getFunctionContaining(ins.getAddress())
                        seen.setdefault(f.getEntryPoint() if f else None, []).append(str(ins.getAddress()))
        for k, v in seen.items():
            print(k, fm.getFunctionAt(k).getName() if k else '?', v[:6])
    elif cmd == 'rename':
        from ghidra.program.model.symbol import SourceType
        f = fm.getFunctionContaining(A(args[0]))
        tx = prog.startTransaction('rename'); f.setName(args[1], SourceType.USER_DEFINED); prog.endTransaction(tx, True)
        prog.save('rename', ConsoleTaskMonitor())
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
