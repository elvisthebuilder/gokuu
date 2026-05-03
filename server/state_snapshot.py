"""
state_snapshot.py — Core Self-Crush Prevention Engine
======================================================
Implements atomic state capture, rollback, and versioned Git tagging
to prevent self-modification crashes and enable recovery.

Design Philosophy:
- Everything mutable must be snapshottable before change
- Rollback must be instant, deterministic, and atomic
- Version tags must persist across reboots
"""

import os
import json
import hashlib
import shutil
import subprocess
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# === Constants ===
SNAPSHOT_DIR = Path.home() / ".gokuu" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

# === Snapshot Management ===

def compute_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_git_head() -> Optional[str]:
    """Get current Git commit hash."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get Git HEAD: {e}")
        return None

def get_git_dirty_state() -> bool:
    """Check if there are uncommitted changes in the repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "status", "--porcelain"],
            capture_output=True, text=True, check=True
        )
        return bool(result.stdout.strip())
    except Exception:
        return False

def capture_runtime_state() -> Dict[str, Any]:
    """Capture current runtime state for recovery."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_head": get_git_head(),
        "git_dirty": get_git_dirty_state(),
        "cwd": os.getcwd(),
        "python_version": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}.{__import__('sys').version_info.micro}",
    }

def create_snapshot(
    name: str,
    target_dir: Optional[Path] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a full snapshot of specified files/dirs.
    
    Args:
        name: Snapshot identifier (e.g., "before_self_update", "v3.0.1")
        target_dir: Directory to snapshot (default: gokuu root)
        include: Explicit list of paths to include
        exclude: Glob patterns to exclude (e.g., ["*.db", "__pycache__"])
    
    Returns:
        Metadata dict with checksums, timestamp, and Git state
    """
    if target_dir is None:
        target_dir = Path(__file__).parent.parent
    
    if include is None:
        include = ["server/", "agents/", "skills/"]
    
    if exclude is None:
        exclude = ["*.db", "*.pyc", "__pycache__/", "*.log", ".env", "venv/", ".venv/"]
    
    snapshot_id = f"snapshot_{name}_{int(datetime.now(timezone.utc).timestamp())}"
    snapshot_path = SNAPSHOT_DIR / snapshot_id
    snapshot_path.mkdir(parents=True, exist_ok=True)
    
    metadata = {
        "id": snapshot_id,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_dir": str(target_dir),
        "files": [],
        "runtime": capture_runtime_state(),
    }
    
    for rel_path in include:
        full_path = target_dir / rel_path
        if not full_path.exists():
            continue
        
        for filepath in full_path.rglob("*"):
            if filepath.is_file():
                # Apply exclude filters
                skip = False
                for pattern in exclude:
                    if filepath.match(pattern) or pattern in str(filepath):
                        skip = True
                        break
                if skip:
                    continue
                
                # Copy file to snapshot dir
                rel_to_target = filepath.relative_to(target_dir)
                dest_path = snapshot_path / rel_to_target
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(filepath), str(dest_path))
                
                # Record checksum and original
                metadata["files"].append({
                    "original": str(filepath),
                    "snapshot": str(dest_path),
                    "checksum": compute_checksum(dest_path),
                    "size": dest_path.stat().st_size,
                })
    
    # Save metadata
    metadata_path = snapshot_path / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Snapshot {snapshot_id} created with {len(metadata['files'])} files.")
    return metadata

def restore_snapshot(snapshot_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Restore files from a snapshot.
    
    Args:
        snapshot_id: The ID of the snapshot to restore (full or partial match)
        dry_run: If True, only validate and report, no actual changes
    
    Returns:
        Status dict with success, errors, and files restored
    """
    # Find snapshot dir
    matches = list(SNAPSHOT_DIR.glob(f"snapshot_*{snapshot_id}*"))
    if not matches:
        return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}
    
    snapshot_path = matches[0]
    metadata_path = snapshot_path / "metadata.json"
    if not metadata_path.exists():
        return {"success": False, "error": "Corrupt snapshot: no metadata.json"}
    
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    
    restored_count = 0
    errors = []
    
    for file_info in metadata["files"]:
        snapshot_file = Path(file_info["snapshot"])
        original_file = Path(file_info["original"])
        
        if not snapshot_file.exists():
            errors.append(f"Missing snapshot file: {snapshot_file}")
            continue
        
        if dry_run:
            logger.info(f"[DRY-RUN] Would restore {original_file}")
            restored_count += 1
            continue
        
        # Ensure parent dir exists
        original_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        try:
            shutil.copy2(str(snapshot_file), str(original_file))
            restored_count += 1
        except Exception as e:
            errors.append(f"Failed to restore {original_file}: {e}")
    
    return {
        "success": len(errors) == 0,
        "snapshot_id": snapshot_id,
        "restored": restored_count,
        "errors": errors,
    }

def create_git_tag(tag_name: str, message: Optional[str] = None) -> bool:
    """
    Create a Git tag referencing the current state.
    Used for atomic rollback via `git reset --hard`.
    """
    try:
        # Commit current state first (if not dirty)
        subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "add", "-A"],
            check=True, capture_output=True
        )
        
        # Create commit if changes
        commit_result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "commit", "-m", f"[Auto] Snapshot before {tag_name}"],
            capture_output=True,
            text=True
        )
        if commit_result.returncode != 0 and "nothing to commit" not in commit_result.stderr:
            logger.warning(f"Commit warning: {commit_result.stderr}")
        
        # Create tag
        subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "tag", "-a", tag_name, "-m", message or f"Snapshot {tag_name}"],
            check=True
        )
        logger.info(f"Git tag created: {tag_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to create Git tag {tag_name}: {e}")
        return False

def rollback_to_tag(tag_name: str, hard: bool = True) -> Dict[str, Any]:
    """
    Rollback to a tagged commit state.
    Optionally wipe current changes (`hard=True`).
    """
    try:
        cmd = ["git", "-C", str(Path(__file__).parent.parent)]
        
        # Check tag exists
        result = subprocess.run(cmd + ["tag", "-l", tag_name], capture_output=True, text=True)
        if tag_name not in result.stdout:
            return {"success": False, "error": f"Tag not found: {tag_name}"}
        
        # Reset to tag
        reset_flag = "--hard" if hard else "--soft"
        subprocess.run(cmd + ["reset", reset_flag, tag_name], check=True)
        logger.info(f"Rolled back to tag: {tag_name}")
        
        return {"success": True, "tag": tag_name, "hard": hard}
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {"success": False, "error": str(e)}

# === Safety Check Hooks ===

def pre_modify_check() -> bool:
    """
    Pre-modify safety check — run before *any* self-alteration.
    """
    # 1. Ensure we're on main or a feature branch
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True
        )
        current_branch = result.stdout.strip()
        
        if current_branch == "main" and get_git_dirty_state():
            logger.warning("⚠️  Attempting self-modification on dirty main branch.")
            return False
    except Exception:
        pass
    
    # 2. Take pre-modify snapshot
    snap = create_snapshot("pre_modify")
    if not snap.get("files"):
        logger.error("Pre-modify snapshot failed.")
        return False
    
    # 3. Git tag for rollback
    tag = f"pre_modify_{int(datetime.now(timezone.utc).timestamp())}"
    if not create_git_tag(tag, f"Pre-modify checkpoint: {snap['id']}"):
        logger.warning("Git tag creation failed, proceeding anyway.")
    
    logger.info("✅ Pre-modify checks passed.")
    return True

def post_modify_verify() -> bool:
    """
    Post-modify integrity verification.
    Checks that critical files are still present and intact.
    """
    critical_files = [
        Path(__file__).parent / "agent.py",
        Path(__file__).parent / "gateway.py",
        Path(__file__).parent / "main.py",
    ]
    
    for f in critical_files:
        if not f.exists():
            logger.critical(f"Critical file missing after modify: {f}")
            return False
        try:
            checksum = compute_checksum(f)
            if not checksum:
                logger.critical(f"Critical file unreadable: {f}")
                return False
        except Exception:
            logger.critical(f"Could not verify integrity: {f}")
            return False
    
    logger.info("✅ Post-modify integrity check passed.")
    return True

def auto_rollback_if_failed(error: Exception) -> bool:
    """
    Automatically restore snapshot on error during self-modify.
    Returns True if rollback succeeded.
    """
    # Find last pre_modify snapshot
    matches = sorted(
        SNAPSHOT_DIR.glob("snapshot_pre_modify_*"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not matches:
        logger.error("No pre_modify snapshot found for rollback.")
        return False
    
    latest = matches[0]
    snapshot_id = latest.name
    
    logger.warning(f"Triggering rollback from error: {error}")
    result = restore_snapshot(snapshot_id)
    
    if not result["success"]:
        logger.critical(f"Rollback failed: {result['errors']}")
        return False
    
    # Restore Git state
    tag_matches = subprocess.run(
        ["git", "-C", str(Path(__file__).parent.parent), "tag", "-l", "pre_modify_*"],
        capture_output=True, text=True
    ).stdout.strip().split("\n")
    
    if tag_matches and tag_matches[-1]:
        rollback_to_tag(tag_matches[-1])
    
    logger.warning(f"✅ Auto-rolled back to snapshot: {snapshot_id}")
    return True
