"""
Dependency version checker and auto-upgrader.

Runs on startup in a background thread. Checks whether GUI-side packages are
up to date (pywebview, anthropic, openai, sounddevice, keyring) and upgrades
them if outdated. Whisperx and torch are excluded — they require careful
version pinning and are managed separately.

In a bundled .app the updater is disabled (can't pip-upgrade a frozen bundle).
"""
import json
import subprocess
import sys
import threading
from typing import Callable, Optional

# Minimum required versions — anything below these is considered outdated.
# Bump these when you know a newer version fixes a real issue.
MIN_VERSIONS: dict[str, tuple] = {
    "pywebview":  (6, 1),
    "anthropic":  (0, 40, 0),
    "openai":     (1, 0, 0),
    "sounddevice":(0, 4, 6),
    "keyring":    (25, 0, 0),
    "numpy":      (1, 24, 0),
}

# Packages to auto-upgrade when outdated (subset of MIN_VERSIONS)
AUTO_UPGRADE = {"anthropic", "openai", "keyring"}

_IS_FROZEN = getattr(sys, "frozen", False)


def _parse_version(v: str) -> tuple:
    """'1.2.3a0' → (1, 2, 3)"""
    import re
    parts = re.split(r"[^0-9]+", v)
    nums = []
    for p in parts:
        if p.isdigit():
            nums.append(int(p))
        else:
            break
    return tuple(nums)


def _installed_versions() -> dict[str, tuple]:
    """Return {package_name: version_tuple} for installed packages."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=15
        )
        pkgs = json.loads(result.stdout)
        return {p["name"].lower(): _parse_version(p["version"]) for p in pkgs}
    except Exception:
        return {}


def _upgrade(package: str) -> bool:
    """Upgrade a single package. Returns True on success."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", package],
            capture_output=True, timeout=120
        )
        return True
    except Exception:
        return False


def check_and_upgrade(
    on_status: Optional[Callable[[str], None]] = None
) -> None:
    """
    Run in a background thread. Checks versions and auto-upgrades stale packages.
    `on_status` is called with a human-readable status message when something noteworthy happens.
    """
    if _IS_FROZEN:
        return  # cannot upgrade a bundled .app

    installed = _installed_versions()
    upgraded = []
    missing = []

    for pkg, min_ver in MIN_VERSIONS.items():
        key = pkg.lower()
        if key not in installed:
            missing.append(pkg)
            if pkg in AUTO_UPGRADE:
                _upgrade(pkg)
        elif installed[key] < min_ver:
            if pkg in AUTO_UPGRADE:
                if on_status:
                    on_status(f"Upgrading {pkg}…")
                if _upgrade(pkg):
                    upgraded.append(pkg)

    if upgraded and on_status:
        on_status(f"Updated: {', '.join(upgraded)}")
    if missing and on_status:
        on_status(f"Missing (reinstall from requirements.txt): {', '.join(missing)}")


def run_in_background(on_status: Optional[Callable[[str], None]] = None) -> None:
    """Start the check in a daemon thread so it never blocks the UI."""
    t = threading.Thread(target=check_and_upgrade, args=(on_status,), daemon=True)
    t.start()
