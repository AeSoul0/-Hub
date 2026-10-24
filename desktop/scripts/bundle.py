"""
@file desktop/scripts/bundle.py
@description Assemble the resources the desktop installer ships (M14, ADR-020).

    python desktop/scripts/bundle.py --pg-root "C:/Program Files/PostgreSQL/17"

Output, in desktop/src-tauri/resources/ (gitignored):

    python/     the CPython interpreter running this script, with a clean
                site-packages holding only backend/requirements-desktop.txt
    backend/    app/, main.py, desktop.py and the keyring code of
                scripts/aehub.py (as aehub_launcher.py)
    frontend/   the static export (frontend/out, AEHUB_STATIC_EXPORT=1)
    postgres/   bin/, lib/, share/ of the PostgreSQL install, which must
                already hold pgvector (vector.control)

Only the standard library is used.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404 - runs the bundled interpreter only
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "desktop" / "src-tauri" / "resources"

# Parts of a CPython or PostgreSQL install the app never uses.
SKIP_ALWAYS = {"__pycache__", "*.pyc", "*.pdb"}
SKIP_PYTHON = {"Doc", "include", "libs", "tcl", "Tools", "test", "idlelib", "tkinter", "turtledemo"}
SKIP_POSTGRES = {"doc", "include", "symbols", "pgAdmin 4", "StackBuilder", "*.lib"}


def ignore(names_to_skip: set):
    return shutil.ignore_patterns(*(SKIP_ALWAYS | names_to_skip))


def folder_size(path: Path) -> str:
    total = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return f"{total / 1_000_000:.0f} MB"


def bundle_python(out: Path) -> Path:
    home = Path(sys.base_prefix)
    target = out / "python"
    shutil.copytree(home, target, ignore=ignore(SKIP_PYTHON))

    # Whatever the build machine installed stays behind: a fresh pip, then
    # exactly the desktop requirements.
    site_packages = target / "Lib" / "site-packages"
    shutil.rmtree(site_packages, ignore_errors=True)
    site_packages.mkdir(parents=True)

    python = target / ("python.exe" if sys.platform == "win32" else "bin/python3")
    run = [str(python), "-I", "-m"]
    subprocess.run([*run, "ensurepip", "--upgrade"], check=True)  # nosec B603
    subprocess.run(  # nosec B603
        [
            *run, "pip", "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            "-r", str(ROOT / "backend" / "requirements-desktop.txt"),
        ],
        check=True,
    )
    return target


def bundle_backend(out: Path) -> Path:
    target = out / "backend"
    shutil.copytree(ROOT / "backend" / "app", target / "app", ignore=ignore(set()))

    for name in ("main.py", "desktop.py", "requirements-desktop.txt"):
        shutil.copy2(ROOT / "backend" / name, target / name)

    shutil.copy2(ROOT / "scripts" / "aehub.py", target / "aehub_launcher.py")
    return target


def bundle_frontend(out: Path) -> Path:
    source = ROOT / "frontend" / "out"

    if not (source / "index.html").is_file():
        raise SystemExit("frontend/out is missing: build it with AEHUB_STATIC_EXPORT=1 npm run build")

    target = out / "frontend"
    shutil.copytree(source, target)
    return target


def bundle_postgres(out: Path, pg_root: Path) -> Path:
    if not list((pg_root / "share").rglob("vector.control")):
        raise SystemExit(f"pgvector is not installed in {pg_root}: build it first (nmake /F Makefile.win install)")

    target = out / "postgres"

    for part in ("bin", "lib", "share"):
        shutil.copytree(pg_root / part, target / part, ignore=ignore(SKIP_POSTGRES))

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pg-root", required=True, help="PostgreSQL install with pgvector")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    for name, built in (
        ("frontend", bundle_frontend(out)),
        ("backend", bundle_backend(out)),
        ("postgres", bundle_postgres(out, Path(args.pg_root))),
        ("python", bundle_python(out)),
    ):
        print(f"{name:9} {folder_size(built):>8}  {built}")

    print(f"{'total':9} {folder_size(out):>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
