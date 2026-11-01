# -*- coding: utf-8 -*-
"""
modsloader - runescape
RuneScape: Dragonwilds 現代化極簡 Git 模組同步安裝器主程式入口
符合 AIToolLauncher 專案開發標準 (AI Tool Standard)
"""

import os
import sys
import ctypes
from pathlib import Path

# Windows CP950 終端編碼保護与 pythonw 無控制台防護
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

VERSION = "2.0.0"
__version__ = "2.0.0"

# 註冊專屬 Windows AppUserModelID，確保工作列顯示專屬 Dragonwilds 圖標
if sys.platform == "win32":
    try:
        myappid = "jiasai.modsloader.runescape.v2"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass


def main():
    print(f"Starting modsloader - runescape v{VERSION}...")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from src.main_window import MainWindow
    from src.theme_utils import get_app_font

    app = QApplication(sys.argv)
    app.setFont(get_app_font(10, False))

    icon_path = ROOT_DIR / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(version=VERSION)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
