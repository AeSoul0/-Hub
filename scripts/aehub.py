"""
@file scripts/aehub.py
@description The ÆHub launcher: secrets in the OS keyring, the stack with
Docker Compose (M12).

    python scripts/aehub.py setup       keys into the OS keyring, working folder
    python scripts/aehub.py up          start the stack with the keys from the keyring
    python scripts/aehub.py down        stop the stack
    python scripts/aehub.py secrets     which keys are set (never their values)
    python scripts/aehub.py login-key   print the Control Plane login key

Keys never touch the disk: `up` reads them from the keyring and hands them to
`docker compose` through its environment, and docker-compose.yaml passes them
to the backend container. Keys found in `backend/.env` are moved into the
keyring and removed from the file. Model roles, prices and budget are set in
the Control Plane (Settings), not here.

Keyring: the `keyring` package when installed (Windows Credential Manager,
macOS Keychain, Secret Service on Linux). Without it, Windows Credential
Manager is used directly, so a fresh Windows machine needs only Python.
Elsewhere: `pip install keyring`.

Only the Python standard library is required, as for `make demo`.
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets as token_source
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple


ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = ROOT / ".env"
BACKEND_ENV = ROOT / "backend" / ".env"

SERVICE = "aehub"

# Name -> what it is for. AEHUB_SECRET_KEY is the Control Plane login key.
SECRETS: Dict[str, str] = {
    "AEHUB_SECRET_KEY": "Control Plane login key",
    "OPENAI_API_KEY": "OpenAI models",
    "OPENROUTER_API_KEY": "OpenRouter models",
    "GROQ_API_KEY": "voice transcription (optional)",
    "AEHUB_LOCAL_API_KEY": "local OpenAI-compatible server (optional)",
}

# Values older `make demo` runs wrote as placeholders: not real keys.
PLACEHOLDERS = {"", "not-configured", "changeme", "your-key-here"}


class LauncherError(RuntimeError):
    pass


# ==============================================================================
# KEYRING
# ==============================================================================


class SecretStore(Protocol):
    name: str

    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...


class PackageStore:
    """
    The `keyring` package, with whatever backend it picked for this system.
    """

    def __init__(self, module) -> None:
        self._keyring = module
        self.name = f"keyring ({type(module.get_keyring()).__name__})"

    def get(self, key: str) -> Optional[str]:
        return self._keyring.get_password(SERVICE, key)

    def set(self, key: str, value: str) -> None:
        self._keyring.set_password(SERVICE, key, value)

    def delete(self, key: str) -> None:
        try:
            self._keyring.delete_password(SERVICE, key)
        except Exception:  # keyring raises PasswordDeleteError when absent
            pass


class WindowsCredentialStore:
    """
    Windows Credential Manager through advapi32, readable by the `keyring`
    package too: generic credentials named "<key>@aehub", UTF-16 blobs.
    """

    name = "Windows Credential Manager"

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL
        advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        advapi32.CredDeleteW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None

        self._ctypes = ctypes
        self._credential = CREDENTIAL
        self._api = advapi32

    def _read(self, target: str) -> Optional[Tuple[str, str]]:
        ctypes = self._ctypes
        pointer = ctypes.POINTER(self._credential)()

        if not self._api.CredReadW(target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == self.ERROR_NOT_FOUND:
                return None
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            credential = pointer.contents
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return credential.UserName or "", blob.decode("utf-16-le")
        finally:
            self._api.CredFree(pointer)

    def get(self, key: str) -> Optional[str]:
        found = self._read(f"{key}@{SERVICE}")

        if found is None:
            # Where the `keyring` package writes the first key of a service.
            found = self._read(SERVICE)
            if found is not None and found[0] != key:
                found = None

        return found[1] if found else None

    def set(self, key: str, value: str) -> None:
        ctypes = self._ctypes
        blob = value.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)

        credential = self._credential()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = f"{key}@{SERVICE}"
        credential.UserName = key
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE

        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def delete(self, key: str) -> None:
        self._api.CredDeleteW(f"{key}@{SERVICE}", self.CRED_TYPE_GENERIC, 0)


def open_store() -> SecretStore:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        keyring = None

    if keyring is not None:
        backend = type(keyring.get_keyring()).__name__

        # keyring's "fail" backend means no usable OS keyring was found.
        if "fail" not in backend.lower() and "null" not in backend.lower():
            return PackageStore(keyring)

    if sys.platform == "win32":
        return WindowsCredentialStore()

    raise LauncherError(
        "No OS keyring available. Install one with: pip install keyring\n"
        "(macOS Keychain and the Linux Secret Service are used through it.)"
    )


# ==============================================================================
# ENV FILES
# ==============================================================================


def read_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}

    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def append_env(path: Path, values: Dict[str, str], note: str) -> None:
    if not values:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [] if not existing or existing.endswith("\n") else [""]
    lines.append(f"# {note}")
    lines.extend(f"{key}={value}" for key, value in values.items())
    path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def set_env_value(path: Path, key: str, value: str, note: str) -> None:
    """
    Replace the line of `key`, or append it.
    """
    if not path.exists() or key not in read_env(path):
        append_env(path, {key: value}, note)
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = [
        f"{key}={value}" if line.strip().split("=", 1)[0].strip() == key and not line.strip().startswith("#") else line
        for line in lines
    ]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def remove_env_keys(path: Path, keys: List[str]) -> None:
    if not keys or not path.exists():
        return

    kept = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("#")
        or "=" not in line
        or line.split("=", 1)[0].strip() not in keys
    ]
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


# ==============================================================================
# SETUP
# ==============================================================================


def migrate_env_secrets(store: SecretStore, path: Path = BACKEND_ENV) -> List[str]:
    """
    Move keys from a plaintext env file into the keyring. A key that differs
    from the one already in the keyring stays in the file, with a warning:
    the keyring value is the one the stack uses.
    """
    found = read_env(path)
    moved: List[str] = []
    removable: List[str] = []

    for key in SECRETS:
        if key not in found:
            continue

        value = found[key]

        if value.strip().lower() in PLACEHOLDERS:
            removable.append(key)
            continue

        current = store.get(key)

        if current is None:
            store.set(key, value)
            moved.append(key)
            removable.append(key)
        elif current == value:
            removable.append(key)
        else:
            print(
                f"  ! {key} in {path} differs from the one in the keyring. The keyring "
                "one is used; remove the line from the file once you have checked."
            )

    remove_env_keys(path, removable)
    return moved


def ensure_login_key(store: SecretStore) -> bool:
    """
    Create the Control Plane login key once. Returns True when created.
    """
    if store.get("AEHUB_SECRET_KEY"):
        return False

    store.set("AEHUB_SECRET_KEY", token_source.token_urlsafe(32))
    return True


def ensure_database_password(path: Path = ROOT_ENV) -> bool:
    # The database runs only on this machine, behind the Compose network; its
    # password stays in .env because the postgres container reads it too.
    if "POSTGRES_PASSWORD" in read_env(path):
        return False

    append_env(
        path,
        {"POSTGRES_PASSWORD": token_source.token_urlsafe(24)},
        "Created by the ÆHub launcher: password of the local PostgreSQL container.",
    )
    return True


def has_model_key(store: SecretStore) -> bool:
    return any(store.get(key) for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"))


Ask = Callable[[str, bool], str]


def prompt(question: str, secret: bool = False) -> str:
    return (getpass.getpass(question) if secret else input(question)).strip()


def setup(
    store: SecretStore,
    ask: Ask = prompt,
    root_env: Path = ROOT_ENV,
    backend_env: Path = BACKEND_ENV,
    root: Path = ROOT,
) -> None:
    print(f"Keyring: {store.name}")

    if ensure_database_password(root_env):
        print("  created .env with a random database password")

    moved = migrate_env_secrets(store, backend_env)
    if moved:
        print(f"  moved {', '.join(moved)} from {backend_env.name} into the keyring")

    if ensure_login_key(store):
        print("  created the Control Plane login key (show it with: python scripts/aehub.py login-key)")

    if not has_model_key(store):
        print(
            "\n  A model provider key is needed for the agent to run. Press Enter to\n"
            "  skip one; you can run setup again later.\n"
        )
        for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
            value = ask(f"  {key} (hidden): ", True)
            if value:
                store.set(key, value)
                print(f"  saved {key} in the keyring")
                break

    if not store.get("GROQ_API_KEY"):
        value = ask("  GROQ_API_KEY for voice input (hidden, Enter to skip): ", True)
        if value:
            store.set("GROQ_API_KEY", value)
            print("  saved GROQ_API_KEY in the keyring")

    current = read_env(root_env).get("AEHUB_WORKSPACE_DIR", "./workspace")
    answer = ask(f"  Working folder for the agent's files [{current}]: ", False) or current
    folder = Path(os.path.expanduser(answer))
    absolute = folder if folder.is_absolute() else root / folder
    absolute.mkdir(parents=True, exist_ok=True)
    set_env_value(
        root_env,
        "AEHUB_WORKSPACE_DIR",
        answer,
        "Folder mounted as the agent's workspace (python scripts/aehub.py setup).",
    )
    print(f"  working folder: {absolute}")

    print(
        "\nNext: python scripts/aehub.py up, then finish the setup (models, prices,\n"
        "budget) at http://localhost:3000/control-plane/setup"
    )


# ==============================================================================
# STACK
# ==============================================================================


def compose_env(store: SecretStore, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    The environment of `docker compose`: the current one plus the keys.
    """
    env = dict(os.environ if base is None else base)

    for key in SECRETS:
        value = store.get(key)
        if value:
            env[key] = value

    return env


def compose(args: List[str], env: Dict[str, str], root: Path = ROOT) -> None:
    if shutil.which("docker") is None:
        raise LauncherError("Docker is required: https://docs.docker.com/get-docker/")

    command = ["docker", "compose", *args]
    print("  $ " + " ".join(command))
    subprocess.run(command, cwd=root, env=env, check=True)


def up(store: SecretStore, build: bool = True, services: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Start the stack with the keys from the keyring. Returns the environment
    handed to compose (for callers that need the login key).
    """
    if not store.get("AEHUB_SECRET_KEY"):
        raise LauncherError("No login key yet: run python scripts/aehub.py setup first.")

    leftovers = [key for key in SECRETS if read_env(BACKEND_ENV).get(key, "").strip().lower() not in PLACEHOLDERS]
    if leftovers:
        print(
            f"  ! {', '.join(leftovers)} still in backend/.env: the keyring values are used. "
            "Run setup to move them."
        )

    env = compose_env(store)
    compose(["up", "-d", *(["--build"] if build else []), *(services or [])], env)
    return env


def secrets_report(store: SecretStore) -> List[str]:
    return [
        f"  {key:<22} {'set' if store.get(key) else 'not set':<8} {purpose}"
        for key, purpose in SECRETS.items()
    ]


# ==============================================================================
# CLI
# ==============================================================================


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="keys into the OS keyring, working folder")
    start = commands.add_parser("up", help="start the stack with the keys from the keyring")
    start.add_argument("--no-build", action="store_true", help="reuse existing images")
    commands.add_parser("down", help="stop the stack")
    commands.add_parser("secrets", help="which keys are set (never their values)")
    commands.add_parser("login-key", help="print the Control Plane login key")
    args = parser.parse_args(argv)

    try:
        if args.command == "down":
            compose(["down"], dict(os.environ))
            return 0

        store = open_store()

        if args.command == "setup":
            setup(store)
        elif args.command == "up":
            up(store, build=not args.no_build)
            print("  Control Plane: http://localhost:3000/control-plane")
        elif args.command == "secrets":
            print(f"Keyring: {store.name}")
            print("\n".join(secrets_report(store)))
        elif args.command == "login-key":
            key = store.get("AEHUB_SECRET_KEY")
            if not key:
                raise LauncherError("No login key yet: run python scripts/aehub.py setup first.")
            print(key)

    except LauncherError as exc:
        print(exc, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
