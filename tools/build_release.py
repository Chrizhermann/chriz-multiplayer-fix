"""Build a reproducible Windows release archive and SHA-256 checksum for Chriz Multiplayer Fix."""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TP2_PATH = REPO_ROOT / "chriz_multiplayer_fix" / "setup-chriz_multiplayer_fix.tp2"
VERSION_RE = re.compile(r"^VERSION\s+~v?([^~\s]+)~", re.MULTILINE)
FIXED_ZIP_DT = (2026, 11, 22, 0, 0, 0)

ALLOWLIST = (
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "docs/compatibility.md",
    "chriz_multiplayer_fix/setup-chriz_multiplayer_fix.tp2",
    "chriz_multiplayer_fix/lib/czmp_preflight.tpa",
    "chriz_multiplayer_fix/lua/CZMP.db",
    "chriz_multiplayer_fix/lua/CZMS.menu",
    "chriz_multiplayer_fix/lua/M_CZMP.lua",
    "chriz_multiplayer_fix/lua/M_CZMS.lua",
)


def read_tp2_version() -> str:
    match = VERSION_RE.search(TP2_PATH.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"Could not find VERSION in {TP2_PATH}")
    return match.group(1)


def _write_deterministic(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    data = src.read_bytes()
    info = zipfile.ZipInfo(filename=arcname, date_time=FIXED_ZIP_DT)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_release(version: str, weidu_path: Path, out_dir: Path) -> tuple[Path, Path]:
    clean_version = version.lstrip("v")
    tp2_version = read_tp2_version()
    if clean_version != tp2_version:
        raise ValueError(
            f"Requested version {clean_version!r} does not match .tp2 VERSION {tp2_version!r}"
        )
    if not weidu_path.is_file():
        raise FileNotFoundError(f"WeiDU binary not found: {weidu_path}")

    mod_files = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "chriz_multiplayer_fix").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )
    expected_mod_files = sorted(p for p in ALLOWLIST if p.startswith("chriz_multiplayer_fix/"))
    if mod_files != expected_mod_files:
        raise ValueError(
            f"chriz_multiplayer_fix/ contents {mod_files} do not match allowlist {expected_mod_files}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"chriz-multiplayer-fix-v{clean_version}.zip"
    zip_path = out_dir / zip_name
    sha_path = out_dir / f"{zip_name}.sha256"

    entries: list[tuple[str, Path]] = [("setup-chriz_multiplayer_fix.exe", weidu_path)]
    for rel in ALLOWLIST:
        src = REPO_ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(f"Missing required release file: {rel}")
        entries.append((rel, src))

    with zipfile.ZipFile(zip_path, "w") as zf:
        for arcname, src in sorted(entries, key=lambda item: item[0]):
            _write_deterministic(zf, src, arcname)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_name}\n", encoding="utf-8", newline="\n")
    return zip_path, sha_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Package Chriz Multiplayer Fix release zip and sha256.")
    ap.add_argument("--version", default=None, help="Release version (defaults to .tp2 VERSION)")
    ap.add_argument("--weidu", required=True, type=Path, help="Path to x64 weidu.exe")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    args = ap.parse_args()

    version = args.version or read_tp2_version()
    zip_path, sha_path = build_release(version, args.weidu, args.out_dir)
    print(f"Built {zip_path} ({zip_path.stat().st_size} bytes)")
    print(sha_path.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
