# Technical notes

How the two patches work and how one set of data becomes a patched `main.dol`,
a Gecko code list and a Riivolution patch. For installing and playing see the
[README](../README.md). Addresses are the **USA** `main.dol` (`R4QE01`) unless
noted.

## One data set, three outputs

Every patch is a list of operations on one release's `main.dol`: in-place byte
patches, and **hooks** (one instruction replaced by a branch to a routine that
runs the displaced instruction and branches back). `tools/prebuilt/<feature>_<region>.json`
holds them, with the retail bytes expected at every site. `tools/ops.py` turns
them into a patched DOL (trampolines go in one added text section at
`0x80001820`), `C2` Gecko codes, or Riivolution `<memory>` elements.
`tools/patcher.py` refuses a DOL whose sites do not match; `tools/check.py` and
`tools/verify.py` check the data (the latter against real retail DOLs).

The two European discs share the disc id and version (`R4QP01`, v0), so the
region is chosen by `main.dol`: retail sizes are USA 5,695,424, EUR Rev 1
5,691,072, EUR Rev 2 5,692,416 and JPN 5,696,544 bytes, and every site must hold
the retail (or this tool's own patched) bytes.

## Layers the game uses for input

- **WPAD** (`WPADProbe`, `WPADRead`, `WPADSetDataFormat`): one control block per
  channel (table at `0x805d6170`); records of 0x36 bytes hold the buttons,
  accelerometer, IR objects and the extension data (Classic: buttons at `+0x2a`,
  sticks as signed ±512 at `+0x2c..0x32`, triggers at `+0x34`).
- **KPAD**: calls `WPADRead` from its own sampling callback into a ring of
  sixteen 0x38-byte samples per channel.
- The game's input manager (`FUN_8037537c`, every frame) calls the pad reader
  (`FUN_803753d8`) only for channels whose "connected" flag its WPAD connect
  callback (`FUN_803751f4`) has set — and nothing sets it without a Wii Remote.

## Classic Controller (`src/cc/`)

Vague Rant's codes, verbatim. They make the pad reader treat a Classic Controller
as a Nunchuk, convert Classic buttons to Wii Remote buttons (plus two
"shake" flags for Y and L), turn the right stick into a D-pad, scale the left
stick into Nunchuk range and emulate the pointer in KPAD. Every hook is
position independent, so the Gecko form needs no fixed memory. `gen_cc.py` parses
the files and checks each original instruction against the DOL.

## GameCube controller (`src/gc/`)

The game links the SI library but not PAD, so nothing polls the pads. Four hooks
(compiled with devkitPPC from `gcpad.c`, one copy per hook, per release):

| Hook | Function | Does |
| --- | --- | --- |
| `FRAME` | input manager frame update | runs the SI poller; calls the connect callback for every port a pad answers on |
| `PROBE` | `WPADProbe` | polls; reports a Classic Controller (type 2) while a pad answers, including inside KPAD's callback; with no remote, drives KPAD's sampling callback once per frame |
| `READ` | `WPADRead` | fills the record with the pad as a Classic Controller |
| `SETFMT` | `WPADSetDataFormat` | accepts any format when there is no remote |

The poller drives the Serial Interface directly (`0xCD006400`): it sets the poll
command `0x00400300` on all four channels, enables polling for the ports whose
type cache says a pad is present, mirrors the enable bits into the SI library's
shadow of `SIPOLL` (the library rewrites the register from it every retrace),
probes empty ports with `SIGetType` at a low rate, copies a persistent `NOREP` into
the type cache so an unplugged port is probed again, and un-wedges the library's
busy flag if it stays set. Variables live in a 0x60-byte block at `0x80005790`
(padding in every release). The same code is built for every release from
addresses found by masked-signature search in `tools/anchors.py`.

Because the pad is fed to the game as a Classic Controller, everything downstream
(buttons, sticks, pointer) is Vague Rant's code, which keeps the two inputs
identical except for the GameCube shoulder mapping: Z maps to Classic L (swap
items), and L maps to Classic ZL (modify shots). The physical L + R + Start
combination produces HOME.

## Layout of the injected section

`0x80001820..0x80003000` (the Wii's boot-time scratch area; this game's first
section starts at `0x80004000`). Classic Controller trampolines use
`0x80001820..0x80001C00`, GameCube ones `0x80001C00..0x80002C00`.

## Testing

`tools/dev/dolphin.py` runs Dolphin from a private user folder (`dumps/`, never
your own configuration), feeds scripted input through Dolphin's pipe devices and
reads memory over its GDB stub. A GameCube pad with no Wii Remote at all must
produce the same KPAD hold bits and game-side stick values as an emulated Classic
Controller; that is what was compared. Nothing here has run on real hardware.

## Releases

| Region | Disc | `main.dol` size | `WPADProbe` |
| --- | --- | --- | --- |
| USA | `R4QE01` | 5,695,424 | `0x803ccfe8` |
| Europe Rev 1 | `R4QP01` | 5,691,072 | `0x803CB5CC` |
| Europe Rev 2 | `R4QP01` | 5,692,416 | `0x803CBB5C` |
| Japan | `R4QJ01` | 5,696,544 | `0x803CD448` |
