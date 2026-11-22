"""Real WeiDU; all installs, backups, logs and removals stay in .test-tmp."""
from pathlib import Path
import shutil
import subprocess

import pytest

from conftest import MOD

TP2 = "chriz_multiplayer_fix/setup-chriz_multiplayer_fix.tp2"

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


def prepare(tmp_path, eeex=True, existing=None):
    shutil.copytree(MOD, tmp_path / "chriz_multiplayer_fix", ignore=shutil.ignore_patterns("backup"))
    (tmp_path / "override").mkdir()
    if eeex:
        (tmp_path / "override/M___EEex.lua").write_text("-- EEex presence fixture\n")
        (tmp_path / "EEex_scripts/extra_pattern_dbs").mkdir(parents=True)
        (tmp_path / "EEex_scripts/extra_pattern_dbs/v2.7.3.0.db").write_text("[Other]\nPattern=90\n")
    for path, contents in (existing or {}).items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(contents)
    # Deliberately arbitrary game data: the mod never inspects or gates on it.
    (tmp_path / "override/fixture.spl").write_bytes(b"hand-edited effects and other text\0\xff")
    (tmp_path / "dialog.tlk").write_bytes(b"unrelated localized text\0")
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
        cwd=folder, input="", capture_output=True, text=True, errors="replace", timeout=60,
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


def test_weidu_parse(weidu, tmp_path):
    prepare(tmp_path)
    output = invoke(weidu, tmp_path, "--parse-check", "TP2", TP2)
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
        cwd=tmp_path, input="", capture_output=True, text=True, errors="replace", timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "ERROR" not in output and "WARNING" not in output, output
    for files in PAYLOAD.values():
        for target, source in files.items():
            assert (tmp_path / target).read_bytes() == source.read_bytes()
    assert len(active_rows(tmp_path)) == 2


@pytest.mark.parametrize("existing", (None, b"-- an older or hand-edited copy\n\xff"))
def test_install_reinstall_uninstall(weidu, tmp_path, existing):
    old = {target: existing for c in PAYLOAD.values() for target in c} if existing else {}
    preserved = prepare(tmp_path, existing=old)
    for _ in range(2):
        invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
        for files in PAYLOAD.values():
            for target, source in files.items():
                assert (tmp_path / target).read_bytes() == source.read_bytes()
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
    for name, files in PAYLOAD.items():
        for target in files:
            assert (tmp_path / target).exists() == (name == component)


def test_missing_eeex_installs_as_logged_noop(weidu, tmp_path):
    preserved = prepare(tmp_path, eeex=False)
    output = invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
    assert output.count("the lobby crash fix is inactive; EEex is required") == 1
    assert output.count("the save copy button is inactive; EEex is required") == 1
    for files in PAYLOAD.values():
        for target in files:
            assert not (tmp_path / target).exists()
    assert len(active_rows(tmp_path)) == 2
    assert_unchanged(tmp_path, preserved)
    # Installing EEex later and reinstalling enables both.
    (tmp_path / "override/M___EEex.lua").write_text("-- EEex installed later")
    (tmp_path / "EEex_scripts/extra_pattern_dbs").mkdir(parents=True)
    invoke(weidu, tmp_path, TP2, "--force-install-list", "0", "1")
    for files in PAYLOAD.values():
        for target, source in files.items():
            assert (tmp_path / target).read_bytes() == source.read_bytes()
