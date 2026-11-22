from pathlib import Path
import os
import re
import shutil
import struct
import sys

# Optional local wheel/site-packages directory when testing without a dedicated venv.
if extra_libs := os.environ.get("CZMP_PYLIBS"):
    if Path(extra_libs).is_dir() and extra_libs not in sys.path:
        sys.path.insert(0, extra_libs)

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "chriz_multiplayer_fix"
DB_PATTERNS = re.findall(
    r"^Pattern=([0-9A-F?]+)\s*$", (MOD / "lua/CZMP.db").read_text(encoding="utf-8"), re.M
)


def pattern_bytes(pattern, filler=0xCC):
    return bytes(
        filler if pattern[i:i + 2] == "??" else int(pattern[i:i + 2], 16)
        for i in range(0, len(pattern), 2)
    )


def write_fake_exe(path, code=(), data=(), machine=0x8664):
    """A minimal 64-bit PE: a .text (code) and a .rdata section holding the given bytes."""
    def section(blobs):
        body = b"\x90" * 64 + b"".join(blob + b"\x90" * 64 for blob in blobs)
        return body + b"\0" * (-len(body) % 0x200)

    text, rdata = section(code), section(data)
    headers = bytearray(0x400)
    headers[0:2] = b"MZ"
    struct.pack_into("<I", headers, 0x3C, 0x80)
    headers[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", headers, 0x84, machine, 2, 0, 0, 0, 0xF0, 0x22)
    struct.pack_into("<H", headers, 0x98, 0x20B)
    table = 0x98 + 0xF0
    for index, (name, size, raw, flags) in enumerate((
        (b".text", len(text), 0x400, 0x60000020),
        (b".rdata", len(rdata), 0x400 + len(text), 0x40000040),
    )):
        entry = table + index * 40
        headers[entry:entry + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", headers, entry + 8, size, 0x1000 * (index + 1), size, raw)
        struct.pack_into("<I", headers, entry + 36, flags)
    path.write_bytes(bytes(headers) + text + rdata)


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
