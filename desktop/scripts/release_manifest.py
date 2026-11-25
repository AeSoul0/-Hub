"""
@file desktop/scripts/release_manifest.py
@description latest.json for the Tauri updater (M15, ADR-021).

    python desktop/scripts/release_manifest.py --tag v1.0.0 --bundle desktop/src-tauri/target/release/bundle/nsis

The installed app reads it from the latest GitHub Release and accepts the
installer only if its minisign signature (the .sig next to it, made with the
updater's private key in CI) matches the public key in tauri.conf.json.
Only the standard library is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = "AeSoul0/-Hub"


def manifest(tag: str, bundle: Path) -> dict:
    installers = sorted(bundle.glob("*-setup.exe"))

    if len(installers) != 1:
        raise SystemExit(f"Expected one *-setup.exe in {bundle}, found {[path.name for path in installers]}")

    installer = installers[0]
    signature = installer.with_name(installer.name + ".sig")

    if not signature.is_file():
        raise SystemExit(f"{signature.name} is missing: build with the updater's signing key")

    return {
        "version": tag.lstrip("v"),
        "notes": f"ÆHub {tag}",
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": {
            "windows-x86_64": {
                "signature": signature.read_text(encoding="utf-8").strip(),
                "url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{installer.name}",
            }
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write latest.json for the Tauri updater")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", default="latest.json")
    args = parser.parse_args()

    Path(args.out).write_text(json.dumps(manifest(args.tag, Path(args.bundle)), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
