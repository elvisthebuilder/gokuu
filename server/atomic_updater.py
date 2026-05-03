"""
atomic_updater.py — Versioned, Rollback-Safe Self-Updates
===========================================================
Provides atomic update primitives: version bump, push, rollback.

Designed for:
- Safe CLI update commands
- GitHub Actions integration
- Emergency hotfix deployment

Key Functions:
- update_version(bump: "major"|"minor"|"patch")
- create_release(prerelease=False)
- rollback()
"""

import json
import subprocess
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .state_snapshot import create_git_tag, rollback_to_tag, get_git_head
from .self_health import self_modify_guard, check_self_integrity

logger = logging.getLogger(__name__)

# === Constants ===
VERSION_FILE = Path(__file__).parent.parent / "VERSION"
README_FILE = Path(__file__).parent.parent / "README.md"
GOKUU_ROOT = Path(__file__).parent.parent


def get_current_version() -> str:
    """Read current version from VERSION file or git tag."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    
    # Fallback: use latest git tag
    try:
        result = subprocess.run(
            ["git", "-C", str(GOKUU_ROOT), "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "0.0.0"


def bump_version(current: str, bump: str = "patch") -> str:
    """
    Increment version following semver.
    
    Examples:
        bump_version("3.0.0", "patch") → "3.0.1"
        bump_version("3.0.0", "minor") → "3.1.0"
        bump_version("3.0.0", "major") → "4.0.0"
    """
    major, minor, patch = map(int, current.split("."))
    
    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


def update_version_file(new_version: str) -> None:
    """Write new version to VERSION file."""
    VERSION_FILE.write_text(new_version + "\n")
    logger.info(f"Version updated to {new_version}")


def update_readme_version(new_version: str) -> None:
    """Update version badge in README.md if present."""
    if not README_FILE.exists():
        return
    
    content = README_FILE.read_text()
    old = get_current_version()
    
    # Simple search-and-replace for version badge
    if f"version-{old}" in content or f"{old}.svg" in content:
        new_content = content.replace(old, new_version)
        README_FILE.write_text(new_content)
        logger.info(f"README.md version badge updated to {new_version}")


def _commit_and_tag(new_version: str, prerelease: bool = False) -> bool:
    """Commit version bump and create tag."""
    try:
        # Add changed files
        subprocess.run(
            ["git", "-C", str(GOKUU_ROOT), "add", "VERSION", "README.md"],
            check=True, capture_output=True
        )
        
        # Commit
        commit_msg = f"chore: bump version to {new_version}"
        if prerelease:
            commit_msg += " [PRERELEASE]"
        
        subprocess.run(
            ["git", "-C", str(GOKUU_ROOT), "commit", "-m", commit_msg],
            check=True, capture_output=True
        )
        
        # Tag
        tag = f"v{new_version}"
        if prerelease:
            tag += "-alpha"
        
        tag_msg = f"Release {new_version}"
        if prerelease:
            tag_msg += " (Alpha — unstable)"
        
        create_git_tag(tag, tag_msg)
        return True
    except Exception as e:
        logger.error(f"Commit/tag failed: {e}")
        return False


def _push_to_remote() -> bool:
    """Push branch and tags to origin."""
    try:
        subprocess.run(["git", "-C", str(GOKUU_ROOT), "push", "origin", "main"], check=True)
        subprocess.run(["git", "-C", str(GOKUU_ROOT), "push", "origin", "--tags"], check=True)
        return True
    except Exception as e:
        logger.error(f"Push failed: {e}")
        return False


def update(
    bump: str = "patch",
    prerelease: bool = False,
    push: bool = True,
) -> dict:
    """
    Run atomic self-update.
    
    Args:
        bump: "major", "minor", or "patch"
        prerelease: If True, adds "-alpha" suffix and marks as pre-release
        push: If True, pushes changes to origin
    
    Returns:
        Status dict with success, version, and metadata
    """
    current = get_current_version()
    new_version = bump_version(current, bump)
    
    status = {
        "success": False,
        "current_version": current,
        "new_version": new_version,
        "bump": bump,
        "prerelease": prerelease,
        "errors": [],
        "git_head_before": get_git_head(),
        "git_head_after": None,
    }
    
    try:
        # Guardrails check
        from .self_health import pre_modify_check
        if not pre_modify_check():
            status["errors"].append("Pre-modify check failed")
            return status
        
        # Update version files
        update_version_file(new_version)
        update_readme_version(new_version)
        
        # Commit and tag
        if not _commit_and_tag(new_version, prerelease):
            status["errors"].append("Commit/tag failed")
            return status
        
        # Push if requested
        if push:
            if not _push_to_remote():
                logger.warning("Push failed — local changes saved, please push manually.")
        
        # Finalize
        status["success"] = True
        status["git_head_after"] = get_git_head()
        
        return status
        
    except Exception as e:
        status["errors"].append(str(e))
        return status


def rollback() -> dict:
    """
    Rollback to the last stable (non-prerelease) release.
    
    Returns:
        Status dict with rollback result
    """
    # Get list of all tags
    try:
        result = subprocess.run(
            ["git", "-C", str(GOKUU_ROOT), "tag", "-l"],
            capture_output=True, text=True, check=True
        )
        tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
    except Exception as e:
        return {"success": False, "error": f"Failed to list tags: {e}"}
    
    # Find latest non-prerelease tag
    stable_tags = [t for t in tags if not t.endswith("-alpha")]
    if not stable_tags:
        return {"success": False, "error": "No stable tags found to rollback to."}
    
    latest_stable = stable_tags[-1]
    
    # Rollback
    result = rollback_to_tag(latest_stable)
    
    if result["success"]:
        # Update VERSION file to match
        version = latest_stable.lstrip("v")
        (GOKUU_ROOT / "VERSION").write_text(version + "\n")
        return {
            "success": True,
            "rolled_back_to": latest_stable,
            "new_version": version,
        }
    else:
        return {"success": False, "error": result.get("error", "Unknown error")}


def status() -> dict:
    """Return current update status (version, dirty state, etc.)."""
    return {
        "current_version": get_current_version(),
        "dirty_files": check_self_integrity()["dirty_files"],
        "git_dirty": check_self_integrity()["git_status"] == "dirty",
        "last_rollback_tag": check_self_integrity()["last_rollback_tag"],
    }


# === CLI Wrapper ===
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m server.atomic_updater [update|rollback|status]")
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "update":
        bump = sys.argv[2] if len(sys.argv) > 2 else "patch"
        prerelease = "--prerelease" in sys.argv
        result = update(bump=bump, prerelease=prerelease, push=True)
        print(json.dumps(result, indent=2))
        
    elif cmd == "rollback":
        result = rollback()
        print(json.dumps(result, indent=2))
        
    elif cmd == "status":
        result = status()
        print(json.dumps(result, indent=2))
        
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
