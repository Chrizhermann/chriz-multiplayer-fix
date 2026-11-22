"""Build a reproducible Windows release archive and SHA-256 checksum for Chriz Multiplayer Fix.

Every mod and documentation file comes from the Git blobs of one commit (never from the
working tree), and the setup executable is the official WeiDU 249 x64 `weidu.exe`, pinned
by its SHA-256 (the same binary Chriz Easy BG and Chriz Easy IWD pin). The archive holds
`setup-chriz_multiplayer_fix.exe` and the `chriz_multiplayer_fix` folder only, so it never
puts a README or other file into the game's root folder.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_FOLDER = "chriz_multiplayer_fix"
TP2 = f"{MOD_FOLDER}/setup-chriz_multiplayer_fix.tp2"
VERSION_RE = re.compile(r"^VERSION\s+~v?([^~\s]+)~", re.MULTILINE)
FIXED_ZIP_DT = (2026, 11, 22, 0, 0, 0)
# Official WeiDU 249 x64 (WeiDU-Windows-249-amd64.zip, weidu.exe).
WEIDU_SHA256 = "ad70f5897a6d0ba4b0d226f845a9b14cf345f56cc9697ca8d05cac9fe4932c1a"

# The mod itself, as it is in the repository.
MOD_FILES = (
    f"{MOD_FOLDER}/setup-chriz_multiplayer_fix.tp2",
    f"{MOD_FOLDER}/lib/czmp_preflight.tpa",
    f"{MOD_FOLDER}/lua/CZMP.db",
    f"{MOD_FOLDER}/lua/CZMS.menu",
    f"{MOD_FOLDER}/lua/M_CZMP.lua",
    f"{MOD_FOLDER}/lua/M_CZMS.lua",
)
# Documentation, shipped inside the mod folder (repository path -> archive path).
DOC_FILES = {
    "README.md": f"{MOD_FOLDER}/README.md",
    "CHANGELOG.md": f"{MOD_FOLDER}/CHANGELOG.md",
    "LICENSE": f"{MOD_FOLDER}/LICENSE",
    "docs/compatibility.md": f"{MOD_FOLDER}/docs/compatibility.md",
    "docs/images/mp-load-copy-bg.png": f"{MOD_FOLDER}/docs/images/mp-load-copy-bg.png",
    "docs/images/mp-load-copy-iwd.png": f"{MOD_FOLDER}/docs/images/mp-load-copy-iwd.png",
}


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True).stdout


def committed_files(commit: str) -> dict[str, bytes]:
    """Every file of the commit that goes into the archive, from its Git blobs."""
    tracked = git("ls-tree", "-r", "--name-only", commit, "--", MOD_FOLDER).decode().split()
    if sorted(tracked) != sorted(MOD_FILES):
        raise ValueError(f"{MOD_FOLDER}/ in {commit} holds {sorted(tracked)}, expected {sorted(MOD_FILES)}")
    return {path: git("cat-file", "blob", f"{commit}:{path}") for path in (*MOD_FILES, *DOC_FILES)}


def tp2_version(files: dict[str, bytes]) -> str:
    match = VERSION_RE.search(files[TP2].decode("utf-8"))
    if not match:
        raise ValueError(f"Could not find VERSION in {TP2}")
    return match.group(1)


def weidu_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not data.startswith(b"MZ") or hashlib.sha256(data).hexdigest() != WEIDU_SHA256:
        raise ValueError(f"{path} is not the official WeiDU 249 x64 weidu.exe (sha256 {WEIDU_SHA256})")
    return data


def _write_deterministic(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=FIXED_ZIP_DT)
    info.compress_type = zipfile.ZIP_DEFLATED
    # Fixed "made by" system so the bytes do not depend on the OS that builds.
    info.create_system = 3
    info.external_attr = 0o644 << 16
    zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_release(commit: str, weidu_path: Path, out_dir: Path, version: str | None = None) -> tuple[Path, Path]:
    commit = git("rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    files = committed_files(commit)
    clean_version = tp2_version(files)
    if version is not None and version.lstrip("v") != clean_version:
        raise ValueError(f"Requested version {version!r} does not match .tp2 VERSION {clean_version!r}")
    entries = {"setup-chriz_multiplayer_fix.exe": weidu_bytes(weidu_path)}
    entries.update({path: files[path] for path in MOD_FILES})
    entries.update({DOC_FILES[path]: files[path] for path in DOC_FILES})

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"chriz-multiplayer-fix-v{clean_version}.zip"
    zip_path = out_dir / zip_name
    sha_path = out_dir / f"{zip_name}.sha256"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arcname in sorted(entries):
            _write_deterministic(zf, arcname, entries[arcname])

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_name}\n", encoding="utf-8", newline="\n")
    return zip_path, sha_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Package Chriz Multiplayer Fix release zip and sha256.")
    ap.add_argument("--commit", default="HEAD", help="Commit to package (default: HEAD)")
    ap.add_argument("--version", default=None, help="Expected release version (checked against the .tp2)")
    ap.add_argument("--weidu", required=True, type=Path, help="Path to the official WeiDU 249 x64 weidu.exe")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    args = ap.parse_args()

    zip_path, sha_path = build_release(args.commit, args.weidu, args.out_dir, args.version)
    print(f"Built {zip_path} ({zip_path.stat().st_size} bytes)")
    print(sha_path.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
