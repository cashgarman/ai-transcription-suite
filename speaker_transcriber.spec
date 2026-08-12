# Build with: scripts\build_windows.bat
# Or: pyinstaller --clean -y speaker_transcriber.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)

hiddenimports = (
    collect_submodules("faster_whisper")
    + collect_submodules("whisperx")
    + collect_submodules("pyannote")
    + collect_submodules("speechbrain")
    + [
        "speaker_transcriber",
        "speaker_transcriber.app",
        "speaker_transcriber.ui.main_window",
        "speaker_transcriber.pipeline.processor",
        "keyring.backends.Windows",
    ]
)
datas = (
    collect_data_files("whisperx")
    + collect_data_files("pyannote.audio")
    + collect_data_files("faster_whisper")
)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("torch")

if sys.platform == "win32":
    for library in ("cudnn", "cublas", "cuda_nvrtc"):
        try:
            binaries += collect_dynamic_libs(f"nvidia.{library}")
        except Exception:
            pass

a = Analysis(
    ["app.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "speaker_transcriber" / "pyi_rth_cuda.py")],
    excludes=["tkinter", "customtkinter", "IPython", "jupyter", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SpeakerTranscriber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SpeakerTranscriber",
)
