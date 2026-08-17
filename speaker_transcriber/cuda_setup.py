from __future__ import annotations

import os
import sys
from pathlib import Path


def _frozen_bundle_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        internal_dir = install_dir / "_internal"
        for candidate in (internal_dir, install_dir):
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
    return roots


def _candidate_nvidia_bin_dirs() -> list[Path]:
    site_roots: list[Path] = list(_frozen_bundle_roots())
    venv_site = Path(sys.prefix) / "Lib" / "site-packages"
    if venv_site.is_dir() and venv_site not in site_roots:
        site_roots.append(venv_site)
    try:
        import site

        for entry in site.getsitepackages():
            path = Path(entry)
            if path.is_dir() and path not in site_roots:
                site_roots.append(path)
    except Exception:
        pass

    candidates: list[Path] = []
    seen: set[str] = set()
    for site_packages in site_roots:
        for library in ("cudnn", "cublas", "cuda_nvrtc"):
            directory = site_packages / "nvidia" / library / "bin"
            key = str(directory)
            if directory.is_dir() and key not in seen:
                seen.add(key)
                candidates.append(directory)
    return candidates


def configure_cuda_libraries() -> None:
    """Expose NVIDIA runtime DLLs required by CTranslate2 on Windows."""
    if os.name != "nt":
        return

    found_dirs = _candidate_nvidia_bin_dirs()

    for directory in found_dirs:
        path = str(directory)
        if path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{path}{os.pathsep}{os.environ.get('PATH', '')}"
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(path)
            except OSError:
                pass
