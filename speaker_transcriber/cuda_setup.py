from __future__ import annotations

import os
import sys
from pathlib import Path

from speaker_transcriber.debug_log import agent_log


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

    base_site = Path(sys.base_prefix) / "Lib" / "site-packages"
    venv_site = Path(sys.prefix) / "Lib" / "site-packages"
    cudnn_dll_base = base_site / "nvidia" / "cudnn" / "bin" / "cudnn_ops_infer64_8.dll"
    cudnn_dll_venv = venv_site / "nvidia" / "cudnn" / "bin" / "cudnn_ops_infer64_8.dll"
    found_dirs = _candidate_nvidia_bin_dirs()
    agent_log(
        "cuda_setup.py:configure_cuda_libraries",
        "cuda library discovery",
        {
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "found_dirs": [str(path) for path in found_dirs],
            "cudnn_dll_base_exists": cudnn_dll_base.exists(),
            "cudnn_dll_venv_exists": cudnn_dll_venv.exists(),
            "path_head": os.environ.get("PATH", "")[:500],
        },
        "H2",
    )

    for directory in found_dirs:
        path = str(directory)
        if path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{path}{os.pathsep}{os.environ.get('PATH', '')}"
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(path)
            except OSError:
                pass

    agent_log(
        "cuda_setup.py:configure_cuda_libraries",
        "cuda library configuration complete",
        {
            "configured_dirs": [str(path) for path in found_dirs],
            "path_contains_cudnn": "nvidia\\cudnn\\bin" in os.environ.get("PATH", "").lower(),
        },
        "H1",
    )
