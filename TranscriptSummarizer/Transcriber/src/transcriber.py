import os
import threading
import tempfile
import whisper
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from pathlib import Path
import ffmpeg
from tqdm import tqdm
from tkinterdnd2 import DND_FILES, TkinterDnD
import torch
import warnings

# Suppress PyTorch security warning about torch.load
warnings.filterwarnings("ignore", category=FutureWarning, module="torch.serialization")

# ... existing code ... 