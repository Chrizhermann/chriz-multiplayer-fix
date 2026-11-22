"""CZMP.db against M_CZMP.lua, and against local 2.7.3.0 executables when configured."""
import os
import re
from pathlib import Path

import pytest

from conftest import MOD

DB = (MOD / "lua/CZMP.db").read_text(encoding="utf-8")
LUA = (MOD / "lua/M_CZMP.lua").read_text(encoding="utf-8")
PATTERNS = dict(re.findall(r"^\[(.+?)\]\s*\nPattern=([0-9A-F?]+)\s*\nNoCache=1$", DB, re.M))

EXES = {
    "bgee": "CZMP_BGEE_EXE",
    "bg2ee": "CZMP_BG2EE_EXE",
    "iwdee": "CZMP_IWDEE_EXE",
}


def lua_number(name):
    return int(re.search(rf"^local {name} = (0x[0-9A-F]+)", LUA, re.M).group(1), 16)


def lua_expected_bytes(what):
    row = re.search(r"expectBytes\([^,]+, \{ ([^}]+) \}, \"" + re.escape(what) + '"', LUA).group(1)
    return bytes(int(b, 16) for b in row.replace(" ", "").split(","))


def to_regex(pattern):
    return re.compile(
        b"".join(
            b"." if pattern[i:i + 2] == "??" else re.escape(bytes.fromhex(pattern[i:i + 2]))
            for i in range(0, len(pattern), 2)
        ),
        re.S,
    )


def test_every_label_has_one_pattern():
    labels = set(re.findall(r'EEex_TryLabel\("([^"]+)"\)', LUA))
    assert labels == set(PATTERNS) == {
        "CZMP-XmppPump::WakeTasks", "CZMP-XmppThread::XmppThread", "CZMP-talk_base::Thread::Start",
    }


def test_hook_sites_lie_inside_the_wake_pattern():
    pattern = PATTERNS["CZMP-XmppPump::WakeTasks"]
    for offset, what in (
        (lua_number("WAKE_HOOK_AT"), "the lobby wake-up"),
        (lua_number("ON_MESSAGE"), "the lobby task runner"),
    ):
        expected = lua_expected_bytes(what)
        assert pattern[offset * 2:(offset + len(expected)) * 2] == expected.hex().upper(), what


def test_layout_offsets_are_in_the_patterns():
    thread = PATTERNS["CZMP-XmppThread::XmppThread"]
    assert "498DB710010000" in thread          # lea rsi,[r15+110h]: XmppThread::notify_
    assert "4D89B720010000" in thread          # mov [r15+120h],r14: XmppThread::pump_
    assert "4989B688000000" in thread          # mov [r14+88h],rsi: XmppPump::notify_
    start = PATTERNS["CZMP-talk_base::Thread::Start"]
    assert "80B9FC00000000" in start           # cmp byte [rcx+0FCh],0: started_
    assert "4C8D8308010000" in start           # lea r8,[rbx+108h]: thread_id_
    assert lua_number("PUMP_NOTIFY") == 0x88
    assert re.search(r"^local NOTIFY_PUMP = 0x10 ", LUA, re.M)
    assert re.search(r"^local NOTIFY_THREAD = 0x110 ", LUA, re.M)
    assert re.search(r"^local NOTIFY_STARTED = 0x110 - 0xFC ", LUA, re.M)
    assert re.search(r"^local NOTIFY_THREAD_ID = 0x110 - 0x108 ", LUA, re.M)


@pytest.mark.parametrize("game", sorted(EXES))
def test_patterns_match_once_in_the_executable(game):
    configured = os.environ.get(EXES[game])
    if not configured or not Path(configured).is_file():
        pytest.skip(f"set {EXES[game]} to a 2.7.3.0 executable")
    data = Path(configured).read_bytes()
    for label, pattern in PATTERNS.items():
        matches = [m.start() for m in to_regex(pattern).finditer(data)]
        assert len(matches) == 1, (label, matches)
