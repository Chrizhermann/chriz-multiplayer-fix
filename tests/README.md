# Offline tests

```powershell
python -X utf8 -m pytest -q
```

Without external files the LuaJIT runtime tests (lupa) and the pattern/Lua
consistency checks run on their own; the save copy tests copy real files in the
pytest temp folder (Windows only). Set these to run the rest:

- `WEIDU_EXE`: a WeiDU 249 executable (`test_installer.py`)
- `CZMP_BGEE_EXE`: BG:EE 2.7.3.0 `Baldur.exe`
- `CZMP_BG2EE_EXE`: BG2:EE 2.7.3.0 `Baldur.exe` (EET uses it too)
- `CZMP_IWDEE_EXE`: IWD:EE 2.7.3.0 `Icewind.exe`
- `CZMP_PYLIBS`: optional site-packages folder added to `sys.path`
