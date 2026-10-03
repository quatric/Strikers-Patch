/* GameCube controller -> Classic Controller bridge for Mario Strikers Charged.
 *
 * The game's own input path (SDK WPAD + KPAD, wrapped by the game) already understands a Classic Controller
 * thanks to Vague Rant's hack, which this patch ships.  So rather than invent a second control scheme, a pad is
 * presented to the game as a Classic Controller: every button and stick lands where the same press on a real
 * Classic Controller would, and the Classic Controller map applies unchanged.
 *
 * Four hooks, one blob each (hooks.S has the register-saving entry stubs):
 *
 *   PROBE   WPADProbe(chan, &type)            runs every frame for every channel, so it also hosts the SI poller
 *   READ    WPADRead(chan, buf)               hands the game the pad as a Classic Controller record
 *   SETFMT  WPADSetDataFormat(chan, fmt)      a channel with no Wii Remote cannot be told a format: accept it
 *   (KPAD)  with no Wii Remote nothing delivers samples, so PROBE runs KPAD's own sampling callback once a frame
 *
 * The game links the SI library but not PAD, so nothing polls the pads: poll_all() drives the Serial Interface's
 * auto-polling (the approach of Barrel Blast Patch, which was checked on a console).  Addresses arrive as -D
 * macros, resolved per release by tools/anchors.py.
 *
 * A channel is "pad driven" while a valid, error-free pad answers on the matching port and the channel does not
 * already hold a real Nunchuk or Classic Controller.  Wii Remotes keep working on every channel with no pad.
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_OUT(c)  (0xCD006400u + 12u * (c))
#define SI_INH(c)  (0xCD006404u + 12u * (c))
#define SI_INL(c)  (0xCD006408u + 12u * (c))
#define SI_POLL    (0xCD006430u)
#define SI_COMCSR  (0xCD006434u)
#define SI_SR      (0xCD006438u)

#define TB_PROBE   15187500u      /* 0.25 s: re-probe an empty port at most this often */
#define TB_NOREP   9112500u       /* 0.15 s of NOREP before a pad counts as unplugged */
#define TB_BUSY    60750000u      /* 1 s: an SI transfer that long is wedged */
#define TB_POLL    30000u         /* the poller itself runs at most every 0.5 ms */
#define TB_FEED    405000u        /* 6.7 ms: one KPAD sample per frame at most */

struct st {
    u32 probe_tb[4];    /* last SIGetType per port */
    u32 norep_tb[4];    /* when NOREP was first seen on a port (0 = not seen) */
    u32 feed_tb[4];     /* last KPAD sample pushed per channel */
    u32 busy_tb;        /* when si:: was first seen busy (0 = idle) */
    u32 poll_tb;        /* last poller run */
    u8 in_cb;           /* inside KPAD's sampling callback */
};
#define ST ((volatile struct st *)STATE)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

static inline int confirmed(u32 type)
{
    return !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
}

/* ------------------------------------------------------------------ SI poller */
static void poll_all(void)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    u32 now = tb(), sisr, mask, poll, c;
    s32 busy;

    if (now - ST->poll_tb < TB_POLL)
        return;
    ST->poll_tb = now;

    /* probe every port that has no confirmed pad, at most every 0.25 s each: probing every frame collided with the
     * pad's own polling on hardware */
    for (c = 0; c < 4; c++) {
        if (!confirmed(types[c]) && now - ST->probe_tb[c] >= TB_PROBE) {
            ST->probe_tb[c] = now;
            ((u32 (*)(u32))FN_SIGETTYPE)(c);
        }
    }

    /* an unplugged pad latches NOREP; si:: never reads it (no PAD library), so copy a persistent one into the type
     * cache ourselves, which makes SIGetType probe the port again once a pad is plugged back in */
    sisr = R32(SI_SR);
    for (c = 0; c < 4; c++) {
        if ((sisr >> (24 - 8 * c)) & 8u) {
            if (!ST->norep_tb[c])
                ST->norep_tb[c] = now | 1;
            else if (now - ST->norep_tb[c] >= TB_NOREP)
                types[c] = 8;
        } else {
            ST->norep_tb[c] = 0;
        }
    }

    R32(SI_OUT(0)) = 0x00400300u;                    /* poll command */
    R32(SI_OUT(1)) = 0x00400300u;
    R32(SI_OUT(2)) = 0x00400300u;
    R32(SI_OUT(3)) = 0x00400300u;
    R32(SI_SR) = (sisr & 0x0F0F0F0Fu) | 0x80000000u; /* ack errors, latch the OUT buffers */

    /* poll (and copy on vblank) only the ports with a confirmed pad: a port can only be probed successfully
     * while it is not being polled */
    mask = 0;
    for (c = 0; c < 4; c++)
        if (confirmed(types[c]))
            mask |= 0x88u >> c;
    poll = R32(SI_POLL) & ~0xFFu;
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = poll | mask;
    /* si:: rewrites SIPOLL from its own shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~0xFFu) | mask;

    /* a pad unplugged mid-transfer leaves si::'s global busy flag wedged (nothing times it out): force it idle
     * after a second */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else if (ST->busy_tb == 0) {
        ST->busy_tb = now | 1;
    } else if (now - ST->busy_tb >= TB_BUSY) {
        u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
        R32(SI_BUSY) = (u32)-1;
        R32(SI_COMCSR) = 0x80000000u;
        ((void (*)(u32))FN_OSRESTORE)(lvl);
        ST->busy_tb = 0;
    }
}

/* ----------------------------------------------------------------- pad access */
static inline u8 *wpd(u32 chan)
{
    return *(u8 **)(WPAD_TBL + chan * 4);
}

/* a valid, error-free pad response on this port */
static inline int pad_in(u32 chan, u32 *h, u32 *l)
{
    u32 v = R32(SI_INH(chan));

    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_INL(chan));
    return 1;
}

/* does this channel hold a real extension (Nunchuk or Classic Controller) that must win over the pad? */
static inline int real_ext(u8 *b)
{
    u32 t = b[0x8C1 - WPAD_SHIFT];

    return *(s32 *)(b + (0x8BC - WPAD_SHIFT)) != -1 && (t == 1 || t == 2);
}

static inline int driven(u32 chan, u32 *h, u32 *l)
{
    u8 *b;

    if (chan > 3 || !pad_in(chan, h, l))
        return 0;
    b = wpd(chan);
    return b && !real_ext(b);
}

/* --------------------------------------------------------- Classic Controller */
/* Classic Controller buttons as WPAD reports them */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_ZR    0x0004
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_ZL    0x0080
#define CL_R     0x0200
#define CL_PLUS  0x0400
#define CL_HOME  0x0800
#define CL_MINUS 0x1000
#define CL_L     0x2000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

static inline s16 stick(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * 5;      /* pad ~+-100 -> game +-500; the game divides by 5 again */

    if (v > 511)
        v = 511;
    if (v < -512)
        v = -512;
    return (s16)v;
}

/* GameCube pad -> Classic Controller buttons.  Start is Plus, L + R + Start is HOME. */
static __attribute__((noinline)) u32 cc_buttons(u32 h)
{
    u32 b = 0;

    if (h & 0x01000000u) b |= CL_A;
    if (h & 0x02000000u) b |= CL_B;
    if (h & 0x04000000u) b |= CL_X;
    if (h & 0x08000000u) b |= CL_Y;
    if (h & 0x10000000u) b |= CL_PLUS;
    if (h & 0x00100000u) b |= CL_ZL;            /* Z */
    if (h & 0x00400000u) b |= CL_L;
    if (h & 0x00200000u) b |= CL_R;
    if (h & 0x00080000u) b |= CL_UP;
    if (h & 0x00040000u) b |= CL_DOWN;
    if (h & 0x00020000u) b |= CL_RIGHT;
    if (h & 0x00010000u) b |= CL_LEFT;
    if ((b & (CL_L | CL_R | CL_PLUS)) == (CL_L | CL_R | CL_PLUS))
        b = (b & ~(CL_L | CL_R | CL_PLUS)) | CL_HOME;
    return b;
}

/* Vague Rant's button injector, applied to the Classic Controller word: what the game's WPAD parser would
 * have written into the Wii Remote button word (flags 0x80 / 0x40 stand for the Wii Remote and Nunchuk shake,
 * which his later hooks turn into accelerometer swings), plus his right stick d-pad emulation. */
static __attribute__((noinline)) u32 remote_bits(u32 cc, s32 rx, s32 ry)
{
    u32 w = 0;

    if (cc & CL_HOME)  w |= 0x8000;
    if (cc & CL_UP)    w |= 0x0008;
    if (cc & CL_DOWN)  w |= 0x0004;
    if (cc & CL_LEFT)  w |= 0x0001;
    if (cc & CL_RIGHT) w |= 0x0002;
    if (cc & CL_A)     w |= 0x0800;
    if (cc & CL_B)     w |= 0x0400;
    if (cc & CL_X)     w |= 0x4000;             /* Nunchuk C */
    if (cc & CL_Y)     w |= 0x0080;             /* Wii Remote shake */
    if (cc & CL_L)     w |= 0x0040;             /* Nunchuk shake */
    if (cc & CL_R)     w |= 0x0002;
    if (cc & CL_ZL)    w |= 0x2000;             /* Nunchuk Z */
    if (cc & CL_ZR)    w |= 0x0400;
    if (cc & CL_PLUS)  w |= 0x0200;
    if (cc & CL_MINUS) w |= 0x0200;
    if (rx >= 255)  w |= 0x0008;
    if (rx <= -256) w |= 0x0004;
    if (ry >= 255)  w |= 0x0001;
    if (ry <= -256) w |= 0x0002;
    return w;
}

/* One Classic Controller record in the layout WPADRead hands out (the same 0x36 bytes KPAD queues per sample). */
static __attribute__((noinline)) void fill_record(u8 *s, u32 h, u32 l)
{
    u32 cc = cc_buttons(h), i;
    s16 lx = stick(h >> 8), ly = stick(h), rx = stick(l >> 24), ry = stick(l >> 16);

    for (i = 0; i < 0x36; i++)
        s[i] = 0;
    *(u16 *)(s + 0x00) = (u16)remote_bits(cc, rx, ry);
    *(s16 *)(s + 0x06) = 0x68;                  /* at rest: 1 g on Z (a Wii Remote lying flat) */
    for (i = 0; i < 4; i++) {                   /* no pointer: four invalid IR objects */
        *(s16 *)(s + 8 + i * 8) = 1023;
        *(s16 *)(s + 10 + i * 8) = 1023;
    }
    s[0x28] = 2;                                /* extension: Classic Controller */
    s[0x29] = 0;                                /* no extension error */
    *(u16 *)(s + 0x2A) = (u16)cc;
    *(s16 *)(s + 0x2C) = lx;
    *(s16 *)(s + 0x2E) = ly;
    *(s16 *)(s + 0x30) = rx;
    *(s16 *)(s + 0x32) = ry;
    s[0x34] = (cc & CL_L) ? 0xF8 : 0;
    s[0x35] = (cc & CL_R) ? 0xF8 : 0;
}

/* ------------------------------------------------------------------- the hooks */
#if defined(HOOK_PROBE)
/* WPADProbe(chan, &type): report a Classic Controller while a pad answers.  Returns 1 when handled. */
u32 gc_probe(u32 chan, u32 *type)
{
    u32 h, l, now;
    u8 *b;

    if (chan > 3)
        return 0;
    if (!ST->in_cb)
        poll_all();
    if (!driven(chan, &h, &l))
        return 0;
    if (type)
        *type = 2;
    if (ST->in_cb)              /* KPAD's own callback asks too: answer, but do not feed it again */
        return 1;

    /* no Wii Remote at all: nothing will ever deliver a sample, so run KPAD's own sampling callback (the one the
     * WPAD library calls for each incoming report) once a frame; it reads the pad through the READ hook */
    b = wpd(chan);
    if (*(s32 *)(b + (0x8BC - WPAD_SHIFT)) == -1) {
        void (*cb)(u32) = *(void (**)(u32))(b + (0x8A8 - WPAD_SHIFT));

        now = tb();
        if (cb && now - ST->feed_tb[chan] >= TB_FEED) {
            ST->feed_tb[chan] = now;
            ST->in_cb = 1;
            cb(chan);
            ST->in_cb = 0;
        }
    }
    return 1;
}
#endif

#if defined(HOOK_READ)
/* WPADRead(chan, buf): the pad as a Classic Controller record.  Returns 1 when handled. */
u32 gc_read(u32 chan, u8 *buf)
{
    u32 h, l;

    if (!driven(chan, &h, &l))
        return 0;
    fill_record(buf, h, l);
    return 1;
}
#endif

#if defined(HOOK_SETFMT)
/* WPADSetDataFormat(chan, fmt): with no Wii Remote there is nothing to tell, so record the format and report success. */
u32 gc_setfmt(u32 chan, u32 fmt)
{
    u32 h, l;
    u8 *b;

    if (!driven(chan, &h, &l))
        return 0;
    b = wpd(chan);
    if (*(s32 *)(b + (0x8BC - WPAD_SHIFT)) != -1)
        return 0;
    *(u32 *)(b + (0x8B8 - WPAD_SHIFT)) = fmt;
    return 1;
}
#endif

#if defined(HOOK_FRAME)
/* The input manager's per-frame update (r3 = the manager): it reads only the channels whose "connected" flag its
 * WPAD connect callback sets, and no Wii Remote means no callback.  Run the callback ourselves for every port a pad
 * answers on, and keep the SI poller going from here, since nothing else polls the pads. */
u32 gc_frame(u8 *self)
{
    u32 c, h, l;

    poll_all();
    for (c = 0; c < 4; c++)
        if (!self[0x2F0 + c] && driven(c, &h, &l))
            ((void (*)(u32, u32))FN_CONNECT)(c, 0);
    return 0;
}
#endif

