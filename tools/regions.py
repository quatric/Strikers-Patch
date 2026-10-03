"""The four retail releases of Mario Strikers Charged.

The two European discs share the disc id (R4QP01) and the disc version (0), so a disc is told apart by its
main.dol: every release's DOL has its own size, and the patcher also checks the retail bytes at every site.
Korea released the game too, but no dump of it was available to build or test against.
"""
REGIONS = {
    'R4QE01': dict(disc_id='R4QE01', label='Mario Strikers Charged (USA)', short='USA', dol_size=5695424),
    'R4QP01_rev1': dict(disc_id='R4QP01', label='Mario Strikers Charged Football (Europe, Rev 1)',
                        short='Europe Rev 1', dol_size=5691072),
    'R4QP01_rev2': dict(disc_id='R4QP01', label='Mario Strikers Charged Football (Europe, Rev 2)',
                        short='Europe Rev 2', dol_size=5692416),
    'R4QJ01': dict(disc_id='R4QJ01', label='Mario Strikers Charged (Japan)', short='Japan', dol_size=5696544),
}


def for_disc(disc_id):
    """Regions that share a disc id (two for the European release)."""
    return [r for r, v in REGIONS.items() if v['disc_id'][:4] == disc_id[:4]]
