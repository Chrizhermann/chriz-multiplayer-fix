# Changelog

## 0.1.0 — 2026-11-22

- Component 0: fixes the random crash when leaving the multiplayer lobby
  (for example *Local network game > Load*) on BG:EE, BG2:EE, EET and IWD:EE
  2.7.3.0 with EEex v1.2.0 / v1.3.1. Two hooks keep every lobby task on the
  lobby's own network thread (`M_CZMP.lua`, patterns in `CZMP.db`).
- Component 1: a Load screen button copies a save between the single-player
  and the multiplayer saves (`M_CZMS.lua`, `CZMS.menu`). IWD:EE gets a Copy
  button in every save row; BG:EE, BG2:EE and EET get one button that copies
  the selected save.
