# Changelog

## 0.1.0 — 2026-11-22

- Component 0: fixes the random crash when leaving the multiplayer lobby
  (for example *Local network game > Load*) on BG:EE, BG2:EE, EET and IWD:EE
  2.7.3.0 with EEex v1.3.1 (v1.2.0 checked against its source). Two hooks
  keep every lobby task on the lobby's own network thread (`M_CZMP.lua`,
  patterns in `CZMP.db`). The installer checks the game's executable first
  and leaves the fix out when its lobby code differs, because a pattern that
  does not match stops the game from starting.
- Component 1: a Load screen button copies a save between the single-player
  and the multiplayer saves (`M_CZMS.lua`, `CZMS.menu`). IWD:EE gets a Copy
  button in every save row; BG:EE, BG2:EE and EET get one button that copies
  the selected save. It copies only the save the Load screen lists, is hidden
  while BG2:EE imports a BG:EE save, and removes an unfinished copy.
