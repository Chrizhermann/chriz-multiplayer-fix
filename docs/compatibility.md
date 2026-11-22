# Support and verification

Target: Windows x64 engine **2.7.3.0** with **EEex v1.2.0 or v1.3.1**. Both
components only add runtime files; no game resource, save, executable on disk
or shared loader setting is edited.

| Component | Files |
|---|---|
| 0 Lobby crash fix | `override/M_CZMP.lua`, `EEex_scripts/extra_pattern_dbs/CZMP.db` |
| 1 Save copy button | `override/M_CZMS.lua`, `override/CZMS.menu` |

## The lobby crash

The multiplayer lobby uses libjingle. Its `XmppClient` and socket live on a
dedicated network thread (`XmppThread`). Lobby tasks are run by
`XmppPump::OnMessage`, which is posted by `XmppPump::WakeTasks`. `WakeTasks`
posts to **the thread that woke the tasks**, and the compiler inlined the same
post into `Task::Start` and `Task::Wake`. Opening the lobby or refreshing its
rooms wakes tasks from the game's main thread, so the main thread also ran
lobby tasks.

On leaving the lobby, `DPProviderJingle::Close` makes the main thread run the
remaining tasks; the finished `XmppClient` is deleted there (`ResetSocket`).
At the same time the network thread handles `MSG_DISCONNECT` in
`XmppThread::OnMessage` and calls `ResetSocket` too. Both close and free the
same socket: crash dumps show heap corruption in
`PhysicalSocketServer::Remove`, or a second `SignalThread::Destroy` of the
same object. How often it hits depends on timing; *Local network game > Load*
right after the lobby was open hit it most.

### The fix

Two hooks keep every lobby task on the network thread:

1. `XmppPump::OnMessage` (`WakeTasks + 0xB0`): when it runs on any OS thread
   other than the pump's own `XmppThread`, it calls `WakeTasks` instead of
   running the tasks.
2. `XmppPump::WakeTasks + 0x16`: the post goes to the pump's `XmppThread`
   instead of the current thread.

While the network thread is not running (`started_` false), both hooks leave
everything as it was. Layout used, each proven by a pattern in `CZMP.db`:
`XmppPump::notify_` at `+0x88`; `XmppThread::notify_` at `+0x110` and
`pump_` at `+0x120`; `talk_base::Thread::started_` at `+0xFC` and
`thread_id_` at `+0x108`. Before patching, `M_CZMP.lua` checks the bytes at
both hook sites; any difference leaves the fix inactive with one log line.

Each pattern matches exactly once in the Steam 2.7.3.0 `Baldur.exe` of BG:EE
and BG2:EE (EET uses the BG2:EE exe) and in the 2.7.3.0 `Icewind.exe`
(`tests/test_patterns.py`).

### Verified in quiet labs (2026-11-22)

| Game | Without the fix | With the fix |
|---|---|---|
| IWD:EE 2.7.3.0, EEex v1.3.1 | crashes reproduced, dumps as above | 15 cycles lobby → *Local network game > Load*, plus 3 runs of the order that crashed most, no crash; lobby sign-in works |
| EET on BG2:EE 2.7.3.0, EEex v1.3.1 | crash in cycle 2, same stack | 10 cycles plus 3 runs of that order, no crash; 13–14 lobby rooms listed |

Not tested: hosting an internet game (labs never host in the public lobby),
and a standalone BG:EE game (patterns only).

## The save copy button

- Saves live in `Documents\<engine_name>\save` and `...\mpsave` (the Documents
  folder Windows reports, also when OneDrive moved it).
- The button copies one save folder file by file with the Windows file
  functions (LuaJIT FFI) into a new folder with the next free slot number in
  the other folder. A failed copy deletes what it wrote. Nothing is
  overwritten, and the original stays.
- **IWD:EE** has a Load and Delete button per row and no selection, so every
  row gets a **Copy** button left of the party portraits.
- **BG:EE, BG2:EE, EET** select a save in a list, so one button in the bottom
  row copies the selected save and is clickable only while one is selected,
  like Load and Delete.
- Verified 2026-11-22 in both labs, in both directions: the button's copies
  were byte-identical to the originals. Saves copied between the folders
  loaded in the other mode with the same party, including characters players
  had created in multiplayer (round trips multiplayer → single player →
  multiplayer on IWD:EE, single player → multiplayer → single player on EET).
