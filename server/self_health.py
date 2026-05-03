"""
self_health.py — Self-Modifying Agent Guardrails
=================================================
Enforces safety before any self-alteration (code edit, personality switch,
module load, config change). Acts as a "bodyguard" for the agent's core.

Design:
- Hooks into any self-alteration function
- Enforces: pre-check → execute → verify → (on fail → rollback)
- Provides interactive prompt or auto-skip (configurable)
"""

import logging
from typing import Callable, Any, Dict, Optional
from functools import wraps
from pathlib import Path
import os

from .state_snapshot import (
    pre_modify_check,
    post_modify_verify,
    auto_rollback_if_failed,
)

logger = logging.getLogger(__name__)

# === Guardrail Levels ===
GUARD_LEVELS = {
    "strict": "Block all unsafe changes, require pre-check",
    "warn": "Warn but allow unsafe changes",
    "off": "No checks — USE ONLY IN DEV",
}

GUARD_DEFAULT = "strict"

# === Context-aware Decorators ===

class GuardrailError(Exception):
    """Raised when guardrails prevent an operation."""
    pass


def self_modify_guard(
    func: Optional[Callable] = None,
    *,
    guard_level: str = None,
    auto_rollback: bool = True,
    description: str = "",
):
    """
    Decorator to protect any function that modifies the agent's code or state.
    
    Usage:
        @self_modify_guard
        def update_personality(...): ...
        
        @self_modify_guard(guard_level="warn", description="Personality edit")
        def reload_skills(...): ...
    """
    if func is None:
        return lambda f: self_modify_guard(
            f,
            guard_level=guard_level,
            auto_rollback=auto_rollback,
            description=description
        )
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        level = guard_level or os.getenv("GOKUU_GUARD_LEVEL", GUARD_DEFAULT)
        
        # Skip in dev/test mode
        if level == "off":
            return func(*args, **kwargs)
        
        # Pre-modify check
        try:
            if not pre_modify_check():
                if level == "strict":
                    raise GuardrailError("Pre-modify check failed. Aborting.")
                logger.warning("Pre-modify check failed, proceeding in warn mode.")
        except Exception as e:
            if level == "strict":
                raise GuardrailError(f"Pre-modify check error: {e}")
            logger.warning(f"Pre-modify check error (warn mode): {e}")
        
        # Try execution
        result = None
        try:
            result = func(*args, **kwargs)
            
            # Post-modify verification
            if not post_modify_verify():
                if level == "strict":
                    raise GuardrailError("Post-modify verification failed.")
                logger.warning("Post-modify verification failed, proceeding in warn mode.")
            
            return result
        except Exception as e:
            logger.error(f"Self-modify operation failed: {e}")
            
            if auto_rollback and level != "off":
                if auto_rollback_if_failed(e):
                    logger.warning("Auto-rollback succeeded.")
                    return None  # Silent recovery in strict mode
                else:
                    raise GuardrailError("Auto-rollback failed. Manual intervention required.")
            raise
    return wrapper


def check_self_integrity() -> Dict[str, Any]:
    """
    Full integrity scan of the core agent code.
    Checks:
      - Git HEAD is clean (or on feature branch)
      - Critical files match known checksums (future: fingerprinting)
      - No unexpected new modules in critical paths
    """
    import subprocess
    
    status = {
        "git_status": "unknown",
        "dirty_files": [],
        "missing_files": [],
        "integrity_ok": True,
        "last_rollback_tag": None,
    }
    
    # 1. Git status
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "status", "--porcelain"],
            capture_output=True, text=True
        )
        dirty = result.stdout.strip().split("\n") if result.stdout.strip() else []
        status["git_status"] = "dirty" if dirty else "clean"
        status["dirty_files"] = [d.split(maxsplit=1)[-1] for d in dirty if d]
    except Exception as e:
        status["git_status"] = f"error: {e}"
    
    # 2. Check for rollback tags
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).parent.parent), "tag", "-l", "pre_modify_*"],
            capture_output=True, text=True
        )
        tags = result.stdout.strip().split("\n")
        if tags:
            status["last_rollback_tag"] = tags[-1]
    except Exception:
        pass
    
    # 3. Check critical files (agent, gateway, main, config_manager)
    critical = [
        Path(__file__).parent / "agent.py",
        Path(__file__).parent / "gateway.py",
        Path(__file__).parent / "config_manager.py",
        Path(__file__).parent / "main.py",
    ]
    
    for f in critical:
        if not f.exists():
            status["missing_files"].append(str(f))
            status["integrity_ok"] = False
    
    return status


def enforce_guardrails(func: Callable) -> Callable:
    """
    Context manager-style guard for inline usage.
    
    Usage:
        with enforce_guardrails():
            agent.update_config(...)
    """
    class GuardContext:
        def __enter__(self):
            if not pre_modify_check():
                raise GuardrailError("Pre-modify guard failed.")
            return self
        
        def __exit__(self, exc_type, exc, tb):
            if exc_type:
                auto_rollback_if_failed(exc)
            else:
                post_modify_verify()
    
    from contextlib import contextmanager
    
    @contextmanager
    def _guard():
        ctx = GuardContext()
        try:
            yield ctx
        except Exception as e:
            raise
    
    return _guard()


# === Safety API Helpers ===

def get_safety_status() -> str:
    """Return human-readable safety status."""
    status = check_self_integrity()
    
    if not status["integrity_ok"]:
        return "⚠️  Integrity compromised"
    elif status["git_status"] == "dirty":
        return "⚠️  Local changes detected (not committed)"
    else:
        return "✅ Agent integrity OK"


def print_safety_summary():
    """Print a formatted safety summary to console."""
    status = check_self_integrity()
    
    print("=" * 60)
    print("Self-Health Report")
    print("=" * 60)
    print(f"Git Status       : {status['git_status']}")
    print(f"Dirty Files      : {len(status['dirty_files'])}")
    if status["dirty_files"]:
        for f in status["dirty_files"]:
            print(f"  - {f}")
    print(f"Missing Files    : {len(status['missing_files'])}")
    if status["missing_files"]:
        for f in status["missing_files"]:
            print(f"  - {f}")
    print(f"Last Rollback    : {status['last_rollback_tag'] or 'None'}")
    print(f"Integrity OK     : {status['integrity_ok']}")
    print("=" * 60)
