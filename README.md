# Chriz Multiplayer Fix

Two small EEex additions for the Enhanced Editions' multiplayer:

1. **Lobby crash fix.** The games crash at random when you leave Beamdog's
   multiplayer lobby, most often with *Multiplayer > Local network game >
   Load*. This component removes the cause.
2. **Copy saves between single player and multiplayer.** A button on the Load
   screen copies a save from the multiplayer saves to the single-player saves,
   or the other way round. The original stays as it is.

Together they make it easy to let viewers or friends create characters in a
multiplayer session and then carry the party into a single-player game, and
back again, whenever you like.

## Moving a party between multiplayer and single player

1. **Multiplayer > Local network game > Load** (or New Game): host the game.
   Players create or import their characters. Save the game.
2. Still on the multiplayer **Load** screen, copy that save:
   - **Icewind Dale:EE**: click **Copy** in the save's row.
   - **Baldur's Gate:EE, BG2:EE, EET**: click the save, then
     **Copy to single player** at the bottom left.
3. Confirm. The game says where the copy is: **Single Player > Load Game**.
4. Load it there and play on. To go back to multiplayer, do the same on the
   single-player Load screen with **Copy to multiplayer**.

The copy gets the next free slot number in the other folder, so no save is
ever overwritten. Files are copied directly; no window opens.

## Why the lobby crashed

The lobby client runs on its own network thread, but its tasks were also run
by the game's main thread whenever the main thread woke them. On leaving the
lobby both threads tore the same connection down at once, closed and freed
the same socket twice, and the heap was corrupted. Two small hooks keep every
lobby task on the network thread. Details:
[support and verification](docs/compatibility.md).

## Requirements and support

Windows x64 **BG:EE (including SoD), BG2:EE, EET and IWD:EE 2.7.3.0** with
[EEex](https://github.com/Bubb13/EEex) **v1.2.0 or v1.3.1**. The save copy
button needs EEex running on LuaJIT (EEex's default). Part of **Chriz Easy
BG** and **Chriz Easy IWD**.

If an engine build differs from the one checked, the crash fix stays inactive
and the game runs as before. Without EEex, each component installs as a logged
no-op.

## Install

1. Close the game and install EEex first.
2. Copy the `chriz_multiplayer_fix` folder into the game folder.
3. Copy a Windows x64 `weidu.exe` from
   [WeiDU](https://github.com/WeiDUorg/weidu/releases) into the game folder and
   rename that copy to `setup-chriz_multiplayer_fix.exe`.
4. Run it and install components **0** and **1**. Start the game through
   EEex's `InfinityLoader.exe`.

Run `setup-chriz_multiplayer_fix.exe` again to reinstall or uninstall.

[MIT license](LICENSE) · [Changelog](CHANGELOG.md) · [Offline tests](tests/README.md)
