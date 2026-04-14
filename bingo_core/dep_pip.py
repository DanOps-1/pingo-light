"""
bingo_core.dep_pip — pip/pipx backend for dependency patching.

Detects Python projects, fetches original packages from PyPI,
resolves install paths in site-packages/.

Python 3.8+ stdlib only.
"""

from __future__ import annotations

import json
import os
import site
import zipfile
from typing import List, Optional
from urllib.request import urlopen

from bingo_core.dep import DepBackend


class PipBackend(DepBackend):
    """Backend for pip/pipx Python packages."""

    name = "pip"

    def detect(self, cwd: str) -> bool:
        """Detect Python project by presence of requirements.txt, pyproject.toml, or venv."""
        indicators = [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            ".venv",
            "venv",
        ]
        return any(
            os.path.exists(os.path.join(cwd, f)) for f in indicators
        )

    def _find_site_packages(self, cwd: str) -> List[str]:
        """Find site-packages directories, preferring project venvs."""
        dirs = []

        # Check for project venv
        for venv_name in (".venv", "venv"):
            venv_path = os.path.join(cwd, venv_name)
            if os.path.isdir(venv_path):
                # Find site-packages inside venv
                for root, dirnames, _files in os.walk(venv_path):
                    if "site-packages" in dirnames:
                        dirs.append(os.path.join(root, "site-packages"))
                        break

        # System/user site-packages
        dirs.extend(site.getsitepackages())
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            dirs.append(user_site)

        return [d for d in dirs if os.path.isdir(d)]

    def get_installed_version(self, package: str, cwd: str) -> Optional[str]:
        """Get installed version via importlib.metadata or dist-info."""
        # Normalize package name
        normalized = package.replace("-", "_").lower()

        for sp_dir in self._find_site_packages(cwd):
            # Check dist-info directories
            for entry in os.listdir(sp_dir):
                if entry.endswith(".dist-info"):
                    dist_name = entry.rsplit("-", 1)[0].replace("-", "_").lower()
                    if dist_name == normalized:
                        metadata_path = os.path.join(sp_dir, entry, "METADATA")
                        if os.path.isfile(metadata_path):
                            with open(metadata_path) as f:
                                for line in f:
                                    if line.startswith("Version:"):
                                        return line.split(":", 1)[1].strip()
        return None

    def get_install_path(self, package: str, cwd: str) -> Optional[str]:
        """Get the filesystem path of the installed package."""
        normalized = package.replace("-", "_").lower()

        for sp_dir in self._find_site_packages(cwd):
            # Direct package directory
            for entry in os.listdir(sp_dir):
                if entry.replace("-", "_").lower() == normalized:
                    full = os.path.join(sp_dir, entry)
                    if os.path.isdir(full):
                        return full
        return None

    def fetch_original(self, package: str, version: str, dest: str) -> bool:
        """Download original package from PyPI and extract to dest.

        Prefers wheel (.whl) for consistency, falls back to sdist.
        """
        try:
            # Fetch package metadata from PyPI JSON API
            url = f"https://pypi.org/pypi/{package}/{version}/json"
            with urlopen(url, timeout=30) as resp:
                meta = json.loads(resp.read().decode())

            # Find wheel URL (prefer), then sdist
            download_url = None
            is_wheel = False
            for file_info in meta.get("urls", []):
                if file_info.get("packagetype") == "bdist_wheel":
                    download_url = file_info["url"]
                    is_wheel = True
                    break
            if not download_url:
                for file_info in meta.get("urls", []):
                    if file_info.get("packagetype") == "sdist":
                        download_url = file_info["url"]
                        break

            if not download_url:
                return False

            # Download
            tmp_file = os.path.join(dest, "_pkg.tmp")
            with urlopen(download_url, timeout=60) as resp:
                with open(tmp_file, "wb") as f:
                    f.write(resp.read())

            if is_wheel:
                # Wheel is a zip file
                normalized = package.replace("-", "_").lower()
                with zipfile.ZipFile(tmp_file) as zf:
                    for member in zf.namelist():
                        # Extract only the package directory
                        parts = member.split("/")
                        if parts[0].replace("-", "_").lower() == normalized:
                            zf.extract(member, dest)
                        elif parts[0].endswith(".dist-info") or parts[0].endswith(".data"):
                            continue  # Skip metadata
                        else:
                            # Single-file module
                            if member.endswith(".py"):
                                zf.extract(member, dest)
                # Move extracted package dir to dest root
                extracted = os.path.join(dest, normalized)
                if os.path.isdir(extracted):
                    # Already in right place
                    pass
            else:
                # Sdist: tar.gz — extract and find the package dir
                import tarfile
                with tarfile.open(tmp_file, "r:gz") as tar:
                    tar.extractall(dest)
                # Find the actual package inside the extracted tree
                # Sdist typically has project-version/ at top level

            os.remove(tmp_file)
            return True

        except Exception:
            return False

    def list_files(self, package: str, cwd: str) -> List[str]:
        """List all files in the installed package."""
        install_path = self.get_install_path(package, cwd)
        if not install_path:
            return []
        result = []
        for root, _dirs, files in os.walk(install_path):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, install_path)
                result.append(rel)
        return sorted(result)

    def install_hook_command(self) -> str:
        return "bingo-light dep apply"
