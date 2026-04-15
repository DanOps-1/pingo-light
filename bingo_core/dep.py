"""
bingo_core.dep — Dependency patching engine.

Maintains patches on top of npm/pip packages. Same mental model as git fork
patching: upstream is the published package, your patches sit on top.

Storage layout:
    .bingo-deps/
        config.json         # { "packages": { "some-lib": { "version": "2.1.0", "manager": "npm" } } }
        patches/
            some-lib/
                fix-auth.patch
                add-logging.patch
            another-lib/
                typo-fix.patch

Python 3.8+ stdlib only. No pip dependencies.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ─── Constants ───────────────────────────────────────────────────────────────

DEP_DIR = ".bingo-deps"
DEP_CONFIG = "config.json"
PATCHES_DIR = "patches"


# ─── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class DepPatch:
    """A single patch on a dependency."""
    package: str
    name: str          # patch file name (e.g. "fix-auth.patch")
    path: str          # full path to .patch file
    description: str = ""


@dataclass
class DepPackage:
    """A patched dependency."""
    name: str
    version: str       # version the patches were generated against
    manager: str       # "npm" | "pip"
    patches: List[DepPatch] = field(default_factory=list)


@dataclass
class DepConflict:
    """Conflict when applying a patch after upstream update."""
    package: str
    patch_name: str
    old_version: str
    new_version: str
    error: str
    hint: str = ""


# ─── Backend Interface ───────────────────────────────────────────────────────


class DepBackend:
    """Abstract backend for a package manager (npm, pip, etc.)."""

    name: str = "unknown"

    def detect(self, cwd: str) -> bool:
        """Return True if this backend applies to the project at cwd."""
        raise NotImplementedError

    def get_installed_version(self, package: str, cwd: str) -> Optional[str]:
        """Get the currently installed version of a package."""
        raise NotImplementedError

    def get_install_path(self, package: str, cwd: str) -> Optional[str]:
        """Get the filesystem path where the package is installed."""
        raise NotImplementedError

    def fetch_original(self, package: str, version: str, dest: str) -> bool:
        """Download the original (unpatched) package source to dest dir."""
        raise NotImplementedError

    def list_files(self, package: str, cwd: str) -> List[str]:
        """List all files in the installed package (relative paths)."""
        raise NotImplementedError

    def install_hook_command(self) -> str:
        """Return the postinstall command string for auto-applying patches."""
        return "bingo-light dep apply"


# ─── Core Engine ─────────────────────────────────────────────────────────────


class DepManager:
    """Core dependency patching engine."""

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
        self.dep_dir = os.path.join(self.cwd, DEP_DIR)
        self.config_path = os.path.join(self.dep_dir, DEP_CONFIG)
        self.patches_dir = os.path.join(self.dep_dir, PATCHES_DIR)
        self._backends: List[DepBackend] = []
        self._config: Optional[Dict] = None

        # Register backends (import lazily to avoid circular deps)
        from bingo_core.dep_npm import NpmBackend
        from bingo_core.dep_pip import PipBackend
        self._backends = [NpmBackend(), PipBackend()]

    # ─── Config ──────────────────────────────────────────────────────────

    def _load_config(self) -> Dict:
        if self._config is not None:
            return self._config
        if os.path.isfile(self.config_path):
            with open(self.config_path) as f:
                self._config = json.load(f)
        else:
            self._config = {"packages": {}}
        return self._config

    def _save_config(self) -> None:
        os.makedirs(self.dep_dir, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config or {}, f, indent=2)
            f.write("\n")

    # ─── Backend Detection ───────────────────────────────────────────────

    def _detect_backend(self, package: str) -> Optional[DepBackend]:
        """Auto-detect which backend manages a package."""
        for b in self._backends:
            if b.detect(self.cwd) and b.get_installed_version(package, self.cwd):
                return b
        return None

    def _get_backend(self, manager: str) -> Optional[DepBackend]:
        """Get backend by name."""
        for b in self._backends:
            if b.name == manager:
                return b
        return None

    # ─── Postinstall Hook ─────────────────────────────────────────────────

    def _ensure_postinstall_hook(self, backend: DepBackend) -> Optional[str]:
        """Add 'bingo-light dep apply' to package.json postinstall if npm project.

        Returns a message if hook was added, None otherwise.
        """
        if backend.name != "npm":
            return None

        pkg_json_path = os.path.join(self.cwd, "package.json")
        if not os.path.isfile(pkg_json_path):
            return None

        try:
            with open(pkg_json_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        scripts = data.setdefault("scripts", {})
        # Find bingo-light binary — use absolute path for reliability
        bl_bin = shutil.which("bingo-light")
        if bl_bin:
            hook_cmd = f"{bl_bin} dep apply"
        else:
            # Fallback: npx always works if npm is available
            hook_cmd = "npx --yes bingo-light dep apply"

        existing = scripts.get("postinstall", "")
        if hook_cmd in existing:
            return None  # already present

        if existing:
            scripts["postinstall"] = f"{existing} && {hook_cmd}"
        else:
            scripts["postinstall"] = hook_cmd

        try:
            with open(pkg_json_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        except OSError:
            return None

        return "postinstall hook added to package.json"

    # ─── Patch Generation ────────────────────────────────────────────────

    def patch(self, package: str, patch_name: str = "",
              description: str = "") -> Dict[str, Any]:
        """Generate a patch for a modified dependency.

        1. Detect the package manager
        2. Find the installed (modified) version
        3. Download the original version
        4. Generate a unified diff
        5. Save as .patch file
        """
        backend = self._detect_backend(package)
        if not backend:
            return {"ok": False, "error": f"Package '{package}' not found in any package manager"}

        version = backend.get_installed_version(package, self.cwd)
        if not version:
            return {"ok": False, "error": f"Cannot determine version for '{package}'"}

        install_path = backend.get_install_path(package, self.cwd)
        if not install_path or not os.path.isdir(install_path):
            return {"ok": False, "error": f"Install path not found for '{package}'"}

        # Download original
        tmpdir = tempfile.mkdtemp(prefix="bingo-dep-")
        try:
            original_dir = os.path.join(tmpdir, "original")
            os.makedirs(original_dir)
            if not backend.fetch_original(package, version, original_dir):
                return {"ok": False, "error": f"Failed to download original '{package}@{version}'"}

            # Generate unified diff
            diff_lines = _generate_diff(original_dir, install_path, package)
            if not diff_lines:
                return {"ok": False, "error": f"No modifications found in '{package}'"}

            # Determine patch name
            if not patch_name:
                config = self._load_config()
                pkg_conf = config.get("packages", {}).get(package, {})
                existing = pkg_conf.get("patches", [])
                idx = len(existing) + 1
                patch_name = f"patch-{idx:03d}"

            if not patch_name.endswith(".patch"):
                patch_name += ".patch"

            # Save patch
            pkg_patches_dir = os.path.join(self.patches_dir, package)
            os.makedirs(pkg_patches_dir, exist_ok=True)
            patch_path = os.path.join(pkg_patches_dir, patch_name)
            with open(patch_path, "w") as f:
                f.writelines(diff_lines)

            # Update config
            config = self._load_config()
            pkgs = config.setdefault("packages", {})
            pkg = pkgs.setdefault(package, {
                "version": version,
                "manager": backend.name,
                "patches": [],
            })
            pkg["version"] = version
            if patch_name not in pkg["patches"]:
                pkg["patches"].append(patch_name)
            if description:
                pkg.setdefault("descriptions", {})[patch_name] = description
            self._save_config()

            # Auto-add postinstall hook on first patch
            hook_msg = self._ensure_postinstall_hook(backend)

            file_count = sum(1 for line in diff_lines if line.startswith("--- "))
            result = {
                "ok": True,
                "package": package,
                "version": version,
                "patch": patch_name,
                "files_changed": file_count,
                "manager": backend.name,
            }
            if hook_msg:
                result["hook"] = hook_msg
            return result
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─── Patch Application ───────────────────────────────────────────────

    def apply(self, package: str = "") -> Dict[str, Any]:
        """Apply patches to installed dependencies.

        If package is empty, apply all patches for all tracked packages.
        """
        config = self._load_config()
        packages = config.get("packages", {})

        if package:
            if package not in packages:
                return {"ok": False, "error": f"No patches tracked for '{package}'"}
            targets = {package: packages[package]}
        else:
            targets = packages

        results = []
        for pkg_name, pkg_conf in targets.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            if not backend:
                results.append({"package": pkg_name, "ok": False, "error": "Unknown manager"})
                continue

            install_path = backend.get_install_path(pkg_name, self.cwd)
            if not install_path:
                results.append({"package": pkg_name, "ok": False, "error": "Not installed"})
                continue

            for patch_name in pkg_conf.get("patches", []):
                patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                if not os.path.isfile(patch_path):
                    results.append({
                        "package": pkg_name, "patch": patch_name,
                        "ok": False, "error": "Patch file missing",
                    })
                    continue

                success, error = _apply_patch(patch_path, install_path)
                results.append({
                    "package": pkg_name, "patch": patch_name,
                    "ok": success, "error": error,
                })

        applied = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]
        return {
            "ok": len(failed) == 0,
            "applied": len(applied),
            "failed": len(failed),
            "results": results,
        }

    # ─── Status ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Show status of all tracked dependency patches."""
        config = self._load_config()
        packages = config.get("packages", {})
        pkg_status = []

        for pkg_name, pkg_conf in packages.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            current_ver = None
            installed = False
            if backend:
                current_ver = backend.get_installed_version(pkg_name, self.cwd)
                installed = current_ver is not None

            patched_ver = pkg_conf.get("version", "?")
            version_match = (current_ver == patched_ver) if current_ver else None
            patch_count = len(pkg_conf.get("patches", []))

            status = "ok"
            if not installed:
                status = "not_installed"
            elif not version_match:
                status = "version_mismatch"

            pkg_status.append({
                "package": pkg_name,
                "manager": pkg_conf.get("manager", "?"),
                "patched_version": patched_ver,
                "installed_version": current_ver or "?",
                "patches": patch_count,
                "status": status,
            })

        return {
            "ok": True,
            "packages": pkg_status,
            "total_packages": len(pkg_status),
            "total_patches": sum(p["patches"] for p in pkg_status),
        }

    # ─── List ────────────────────────────────────────────────────────────

    def list_patches(self, package: str = "") -> Dict[str, Any]:
        """List all patches, optionally for a specific package."""
        config = self._load_config()
        packages = config.get("packages", {})
        all_patches = []

        targets = {package: packages[package]} if package and package in packages else packages
        for pkg_name, pkg_conf in targets.items():
            descs = pkg_conf.get("descriptions", {})
            for patch_name in pkg_conf.get("patches", []):
                patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                all_patches.append({
                    "package": pkg_name,
                    "patch": patch_name,
                    "description": descs.get(patch_name, ""),
                    "version": pkg_conf.get("version", "?"),
                    "exists": os.path.isfile(patch_path),
                })

        return {"ok": True, "patches": all_patches}

    # ─── Sync (after npm/pip update) ─────────────────────────────────────

    def sync(self) -> Dict[str, Any]:
        """After a package manager update, re-apply patches and detect conflicts."""
        config = self._load_config()
        packages = config.get("packages", {})
        results = []

        for pkg_name, pkg_conf in packages.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            if not backend:
                continue

            current_ver = backend.get_installed_version(pkg_name, self.cwd)
            patched_ver = pkg_conf.get("version", "")

            if not current_ver:
                results.append({
                    "package": pkg_name, "status": "not_installed",
                    "old_version": patched_ver, "new_version": None,
                })
                continue

            if current_ver == patched_ver:
                # Same version — just re-apply
                apply_result = self.apply(pkg_name)
                results.append({
                    "package": pkg_name, "status": "reapplied",
                    "old_version": patched_ver, "new_version": current_ver,
                    "apply": apply_result,
                })
            else:
                # Version changed — try to apply, may conflict
                install_path = backend.get_install_path(pkg_name, self.cwd)
                conflicts = []
                applied = []

                for patch_name in pkg_conf.get("patches", []):
                    patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                    if not os.path.isfile(patch_path):
                        conflicts.append({
                            "patch": patch_name,
                            "error": "Patch file missing",
                        })
                        continue

                    success, error = _apply_patch(patch_path, install_path)
                    if success:
                        applied.append(patch_name)
                    else:
                        conflicts.append({
                            "patch": patch_name,
                            "error": error,
                            "hint": f"Package updated {patched_ver} → {current_ver}. "
                                    f"Regenerate patch: bingo-light dep patch {pkg_name}",
                        })

                status = "synced" if not conflicts else "conflict"
                results.append({
                    "package": pkg_name,
                    "status": status,
                    "old_version": patched_ver,
                    "new_version": current_ver,
                    "applied": applied,
                    "conflicts": conflicts,
                })

                # Update tracked version if all patches applied
                if not conflicts:
                    pkg_conf["version"] = current_ver
                    self._save_config()

        total_conflicts = sum(
            len(r.get("conflicts", [])) for r in results
        )
        return {
            "ok": total_conflicts == 0,
            "results": results,
            "total_conflicts": total_conflicts,
            "recommended_action": "ok" if total_conflicts == 0 else "regenerate_patches",
        }

    # ─── Drop ────────────────────────────────────────────────────────────

    def drop(self, package: str, patch_name: str = "") -> Dict[str, Any]:
        """Remove a patch or all patches for a package."""
        config = self._load_config()
        packages = config.get("packages", {})

        if package not in packages:
            return {"ok": False, "error": f"No patches tracked for '{package}'"}

        if patch_name:
            # Remove specific patch
            if not patch_name.endswith(".patch"):
                patch_name += ".patch"
            patches = packages[package].get("patches", [])
            if patch_name not in patches:
                return {"ok": False, "error": f"Patch '{patch_name}' not found"}
            patches.remove(patch_name)
            patch_path = os.path.join(self.patches_dir, package, patch_name)
            if os.path.isfile(patch_path):
                os.remove(patch_path)
            if not patches:
                del packages[package]
                pkg_dir = os.path.join(self.patches_dir, package)
                if os.path.isdir(pkg_dir):
                    shutil.rmtree(pkg_dir)
        else:
            # Remove all patches for package
            del packages[package]
            pkg_dir = os.path.join(self.patches_dir, package)
            if os.path.isdir(pkg_dir):
                shutil.rmtree(pkg_dir)

        self._save_config()
        return {"ok": True, "package": package, "dropped": patch_name or "all"}

    # ── Override Management ─────────────────────────────────────────────────

    def _read_package_json(self) -> Optional[dict]:
        """Read package.json from cwd. Returns None if not found."""
        pj_path = os.path.join(self.cwd, "package.json")
        if not os.path.isfile(pj_path):
            return None
        try:
            with open(pj_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _write_package_json(self, data: dict) -> None:
        """Atomically write package.json preserving 2-space indent."""
        pj_path = os.path.join(self.cwd, "package.json")
        fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=self.cwd)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, pj_path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def _load_overrides_tracking(self) -> dict:
        """Load .bingo-deps/overrides.json tracking data."""
        path = os.path.join(self.cwd, DEP_DIR, "overrides.json")
        if not os.path.isfile(path):
            return {"overrides": {}}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"overrides": {}}

    def _save_overrides_tracking(self, data: dict) -> None:
        """Write .bingo-deps/overrides.json."""
        os.makedirs(os.path.join(self.cwd, DEP_DIR), exist_ok=True)
        path = os.path.join(self.cwd, DEP_DIR, "overrides.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def override_list(self) -> dict:
        """List npm/yarn overrides with tracked reasons.

        Returns {"ok": True, "overrides": [...], "count": N}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": True, "overrides": [], "count": 0, "note": "No package.json"}

        # npm uses "overrides", yarn uses "resolutions"
        overrides = pj.get("overrides", {})
        resolutions = pj.get("resolutions", {})
        all_ovs = {}
        for pkg, ver in overrides.items():
            all_ovs[pkg] = {"version": ver if isinstance(ver, str) else json.dumps(ver), "source": "overrides"}
        for pkg, ver in resolutions.items():
            if pkg not in all_ovs:
                all_ovs[pkg] = {"version": ver, "source": "resolutions"}

        # Merge with tracking data
        tracking = self._load_overrides_tracking()
        result = []
        for pkg, info in all_ovs.items():
            tracked = tracking.get("overrides", {}).get(pkg, {})
            result.append({
                "package": pkg,
                "version": info["version"],
                "source": info["source"],
                "reason": tracked.get("reason", ""),
                "created": tracked.get("created", ""),
                "tracked": bool(tracked),
            })

        return {"ok": True, "overrides": result, "count": len(result)}

    def override_check(self) -> dict:
        """Check if npm overrides are still needed.

        Reads package-lock.json to determine what version the tree resolves to.
        Returns {"ok": True, "overrides": [{"package", "status", "reason"}]}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": True, "overrides": [], "count": 0}

        overrides = pj.get("overrides", {})
        resolutions = pj.get("resolutions", {})
        all_ovs = dict(overrides)
        all_ovs.update(resolutions)

        if not all_ovs:
            return {"ok": True, "overrides": [], "count": 0}

        # Try reading package-lock.json for resolved versions
        lock_path = os.path.join(self.cwd, "package-lock.json")
        lock_data: Optional[dict] = None
        if os.path.isfile(lock_path):
            try:
                with open(lock_path) as f:
                    lock_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        results = []
        for pkg, override_ver in all_ovs.items():
            if not isinstance(override_ver, str):
                results.append({
                    "package": pkg,
                    "override_version": json.dumps(override_ver),
                    "status": "complex",
                    "reason": "Nested override — manual check required",
                })
                continue

            # Look up in lock file
            resolved_ver = None
            if lock_data:
                # npm v2/v3 lock format: packages["node_modules/<pkg>"].version
                packages = lock_data.get("packages", {})
                lock_key = f"node_modules/{pkg}"
                if lock_key in packages:
                    resolved_ver = packages[lock_key].get("version", "")

            if resolved_ver is None:
                results.append({
                    "package": pkg,
                    "override_version": override_ver,
                    "status": "unknown",
                    "reason": "Cannot determine resolved version",
                })
            elif resolved_ver == override_ver:
                # Lock resolved to override version — could be redundant
                # Check if the package's parent requires a different version
                # by looking at the dependency entry in lock file
                pkg_entry = packages.get(lock_key, {})
                # If the package has no "overridden" marker and its version
                # matches, the tree might naturally resolve to it
                results.append({
                    "package": pkg,
                    "override_version": override_ver,
                    "resolved_version": resolved_ver,
                    "status": "redundant",
                    "reason": "Lock resolves to override version — may no longer be needed",
                })
            else:
                results.append({
                    "package": pkg,
                    "override_version": override_ver,
                    "resolved_version": resolved_ver,
                    "status": "active",
                    "reason": f"Override forcing {override_ver} (tree wants {resolved_ver})",
                })

        redundant = sum(1 for r in results if r["status"] == "redundant")
        return {"ok": True, "overrides": results, "count": len(results), "redundant": redundant}

    def override_add(self, package: str, version: str, reason: str = "") -> dict:
        """Add an npm override with reason tracking.

        Returns {"ok": True, "package": ..., "version": ...}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": False, "error": "No package.json found"}

        # Detect yarn vs npm
        yarn_lock = os.path.isfile(os.path.join(self.cwd, "yarn.lock"))
        field = "resolutions" if yarn_lock else "overrides"

        if field not in pj:
            pj[field] = {}
        pj[field][package] = version
        self._write_package_json(pj)

        # Track reason
        tracking = self._load_overrides_tracking()
        tracking.setdefault("overrides", {})[package] = {
            "version": version,
            "reason": reason,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "manager_field": field,
        }
        self._save_overrides_tracking(tracking)

        return {"ok": True, "package": package, "version": version, "field": field}

    def override_drop(self, package: str) -> dict:
        """Remove an npm override.

        Returns {"ok": True, "package": ..., "dropped": True}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": False, "error": "No package.json found"}

        dropped = False
        for field in ("overrides", "resolutions"):
            if field in pj and package in pj[field]:
                del pj[field][package]
                if not pj[field]:
                    del pj[field]
                dropped = True
        if dropped:
            self._write_package_json(pj)

        # Remove tracking
        tracking = self._load_overrides_tracking()
        if package in tracking.get("overrides", {}):
            del tracking["overrides"][package]
            self._save_overrides_tracking(tracking)

        return {"ok": True, "package": package, "dropped": dropped}


# ─── Diff Utilities ──────────────────────────────────────────────────────────


def _generate_diff(original_dir: str, modified_dir: str,
                   label: str) -> List[str]:
    """Generate unified diff between two directory trees."""
    diff_lines: List[str] = []

    for root, _dirs, files in os.walk(original_dir):
        for fname in sorted(files):
            orig_path = os.path.join(root, fname)
            rel = os.path.relpath(orig_path, original_dir)
            mod_path = os.path.join(modified_dir, rel)

            # Skip non-text files
            if _is_binary(orig_path):
                continue

            try:
                with open(orig_path) as f:
                    orig_lines = f.readlines()
            except (UnicodeDecodeError, OSError):
                continue

            if os.path.isfile(mod_path):
                try:
                    with open(mod_path) as f:
                        mod_lines = f.readlines()
                except (UnicodeDecodeError, OSError):
                    continue

                if orig_lines != mod_lines:
                    diff = difflib.unified_diff(
                        orig_lines, mod_lines,
                        fromfile=f"a/{label}/{rel}",
                        tofile=f"b/{label}/{rel}",
                    )
                    diff_lines.extend(diff)

    # Check for new files in modified that don't exist in original
    for root, _dirs, files in os.walk(modified_dir):
        for fname in sorted(files):
            mod_path = os.path.join(root, fname)
            rel = os.path.relpath(mod_path, modified_dir)
            orig_path = os.path.join(original_dir, rel)

            if not os.path.isfile(orig_path) and not _is_binary(mod_path):
                try:
                    with open(mod_path) as f:
                        mod_lines = f.readlines()
                    diff = difflib.unified_diff(
                        [], mod_lines,
                        fromfile=f"a/{label}/{rel}",
                        tofile=f"b/{label}/{rel}",
                    )
                    diff_lines.extend(diff)
                except (UnicodeDecodeError, OSError):
                    continue

    return diff_lines


def _apply_patch(patch_path: str, target_dir: str) -> Tuple[bool, str]:
    """Apply a unified diff patch to a directory. Returns (success, error)."""
    # Try system `patch` command first (most reliable)
    # Patches use a/<pkg>/<file> format, so -p2 strips the a/<pkg>/ prefix
    if shutil.which("patch"):
        with open(patch_path) as pf:
            result = subprocess.run(
                ["patch", "-p2", "-d", target_dir, "--forward", "--batch"],
                stdin=pf,
                capture_output=True, text=True,
            )
        if result.returncode == 0:
            return (True, "")
        # patch may partially apply; check if "FAILED" in output
        if "FAILED" in result.stdout or result.returncode != 0:
            return (False, result.stdout.strip() or result.stderr.strip())

    # Fallback: Python-based patch application
    return _apply_patch_python(patch_path, target_dir)


def _apply_patch_python(patch_path: str, target_dir: str) -> Tuple[bool, str]:
    """Pure-Python unified diff patch application.

    Parses unified diff format and applies hunks to target files.
    Supports: context matching, fuzzy offset (±3 lines), new/deleted files.
    Processes hunks in reverse order to avoid line number cascading.
    """
    import re

    try:
        with open(patch_path) as f:
            patch_lines = f.readlines()
    except OSError as e:
        return (False, str(e))

    # Parse into file-level diffs
    file_diffs: List[dict] = []
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]

        # Find --- a/... and +++ b/... pair
        if line.startswith("--- "):
            if i + 1 < len(patch_lines) and patch_lines[i + 1].startswith("+++ "):
                old_path = line[4:].strip()
                new_line = patch_lines[i + 1]
                # Strip p2: +++ b/<pkg>/<file> -> <file>
                new_path_raw = new_line[6:].strip()
                parts = new_path_raw.split("/", 1)
                rel_path = parts[1] if len(parts) > 1 else parts[0]

                is_new = old_path == "/dev/null" or old_path.endswith("/dev/null")
                is_delete = new_line.strip().endswith("/dev/null")

                # Collect hunks for this file
                hunks: List[dict] = []
                i += 2
                while i < len(patch_lines):
                    hunk_line = patch_lines[i]
                    m = re.match(
                        r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',
                        hunk_line,
                    )
                    if m:
                        old_start = int(m.group(1))
                        old_count = int(m.group(2)) if m.group(2) is not None else 1
                        new_start = int(m.group(3))
                        new_count = int(m.group(4)) if m.group(4) is not None else 1
                        hunk_body: List[str] = []
                        i += 1
                        while i < len(patch_lines):
                            hl = patch_lines[i]
                            if hl.startswith((" ", "+", "-")):
                                hunk_body.append(hl)
                                i += 1
                            elif hl.startswith("\\ No newline"):
                                i += 1  # skip no-newline marker
                            else:
                                break
                        hunks.append({
                            "old_start": old_start,
                            "old_count": old_count,
                            "new_start": new_start,
                            "new_count": new_count,
                            "lines": hunk_body,
                        })
                    elif hunk_line.startswith("--- ") or hunk_line.startswith("diff "):
                        break  # next file diff
                    else:
                        i += 1

                file_diffs.append({
                    "path": rel_path,
                    "is_new": is_new,
                    "is_delete": is_delete,
                    "hunks": hunks,
                })
                continue
        i += 1

    if not file_diffs:
        return (False, "No file diffs found in patch")

    # Apply each file diff
    for fd in file_diffs:
        target_file = os.path.join(target_dir, fd["path"])

        if fd["is_delete"]:
            try:
                os.remove(target_file)
            except FileNotFoundError:
                pass
            continue

        if fd["is_new"]:
            os.makedirs(os.path.dirname(target_file) or ".", exist_ok=True)
            new_lines: List[str] = []
            for hunk in fd["hunks"]:
                for hl in hunk["lines"]:
                    if hl.startswith("+"):
                        new_lines.append(hl[1:])
                    elif hl.startswith(" "):
                        new_lines.append(hl[1:])
            with open(target_file, "w") as f:
                f.writelines(new_lines)
            continue

        # Existing file — read, apply hunks in reverse, write
        if not os.path.isfile(target_file):
            return (False, f"File not found: {fd['path']}")

        with open(target_file) as f:
            file_lines = f.readlines()

        # Process hunks in reverse order to preserve line numbers
        for hunk in reversed(fd["hunks"]):
            old_start = hunk["old_start"] - 1  # 0-indexed
            hunk_lines = hunk["lines"]

            # Build expected old lines and new lines
            old_expected: List[str] = []
            new_replacement: List[str] = []
            for hl in hunk_lines:
                if hl.startswith(" "):
                    old_expected.append(hl[1:])
                    new_replacement.append(hl[1:])
                elif hl.startswith("-"):
                    old_expected.append(hl[1:])
                elif hl.startswith("+"):
                    new_replacement.append(hl[1:])

            # Try exact match first, then fuzzy offset ±3
            match_pos = -1
            for offset in range(0, 4):
                for sign in (0, -1, 1) if offset == 0 else (-1, 1):
                    pos = old_start + offset * sign
                    if pos < 0 or pos + len(old_expected) > len(file_lines):
                        continue
                    chunk = file_lines[pos:pos + len(old_expected)]
                    if _lines_match(chunk, old_expected):
                        match_pos = pos
                        break
                if match_pos >= 0:
                    break

            if match_pos < 0:
                context = old_expected[0].rstrip() if old_expected else "(empty)"
                return (
                    False,
                    f"Hunk failed for {fd['path']} at line {hunk['old_start']}: "
                    f"context mismatch near '{context}'",
                )

            # Apply: replace old lines with new lines
            file_lines[match_pos:match_pos + len(old_expected)] = new_replacement

        with open(target_file, "w") as f:
            f.writelines(file_lines)

    return (True, "")


def _lines_match(actual: List[str], expected: List[str]) -> bool:
    """Compare lines ignoring trailing whitespace differences."""
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected):
        if a.rstrip("\n\r") != e.rstrip("\n\r"):
            return False
    return True


def _is_binary(path: str) -> bool:
    """Heuristic: check if a file is binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True
