"""PyInstaller runtime hook: expose NVIDIA DLLs before other imports run."""

from speaker_transcriber.cuda_setup import configure_cuda_libraries

configure_cuda_libraries()
