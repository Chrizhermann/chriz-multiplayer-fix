from pathlib import Path
import os
import shutil
import sys

# Optional local wheel/site-packages directory when testing without a dedicated venv.
if extra_libs := os.environ.get("CZMP_PYLIBS"):
    if Path(extra_libs).is_dir() and extra_libs not in sys.path:
        sys.path.insert(0, extra_libs)

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "chriz_multiplayer_fix"


@pytest.fixture(scope="session")
def weidu(tmp_path_factory):
    configured = os.environ.get("WEIDU_EXE") or shutil.which("weidu")
    if not configured or not Path(configured).is_file():
        pytest.skip("set WEIDU_EXE to a local WeiDU 249 executable")
    tools = tmp_path_factory.mktemp("tools")
    assert tools.resolve().is_relative_to(ROOT)
    target = tools / ("weidu.exe" if os.name == "nt" else "weidu")
    shutil.copy2(configured, target)
    return target
