"""
Frontend build test — verifies that the TypeScript + Vite build completes
without errors. This catches type errors in any .tsx/.ts file.

Requires Node/npm to be available on PATH.
"""
import subprocess
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def test_frontend_typecheck_and_build():
    """Run `npm run build` (which runs tsc -b first) and assert it succeeds."""
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        # Print output to help diagnose
        pytest.fail(
            f"Frontend build failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_frontend_dist_exists_after_build():
    """After build, dist/index.html must exist (what main.py looks for)."""
    index = FRONTEND_DIR / "dist" / "index.html"
    assert index.exists(), (
        f"dist/index.html not found at {index}. "
        "Run: cd frontend && npm run build"
    )


def test_campaigns_tab_exported():
    """CampaignsTab.tsx must export CampaignsTab as a named export."""
    src = FRONTEND_DIR / "src" / "components" / "CampaignsTab.tsx"
    assert src.exists(), "CampaignsTab.tsx is missing"
    content = src.read_text()
    assert "export function CampaignsTab" in content, (
        "CampaignsTab.tsx must have 'export function CampaignsTab'"
    )


def test_app_imports_campaigns_tab():
    """App.tsx must import CampaignsTab and render it somewhere."""
    app = FRONTEND_DIR / "src" / "App.tsx"
    content = app.read_text()
    assert "CampaignsTab" in content, "App.tsx must import/use CampaignsTab"


def test_api_ts_has_beyond_url():
    """api.ts Campaign interface must have beyond_url field."""
    api_ts = FRONTEND_DIR / "src" / "lib" / "api.ts"
    content = api_ts.read_text()
    assert "beyond_url" in content, "Campaign interface in api.ts must have beyond_url"


def test_api_ts_has_update_campaign():
    """api.ts PyWebViewAPI interface must declare update_campaign."""
    api_ts = FRONTEND_DIR / "src" / "lib" / "api.ts"
    content = api_ts.read_text()
    assert "update_campaign" in content, "PyWebViewAPI in api.ts must declare update_campaign"
