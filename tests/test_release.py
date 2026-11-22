"""The release archive: committed files only, nothing in the game's root but the setup."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import build_release  # noqa: E402


@pytest.fixture(scope="module")
def official_weidu():
    configured = os.environ.get("WEIDU_EXE")
    if not configured or not Path(configured).is_file():
        pytest.skip("set WEIDU_EXE to the official WeiDU 249 x64 weidu.exe")
    if hashlib.sha256(Path(configured).read_bytes()).hexdigest() != build_release.WEIDU_SHA256:
        pytest.skip("WEIDU_EXE is not the official WeiDU 249 x64 weidu.exe")
    return Path(configured)


def blob(path):
    return subprocess.run(["git", "cat-file", "blob", f"HEAD:{path}"], cwd=ROOT, check=True,
                          capture_output=True).stdout


def test_the_archive_holds_the_committed_mod_and_its_docs(official_weidu, tmp_path):
    zip_path, sha_path = build_release.build_release("HEAD", official_weidu, tmp_path / "a")
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(zf.namelist())
        assert names == sorted(
            ["setup-chriz_multiplayer_fix.exe", *build_release.MOD_FILES, *build_release.DOC_FILES.values()]
        )
        # Nothing but the setup in the game's root folder.
        assert [n for n in names if "/" not in n] == ["setup-chriz_multiplayer_fix.exe"]
        assert {n.split("/")[0] for n in names if "/" in n} == {"chriz_multiplayer_fix"}
        assert zf.read("setup-chriz_multiplayer_fix.exe") == official_weidu.read_bytes()
        for path in build_release.MOD_FILES:
            assert zf.read(path) == blob(path), path
        for path, arcname in build_release.DOC_FILES.items():
            assert zf.read(arcname) == blob(path), path
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert sha_path.read_text(encoding="utf-8") == f"{digest}  {zip_path.name}\n"
    # The same commit gives the same archive.
    again, _ = build_release.build_release("HEAD", official_weidu, tmp_path / "b")
    assert again.read_bytes() == zip_path.read_bytes()


def test_only_the_official_weidu_is_packed(tmp_path):
    other = tmp_path / "weidu.exe"
    other.write_bytes(b"MZ another program")
    with pytest.raises(ValueError, match="not the official WeiDU 249"):
        build_release.build_release("HEAD", other, tmp_path / "out")


def test_readme_links_work_inside_the_mod_folder():
    """The archive puts README.md next to docs/, CHANGELOG.md and LICENSE."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    shipped = {Path(arc).relative_to("chriz_multiplayer_fix").as_posix() for arc in build_release.DOC_FILES.values()}
    import re
    for target in re.findall(r"\]\((?!https?://)([^)#]+)\)", readme):
        assert target in shipped, target
