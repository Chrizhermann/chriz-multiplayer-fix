# Support and verification

Target: Windows x64 engine **2.7.3.0** with **EEex v1.3.1** (tested in the
labs below). **EEex v1.2.0** is checked against its source only: every EEex
function the mod calls exists there, `EEex_Assembly_x86-64.lua` is
byte-identical to v1.3.1, and `EEex_scripts/extra_pattern_dbs` exists. Both
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

### The check at install time

InfinityLoader resolves every pattern in `EEex_scripts/extra_pattern_dbs`
before the game window opens, and one pattern that does not match stops the
game from starting: in the IWD:EE lab (2.7.3.0, EEex v1.3.1) a `CZMP.db` with
one changed pattern left the game without a window for 1.7 minutes, where it
normally opens after 2 seconds. A check inside the game comes too late for
that, so component 0 checks the executable when it is installed
(`lib/czmp_preflight.tpa`):

- The executable is the one InfinityLoader starts: the first name in
  `ExeNames` that exists. The setting is read the way Windows'
  `GetPrivateProfileString` reads it for the loader: only the first `[General]`
  section, the first `ExeNames` there, names of section and key in any case
  and with blanks around them, the value without surrounding blanks and one
  pair of enclosing quotes; the names between the commas are taken as written.
  Without `ExeNames` the loader starts no game, and nothing is installed.
- It must be a 64-bit Windows program, and every pattern of `CZMP.db` must
  match exactly once, byte for byte, inside its `.text` section, the only part
  InfinityLoader searches (as far as the section reaches both in memory and
  in the file). Copies of the same bytes elsewhere do not matter.
- Otherwise neither `M_CZMP.lua` nor `CZMP.db` is installed, copies left by an
  earlier install are removed (uninstalling puts them back), and the log names
  the reason. The save copy button does not depend on it.

The bytes at both hook sites are checked again in the game before patching;
any difference there leaves the fix inactive with one log line.

After a game update the patterns are already in place, so the mod has to be
installed again for the check to run on the new executable (EEex itself needs
the same after an engine update).

### Verified in quiet labs (2026-11-22)

| Game | Without the fix | With the fix |
|---|---|---|
| IWD:EE 2.7.3.0, EEex v1.3.1 | crashes reproduced, dumps as above | 15 cycles lobby → *Local network game > Load*, plus 3 runs of the order that crashed most, no crash; lobby sign-in works |
| EET on BG2:EE 2.7.3.0, EEex v1.3.1 | crash in cycle 2, same stack | 10 cycles plus 3 runs of that order, no crash; 13–14 lobby rooms listed |

Not tested: hosting an internet game (labs never host in the public lobby),
and a standalone BG:EE game (patterns only).

## The save copy button

- The button needs EEex's LuaJIT component (`B3-EEex-LuaJIT`, component 8 of
  EEex v1.2.0 and v1.3.1, which EEex lists as experimental; it sets
  `LuaPatchMode=REPLACE_INTERNAL_WITH_EXTERNAL` and
  `LuaVersionExternal=5.1-LuaJIT` in `InfinityLoader.ini`). Without it the
  button stays hidden with one console line, and the installer prints one
  line; its files are still installed, so it appears once LuaJIT is added.
  Chriz Easy BG and Chriz Easy IWD install LuaJIT.
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
- Only the save the Load screen lists is copied. Each listed save carries the
  creation time of its `BALDUR.gam` (`gameSaves.files[i].fileTime`), and the
  button copies a folder from `save` or `mpsave` only when its `BALDUR.gam`
  was created at that time. Lists from other folders, such as EET's Black Pits
  campaigns (`bpsave`), can hold a folder with the same name; the button then
  says the save is not one of the single-player or multiplayer saves and copies
  nothing.
- The button is hidden while BG2:EE imports a BG:EE save: the Load screen then
  lists the other game's saves.
- If a copy fails halfway, the button deletes what it wrote. If that is not
  possible either, it names the unfinished folder so the player can delete it.
- Its texts are English and are added again after the game reloads its
  language files, so they stay after a language change.
- Verified 2026-11-22 in both labs, in both directions: the button's copies
  were byte-identical to the originals. Saves copied between the folders
  loaded in the other mode with the same party, including characters players
  had created in multiplayer (round trips multiplayer → single player →
  multiplayer on IWD:EE, single player → multiplayer → single player on EET).
- Verified again after these checks were added (2026-11-22): on EET a Black
  Pits save with the same folder name as a multiplayer save was refused and
  nothing was copied, while copies from the main campaign's Load screen in
  both directions were identical; on IWD:EE copies in both directions, through
  the lobby for multiplayer, were identical. The listed time matched the
  `BALDUR.gam` creation time for all 4 EET multiplayer saves and all 6 IWD:EE
  single-player saves, and every lobby round trip ended without a crash.
