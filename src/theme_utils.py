# -*- coding: utf-8 -*-
"""
動態語意色彩庫與高解析度圓角圖示渲染工具 (Impeccable Adaptive UI)
嚴格遵循 AI Tool Standard 第 6 節規範，根據當前系統深淺色主題動態回傳高對比語意色號。
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath
from qfluentwidgets import isDarkTheme


def get_state_color(state: str) -> str:
    """
    根據當前主題 (isDarkTheme()) 動態回傳語意色彩：
    - success: 深色 #6CCB5F / 淺色 #107C41
    - error:   深色 #FF99A4 / 淺色 #C42B1C
    - warning: 深色 #FCE100 / 淺色 #9D5D00
    - text:    深色 #FFFFFF / 淺色 #000000
    - muted:   深色 #A6ADC8 / 淺色 #5D5D5D
    - accent:  深色 #60CDFF / 淺色 #0078D4
    """
    dark = isDarkTheme()
    if state == "success":
        return "#6CCB5F" if dark else "#107C41"
    elif state == "error":
        return "#FF99A4" if dark else "#C42B1C"
    elif state == "warning":
        return "#FCE100" if dark else "#9D5D00"
    elif state == "accent":
        return "#60CDFF" if dark else "#0078D4"
    elif state == "text":
        return "#FFFFFF" if dark else "#000000"
    elif state == "muted":
        return "#A6ADC8" if dark else "#5D5D5D"
    elif state == "bg_stripe_1":
        return "#222222" if dark else "#F9F9F9"
    elif state == "bg_stripe_2":
        return "#2B2B2B" if dark else "#F0F0F0"
    elif state == "card_sub_bg":
        return "#26262B" if dark else "#F3F3F7"
    elif state == "border":
        return "#383842" if dark else "#E0E0E6"
    return "#FFFFFF" if dark else "#000000"


def get_app_font(size: int = 10, bold: bool = False) -> QFont:
    """
    全域字體優先指定為 Windows 11 的 Segoe UI Variable Display，
    並以 Microsoft YaHei UI / Microsoft JhengHei UI 作為繁中後備字體。
    """
    font = QFont()
    font.setFamilies(["Segoe UI Variable Display", "Microsoft YaHei UI", "Microsoft JhengHei UI", "Segoe UI"])
    font.setPointSize(size)
    font.setBold(bold)
    return font


def get_rounded_pixmap(src_pixmap: QPixmap, size: int, radius_ratio: float = 0.22) -> QPixmap:
    """
    將任意圖示裁切並繪製為最高解析度、平滑抗鋸齒圓角圖示 (比照 AIToolLauncher 標準)
    """
    if src_pixmap.isNull():
        return src_pixmap

    scaled = src_pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    radius = max(6, int(size * radius_ratio))

    dest = QPixmap(size, size)
    dest.fill(Qt.transparent)

    painter = QPainter(dest)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)

    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return dest
