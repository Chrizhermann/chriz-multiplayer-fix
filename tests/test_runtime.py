"""Run the shipping Lua on LuaJIT 2.1 with EEex and engine stubs; no game process.

The save copy tests copy real files with the module's own Windows FFI calls,
inside the pytest temp folder.
"""
import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from lupa import luajit21  # noqa: E402

from conftest import MOD  # noqa: E402

CZMP = (MOD / "lua/M_CZMP.lua").read_text(encoding="utf-8")
CZMS = (MOD / "lua/M_CZMS.lua").read_text(encoding="utf-8")

WAKE = 0x140100000
WAKE_BYTES = bytes.fromhex("488D53F8C64424200045 33C9".replace(" ", ""))
ON_MESSAGE_BYTES = bytes.fromhex("4883C10833D2E9")


def new_runtime():
    lua = luajit21.LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        printed = {}
        print = function(...)
            local parts = {}
            for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
            printed[#printed + 1] = table.concat(parts, " ")
        end
    """)
    return lua


# --- Lobby crash fix -------------------------------------------------------


def fix_runtime(labels=True, wake_bytes=WAKE_BYTES, eeex=True):
    lua = new_runtime()
    lua.execute("""
        memory, hooks, listeners = {}, {}, {}
        EEex_ReadU8 = function(address) return memory[address] or 0 end
        EEex_Malloc = function(size) return 0x7000 end
        EEex_WritePtr = function() end
        EEex_Read64 = function() return 0 end
        EEex_DisableCodeProtection = function() end
        EEex_EnableCodeProtection = function() end
        EEex_HookIntegrityWatchdogRegister = { RAX = 1, RCX = 2, R10 = 3, R11 = 4 }
        EEex_HookBeforeRestoreWithLabels = function(address, a, b, c, labels, asm)
            hooks[#hooks + 1] = { address = address, a = a, b = b, c = c, asm = table.concat(
                (function() local t = {} for _, v in ipairs(asm) do t[#t + 1] = tostring(v) end return t end)()) }
            memory[address] = 0xE9
        end
        EEex_GameState_AddInitializedListener = function(f) listeners[#listeners + 1] = f end
    """)
    if eeex:
        lua.execute("EEex_Active = true")
    known = lua.eval("{}")
    if labels:
        known["CZMP-XmppPump::WakeTasks"] = WAKE
        known["CZMP-XmppThread::XmppThread"] = 0x140200000
        known["CZMP-talk_base::Thread::Start"] = 0x140300000
    lua.globals().known_labels = known
    lua.execute("EEex_TryLabel = function(name) return known_labels[name] end")
    memory = lua.globals().memory
    for i, byte in enumerate(wake_bytes):
        memory[WAKE + 0x16 + i] = byte
    for i, byte in enumerate(ON_MESSAGE_BYTES):
        memory[WAKE + 0xB0 + i] = byte
    return lua


def start(lua, source=CZMP):
    """Load the file, then run the listeners this load added, as the game does."""
    before = len(lua.globals().listeners)
    lua.execute(source)
    for index in range(before + 1, len(lua.globals().listeners) + 1):
        lua.globals().listeners[index]()


def test_fix_installs_both_hooks():
    lua = fix_runtime()
    start(lua)
    state = lua.globals().CZMP_LobbyFix
    assert state.Status == "active" and state.installed
    hooks = list(lua.globals().hooks.values())
    assert [(h.address, h.a, h.b, h.c) for h in hooks] == [(WAKE + 0x16, 0, 9, 9), (WAKE + 0xB0, 0, 6, 6)]
    assert "mov r10, qword ptr ds:[rbx+128]" in hooks[0].asm  # notify_ (0x88) seen from pump + 8
    assert "jmp #L(czmp_wake_tasks)" in hooks[1].asm
    assert list(lua.globals().printed.values()) == ["Multiplayer lobby fix: active"]
    # A second load of the file (menu reload) adds nothing.
    start(lua)
    assert len(lua.globals().hooks) == 2


def test_changed_code_leaves_the_game_as_it_was():
    lua = fix_runtime(wake_bytes=b"\x90" + WAKE_BYTES[1:])
    start(lua)
    state = lua.globals().CZMP_LobbyFix
    assert not state.installed and "changed or another mod already hooked it" in state.Status
    assert len(lua.globals().hooks) == 0


def test_unknown_build_leaves_the_game_as_it_was():
    lua = fix_runtime(labels=False)
    start(lua)
    assert "not found" in lua.globals().CZMP_LobbyFix.Status
    assert len(lua.globals().hooks) == 0


def test_without_eeex_nothing_is_queued():
    lua = fix_runtime(eeex=False)
    start(lua)
    assert lua.globals().CZMP_LobbyFix.Status == "EEex is required"
    assert len(lua.globals().listeners) == 0


# --- Save copy button ------------------------------------------------------


def button_runtime(menu_items, multiplayer=True):
    lua = new_runtime()
    lua.execute("""
        EEex_Active = true
        engine_name = "Test Engine"
        uiStrings = {}
        getUiString = function(key) return uiStrings[key] or key end
        uiItemType = { ITEM_BUTTON = 2 }
        injected, listeners, popups, infos, loaded = {}, {}, {}, {}, {}
        popup2Button = function(info, okText, okFunc, cancelText)
            popups[#popups + 1] = { info = info, okText = okText, ok = okFunc, cancelText = cancelText }
        end
        popupInfo = function(text) infos[#infos + 1] = text end
        EEex_Menu_AddAfterMainFileLoadedListener = function(f) listeners[#listeners + 1] = f end
        EEex_Menu_LoadFile = function(name) loaded[#loaded + 1] = { name = name, text = uiStrings.CZMS_COPY } end
        EEex_Menu_GetItemVariant = function(value) return value end
        local function makeItem(t, x, y, w, h, bam)
            return { type = t, area = { x = x, y = y, w = w, h = h },
                     bam = { resref = bam, sequence = 0, scaletoclip = 0 },
                     pad = { x = 1, y = 2, w = 3, h = 4 } }
        end
        function buildMenu(rows)
            local first, last
            for _, r in ipairs(rows) do
                local item = makeItem(r[1], r[2], r[3], r[4], r[5], r[6])
                if last then last.next = item else first = item end
                last = item
            end
            menu = { items = first }
        end
        EEex_Menu_Find = function(name) return name == "LOAD" and menu or nil end
        EEex_Menu_InjectTemplateInstance = function(menuName, template, id, x, y, w, h)
            local item = { area = { x = x, y = y, w = w, h = h }, bam = {}, pad = {} }
            injected[#injected + 1] = { menu = menuName, template = template, id = id, item = item }
            return item
        end
        e = { IsMultiplayer = function(self) return multiplayer end }
    """)
    lua.globals().multiplayer = multiplayer
    rows = lua.table_from([lua.table_from(r) for r in menu_items])
    lua.globals().buildMenu(rows)
    lua.execute(CZMS)
    for listener in list(lua.globals().listeners.values()):
        listener()
    return lua


IWD_ITEMS = [
    (2, 0, 0, 1024, 768, None), (0, 126, 22, 766, 50, None), (3, 20, 126, 934, 580, None),
]
for row, y in enumerate((130, 276, 422, 566)):
    IWD_ITEMS += [(2, 26, y, 164, 132, None), (0, 216, y + 8, 466, 28, None), (0, 216, y + 42, 466, 24, None)]
    IWD_ITEMS += [(2, x, y + 78, 30, 48, None) for x in (316, 378, 440, 502, 564, 626)]
    IWD_ITEMS += [(2, 712, y + 34, 204, 44, "GUIBUTNT"), (2, 712, y + 82, 204, 44, "GUIBUTNT")]
IWD_ITEMS.append((2, 634, 710, 302, 44, "GUIBUTWT"))

BG_ITEMS = [
    (2, 0, 0, 1024, 768, None), (0, 162, 16, 700, 30, None), (3, 40, 60, 940, 620, None),
    (2, 622, 710, 204, 44, "GUIOSTLM"), (2, 410, 710, 204, 44, "GUIOSTLM"), (2, 200, 710, 204, 44, "GUIOSTLM"),
]


def layout(lua):
    found = lua.globals().CZMS.Layout
    return found.kind, list(found.spots.values())


def test_iwd_gets_a_copy_button_per_row():
    lua = button_runtime(IWD_ITEMS)
    assert layout(lua) == ("rows", ["216 210 92 44", "216 356 92 44", "216 502 92 44", "216 646 92 44"])
    injected = list(lua.globals().injected.values())
    assert [(i.template, i.id) for i in injected] == [("CZMS_TEMPLATE_RowButton", n) for n in (1, 2, 3, 4)]
    assert injected[0].item.bam.resref == "GUIBUTNT" and injected[0].item.bam.scaletoclip == 1
    # The texts exist before the menu file is parsed.
    assert lua.globals().loaded[1].name == "CZMS" and lua.globals().loaded[1].text == "Copy"


def test_bg_gets_one_button_for_the_selected_save():
    lua = button_runtime(BG_ITEMS)
    assert layout(lua) == ("list", ["12 710 173 44"])
    injected = list(lua.globals().injected.values())
    assert [(i.template, i.id) for i in injected] == [("CZMS_TEMPLATE_SelectedButton", 1)]
    assert injected[0].item.bam.resref == "GUIOSTLM" and injected[0].item.bam.scaletoclip == 1


def test_a_free_mirror_spot_keeps_the_row_symmetric():
    lua = button_runtime([(2, 0, 0, 1024, 768, None), (2, 634, 710, 302, 44, "GUIBUTWT")])
    assert layout(lua) == ("list", ["88 710 302 44"])


def saves(lua, names, offset=None, selected=None):
    files = lua.table_from([
        lua.table_from({"fileName": n, "slotName": n.split("-", 1)[1], "chapter": "Chapter Six", "time": "2 days"})
        for n in names
    ])
    lua.globals().gameSaves = lua.table_from({"files": files})
    lua.globals().loadSaveOffset = offset
    lua.globals().currentSave = selected


def test_rows_and_selection_pick_the_right_save():
    lua = button_runtime(IWD_ITEMS, multiplayer=True)
    czms = lua.globals().CZMS
    saves(lua, ["000000003-A", "000000004-B", "000000005-C"], offset=1)
    assert czms.RowEnabled(2) and not czms.RowEnabled(3)
    czms.RowAction(2)
    popup = lua.globals().popups[1]
    assert popup.info.startswith('Copy the save "C" (Chapter Six 2 days) to the single-player saves?')
    assert popup.okText == "CZMS_COPY" and popup.cancelText == "CANCEL_BUTTON"
    assert czms.ButtonText() == "Copy to single player"
    lua.globals().multiplayer = False
    assert czms.ButtonText() == "Copy to multiplayer"
    saves(lua, ["000000003-A", "000000004-B"], selected=None)
    assert not czms.SelectedClickable()
    saves(lua, ["000000003-A", "000000004-B"], selected=2)
    assert czms.SelectedClickable()
    czms.SelectedAction()
    assert '"B"' in lua.globals().popups[2].info and "multiplayer saves" in lua.globals().popups[2].info


def make_save(folder, files):
    folder.mkdir(parents=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)


SAVE_FILES = {"BALDUR.gam": b"GAMEV2.0" + bytes(range(256)), "BALDUR.SAV": b"SAV V1.0\0\xff", "BALDUR.bmp": b"BM"}


@pytest.mark.skipif(os.name != "nt", reason="the copy uses the Windows file functions")
@pytest.mark.parametrize("name", ("pp", "Party-Quick-Save-2", "Ælfric's Rast"))
def test_copy_to_single_player_takes_the_next_free_slot(tmp_path, name):
    lua = button_runtime(IWD_ITEMS)
    profile = tmp_path / "profile"
    make_save(profile / "mpsave" / f"000000052-{name}", SAVE_FILES)
    make_save(profile / "save" / "000000061-RT From MP", {"BALDUR.gam": b"other"})
    make_save(profile / "save" / "000000000-Auto-Save", {"BALDUR.gam": b"auto"})
    lua.globals().test_profile = str(profile)
    lua.execute("CZMS.ProfileFolder = function() return test_profile end")
    folder = lua.globals().CZMS.CopySave(f"000000052-{name}", False)
    assert folder == f"000000062-{name}"
    copy = profile / "save" / folder
    assert {p.name: p.read_bytes() for p in copy.iterdir()} == SAVE_FILES
    assert {p.name: p.read_bytes() for p in (profile / "mpsave" / f"000000052-{name}").iterdir()} == SAVE_FILES


@pytest.mark.skipif(os.name != "nt", reason="the copy uses the Windows file functions")
def test_copy_to_multiplayer_creates_the_folder_and_never_overwrites(tmp_path):
    lua = button_runtime(BG_ITEMS, multiplayer=False)
    profile = tmp_path / "profile"
    make_save(profile / "save" / "000000007-Party", SAVE_FILES)
    lua.globals().test_profile = str(profile)
    lua.execute("CZMS.ProfileFolder = function() return test_profile end")
    czms = lua.globals().CZMS
    assert czms.CopySave("000000007-Party", True) == "000000002-Party"
    assert czms.CopySave("000000007-Party", True) == "000000003-Party"
    assert sorted(p.name for p in (profile / "mpsave").iterdir()) == ["000000002-Party", "000000003-Party"]


@pytest.mark.skipif(os.name != "nt", reason="the copy uses the Windows file functions")
def test_the_whole_flow_from_the_button(tmp_path):
    lua = button_runtime(BG_ITEMS, multiplayer=True)
    profile = tmp_path / "profile"
    make_save(profile / "mpsave" / "000000052-pp hehe", SAVE_FILES)
    lua.globals().test_profile = str(profile)
    lua.execute("CZMS.ProfileFolder = function() return test_profile end")
    saves(lua, ["000000052-pp hehe"], selected=1)
    lua.globals().CZMS.SelectedAction()
    lua.globals().popups[1].ok()
    assert list(lua.globals().infos.values()) == ['Copied. Load "pp hehe" from Single Player > Load Game.']
    assert (profile / "save" / "000000002-pp hehe" / "BALDUR.gam").read_bytes() == SAVE_FILES["BALDUR.gam"]


@pytest.mark.skipif(os.name != "nt", reason="the copy uses the Windows file functions")
def test_a_missing_save_changes_nothing(tmp_path):
    lua = button_runtime(BG_ITEMS, multiplayer=True)
    profile = tmp_path / "profile"
    (profile / "mpsave").mkdir(parents=True)
    lua.globals().test_profile = str(profile)
    lua.execute("CZMS.ProfileFolder = function() return test_profile end")
    saves(lua, ["000000052-gone"], selected=1)
    lua.globals().CZMS.SelectedAction()
    lua.globals().popups[1].ok()
    info = lua.globals().infos[1]
    assert info.startswith("The save could not be copied:") and info.endswith("Nothing was changed.")
    assert not (profile / "save").exists() or not any((profile / "save").iterdir())


def test_without_ffi_the_button_stays_away():
    lua = new_runtime()
    lua.execute("""
        EEex_Active = true
        listeners = {}
        EEex_Menu_AddAfterMainFileLoadedListener = function(f) listeners[#listeners + 1] = f end
        require = function(name) error("module '" .. name .. "' not found") end
    """)
    lua.execute(CZMS)
    assert len(lua.globals().listeners) == 0
    assert list(lua.globals().printed.values()) == ["Save copy button: inactive; it needs EEex running on LuaJIT"]
