# chriz-multiplayer-fix — Working Agreements

Standalone EEex mod for BG:EE (incl. SoD), BG2:EE, EET and IWD:EE `2.7.3.0`
(Windows x64, EEex `v1.2.0` / `v1.3.1`). Part of Chriz Easy BG and Chriz Easy IWD
(`chriz-bg-collection`, which pins its releases in both installers).

## Core rules

- **Target 2.7.3.0.** Build and test against the official `2.7.3.0` Windows x64
  executables. Older patches are optional, never a target.
- **We overwrite, fail soft.** The components copy their files whatever stood there
  before. Without EEex each component is a logged no-op. At run time a changed or
  unknown engine build leaves the lobby fix inactive with one log line; nothing in
  game data stops an install.
- **Lobby fix layout comes from `CZMP.db`.** The three patterns prove every offset
  `M_CZMP.lua` uses; `M_CZMP.lua` re-checks the bytes it overwrites before hooking.
  Change an offset only together with its pattern and the tests.
- **Save copies never overwrite.** A copy always goes to a new slot number in the
  other folder; a failed copy removes what it wrote.
- **Verification:** `python -X utf8 -m pytest` (WeiDU install/reinstall/uninstall,
  LuaJIT runtime tests with stubs and real file copies, pattern checks against
  local `2.7.3.0` executables when configured). In-game checks run only in a
  disposable quiet lab, never in a player's game. Never host an internet lobby
  game from a lab.
- Load the `bg-modding` and `bg-modding-learn` skills for every task here.
