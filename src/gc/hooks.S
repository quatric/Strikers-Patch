/* Entry stubs: save every volatile register, call the C hook, restore, then either return early (the hook
 * handled the call) or run the instruction the hook replaced.  The slot before the last word is that displaced
 * instruction (the builder fills it in); the last word becomes the branch back to site + 4. */
    .macro SAVE
    stwu    1, -0x70(1)
    stw     0, 0x0c(1)
    stw     3, 0x10(1)
    stw     4, 0x14(1)
    stw     5, 0x18(1)
    stw     6, 0x1c(1)
    stw     7, 0x20(1)
    stw     8, 0x24(1)
    stw     9, 0x28(1)
    stw     10, 0x2c(1)
    stw     11, 0x30(1)
    stw     12, 0x34(1)
    mflr    0
    stw     0, 0x38(1)
    mfcr    0
    stw     0, 0x3c(1)
    mfctr   0
    stw     0, 0x40(1)
    mfxer   0
    stw     0, 0x44(1)
    .endm

    .macro RESTORE_ALL          /* everything but r0 */
    lwz     0, 0x44(1)
    mtxer   0
    lwz     0, 0x40(1)
    mtctr   0
    lwz     0, 0x3c(1)
    mtcr    0
    lwz     0, 0x38(1)
    mtlr    0
    lwz     3, 0x10(1)
    lwz     4, 0x14(1)
    lwz     5, 0x18(1)
    lwz     6, 0x1c(1)
    lwz     7, 0x20(1)
    lwz     8, 0x24(1)
    lwz     9, 0x28(1)
    lwz     10, 0x2c(1)
    lwz     11, 0x30(1)
    lwz     12, 0x34(1)
    .endm

    .section .gcstart, "ax"
    b       _entry

    .section .gctail, "ax"
    .globl _entry
_entry:
    SAVE
#if defined(HOOK_PROBE)
    bl      gc_probe            /* WPADProbe(chan, &type): r3 = chan, r4 = &type */
#elif defined(HOOK_READ)
    bl      gc_read             /* WPADRead(chan, buf) */
#elif defined(HOOK_SETFMT)
    bl      gc_setfmt           /* WPADSetDataFormat(chan, fmt) */
#endif
    stw     3, 0x08(1)          /* did the hook handle the call? */
    RESTORE_ALL
    lwz     0, 0x08(1)
    addi    1, 1, 0x70
    cmpwi   0, 0
    beq     1f
    li      3, 0                /* handled: return 0 (success) to the caller */
    blr
1:  .long   0xD15B1ACE          /* the displaced instruction */
    nop                         /* becomes the branch back */
