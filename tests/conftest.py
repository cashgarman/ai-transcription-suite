import os


# Widget tests build real windows; keep them off the developer's screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
