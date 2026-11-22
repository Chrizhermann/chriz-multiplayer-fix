"""Real WeiDU; all installs, backups, logs and removals stay in .test-tmp."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from conftest import DB_PATTERNS, MOD, pattern_bytes, write_fake_exe

TP2 = "chriz_multiplayer_fix/setup-chriz_multiplayer_fix.tp2"
INACTIVE = "the lobby crash fix is inactive"

PAYLOAD = {
    "0": {
        Path("override/M_CZMP.lua"): MOD / "lua/M_CZMP.lua",
        Path("EEex_scripts/extra_pattern_dbs/CZMP.db"): MOD / "lua/CZMP.db",
    },
    "1": {
        Path("override/M_CZMS.lua"): MOD / "lua/M_CZMS.lua",
        Path("override/CZMS.menu"): MOD / "lua/CZMS.menu",
    },
}
ALL_PATTERNS = [pattern_bytes(p) for p in DB_PATTERNS]


def prepare(tmp_path, eeex=True, existing=None, exe="match"):
    shutil.copytree(MOD, tmp_path / "chriz_multiplayer_fix", ignore=shutil.ignore_patterns("backup"))
    (tmp_path / "override").mkdir()
    if eeex:
        (tmp_path / "override/M___EEex.lua").write_text("-- EEex presence fixture\n")
        (tmp_path / "EEex_scripts/extra_pattern_dbs").mkdir(parents=True)
        (tmp_path / "EEex_scripts/extra_pattern_dbs/v2.7.3.0.db").write_text("[Other]\nPattern=90\n")
    if exe == "match":
        write_fake_exe(tmp_path / "Baldur.exe", code=ALL_PATTERNS)
    for path, contents in (existing or {}).items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(contents)
    # Deliberately arbitrary game data: the mod never inspects or gates on it.
    (tmp_path / "override/fixture.spl").write_bytes(b"hand-edited effects and other text\0\xff")
    (tmp_path / "dialog.tlk").write_bytes(b"unrelated localized text\0")
    return snapshot(tmp_path)


def snapshot(tmp_path):
    return {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file() and "chriz_multiplayer_fix" not in p.relative_to(tmp_path).parts
        and p.relative_to(tmp_path) not in {q for c in PAYLOAD.values() for q in c}
    }


def invoke(weidu, folder, *args):
    result = subprocess.run(
        [
            str(weidu), "--noautoupdate", "--no-auto-tp2", "--no-exit-pause", "--nogame",
            "--log", "test.debug", *args,
        ],
        cwd=folder, input="", capture_output=True, text=True, errors="replace", timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output
    return output


def active_rows(folder):
    return [
        line for line in (folder / "weidu.log").read_text().splitlines()
        if line.lstrip().startswith("~")
    ]


def assert_unchanged(folder, preserved):
    for path, contents in preserved.items():
        if path.name in {"weidu.log", "test.debug"}:
            continue
        assert (folder / path).read_bytes() == contents, path


def assert_payload(folder, component, present=True):
    for target, source in PAYLOAD[component].items():
        if present:
            assert (folder / target).read_bytes() == source.read_bytes(), target
        else:
            assert not (folder / target).exists(), target


def test_weidu_parse(weidu, tmp_path):
    prepare(tmp_path)
    for tp in (TP2, "chriz_multiplayer_fix/lib/czmp_preflight.tpa"):
        output = invoke(weidu, tmp_path, "--parse-check", "TP2" if tp == TP2 else "TPA", tp)
        assert "24900" in output


def test_setup_executable_finds_nested_tp2(weidu, tmp_path):
    prepare(tmp_path)
    setup = tmp_path / "setup-chriz_multiplayer_fix.exe"
    shutil.copy2(weidu, setup)
    result = subprocess.run(
        [
            str(setup), "--noautoupdate", "--no-exit-pause", "--nogame",
            "--log", "test.debug", "--force-install-list", "0", "1",
        ],
        cwd=tmp_path, input="", capture_output=True, text=True, errors="replace", timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "ERROR" not in output and "WARNING" not in output, output
    assert "the lobby crash fix is installed for Baldur.exe" in output
    assert_payload(tmp_path, "0")
    assert_payload(tmp_path, "1")
    assert len(active_rows(tmp_path)) == 2


@pytest.mark.parametrize("existing", (None, b"-- an older or hand-edited copy\n\xff"))
def test_install_reinstall_uninstall(weidu, tmp_path, existing):
    old = {target: existing for c in PAYLOAD.values() for target in c} if existing else {}
    preserved = prepare(tmp_path, existing=old)
    for _ in range(2):
        invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
        assert_payload(tmp_path, "0")
        assert_payload(tmp_path, "1")
        rows = active_rows(tmp_path)
        assert len(rows) == 2 and "#0 #0" in rows[0] and "#0 #1" in rows[1] and "0.1.0" in rows[0]
        assert_unchanged(tmp_path, preserved)
    invoke(weidu, tmp_path, TP2, "--force-uninstall-list", "0", "1")
    assert not active_rows(tmp_path)
    for files in PAYLOAD.values():
        for target in files:
            if existing is None:
                assert not (tmp_path / target).exists()
            else:
                assert (tmp_path / target).read_bytes() == existing
    assert_unchanged(tmp_path, preserved)


@pytest.mark.parametrize("component", ("0", "1"))
def test_components_are_independent(weidu, tmp_path, component):
    prepare(tmp_path)
    invoke(weidu, tmp_path, TP2, "--force-install-list", component)
    for name in PAYLOAD:
        assert_payload(tmp_path, name, present=(name == component))


def test_missing_eeex_installs_as_logged_noop(weidu, tmp_path):
    preserved = prepare(tmp_path, eeex=False)
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
    assert output.count(INACTIVE + "; EEex is required") == 1
    assert output.count("the save copy button is inactive; EEex is required") == 1
    assert_payload(tmp_path, "0", present=False)
    assert_payload(tmp_path, "1", present=False)
    assert len(active_rows(tmp_path)) == 2
    assert_unchanged(tmp_path, preserved)
    # Installing EEex later and reinstalling enables both.
    (tmp_path / "override/M___EEex.lua").write_text("-- EEex installed later")
    (tmp_path / "EEex_scripts/extra_pattern_dbs").mkdir(parents=True)
    invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
    assert_payload(tmp_path, "0")
    assert_payload(tmp_path, "1")


# --- The pattern check (InfinityLoader does not start a game whose pattern db
# has a pattern without a match) ---------------------------------------------

UNSUPPORTED = {
    "a pattern is missing": (dict(code=ALL_PATTERNS[:-1]), "lacks the lobby code"),
    "a pattern occurs twice": (dict(code=ALL_PATTERNS + ALL_PATTERNS[:1]), "is ambiguous"),
    "a pattern lies outside the code": (dict(code=ALL_PATTERNS[1:], data=ALL_PATTERNS[:1]), "outside the program code"),
    "one byte differs": (
        dict(code=ALL_PATTERNS[:2] + [ALL_PATTERNS[2][:-1] + bytes([ALL_PATTERNS[2][-1] ^ 0xFF])]),
        "lacks the lobby code",
    ),
    "a 32-bit program": (dict(code=ALL_PATTERNS, machine=0x14C), "is not a 64-bit Windows program"),
}


@pytest.mark.parametrize("case", sorted(UNSUPPORTED))
@pytest.mark.parametrize("existing", (None, b"-- a hand-installed copy\n"))
def test_an_unsupported_executable_gets_no_patterns(weidu, tmp_path, case, existing):
    exe, reason = UNSUPPORTED[case]
    old = {target: existing for target in PAYLOAD["0"]} if existing else {}
    preserved = prepare(tmp_path, exe=None, existing=old)
    write_fake_exe(tmp_path / "Baldur.exe", **exe)
    preserved[Path("Baldur.exe")] = (tmp_path / "Baldur.exe").read_bytes()
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
    assert INACTIVE in output and reason in output and "The game starts and plays as before." in output
    # The decided result is the same whatever stood there before: no patterns.
    assert_payload(tmp_path, "0", present=False)
    assert_payload(tmp_path, "1")
    assert len(active_rows(tmp_path)) == 2
    assert_unchanged(tmp_path, {p: c for p, c in preserved.items() if p not in PAYLOAD["0"]})
    invoke(weidu, tmp_path, TP2, "--force-uninstall-list", "0", "1")
    for target in PAYLOAD["0"]:
        if existing is None:
            assert not (tmp_path / target).exists()
        else:
            assert (tmp_path / target).read_bytes() == existing
    assert_unchanged(tmp_path, preserved)


def test_no_executable_gets_no_patterns(weidu, tmp_path):
    prepare(tmp_path, exe=None)
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0")
    assert INACTIVE + "; no game executable was found" in output
    assert_payload(tmp_path, "0", present=False)


@pytest.mark.parametrize("names, used", (
    ("ExeNames=Nope.exe, Custom.exe ,Baldur.exe", "Custom.exe"),
    ("exenames = Baldur.exe", "Baldur.exe"),
))
def test_the_executable_the_loader_starts_is_checked(weidu, tmp_path, names, used):
    prepare(tmp_path, exe=None)
    write_fake_exe(tmp_path / "Baldur.exe", code=ALL_PATTERNS[:1])
    if used == "Custom.exe":
        write_fake_exe(tmp_path / "Custom.exe", code=ALL_PATTERNS)
    else:
        write_fake_exe(tmp_path / "Baldur.exe", code=ALL_PATTERNS)
    (tmp_path / "InfinityLoader.ini").write_bytes(
        b"[General]\r\n; The list of executables\r\n" + names.encode() + b"\r\nOther=1\r\n"
    )
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0")
    assert f"the lobby crash fix is installed for {used}" in output
    assert_payload(tmp_path, "0")


@pytest.mark.parametrize("game, name", (
    ("CZMP_BGEE_EXE", "Baldur.exe"), ("CZMP_BG2EE_EXE", "Baldur.exe"), ("CZMP_IWDEE_EXE", "icewind.exe"),
))
def test_the_real_2_7_3_0_executables_get_the_fix(weidu, tmp_path, game, name):
    configured = os.environ.get(game)
    if not configured or not Path(configured).is_file():
        pytest.skip(f"set {game} to a 2.7.3.0 executable")
    prepare(tmp_path, exe=None)
    shutil.copy2(configured, tmp_path / name)
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0")
    assert f"the lobby crash fix is installed for {name}" in output
    assert_payload(tmp_path, "0")
    assert (tmp_path / name).read_bytes() == Path(configured).read_bytes()
