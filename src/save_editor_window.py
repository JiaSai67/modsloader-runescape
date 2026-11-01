# -*- coding: utf-8 -*-
"""
MLRS - 世界存檔自訂難度設定編輯器 (World Save Settings Editor)
採用 QFluentWidgets 打造現代流暢視覺，支援自由鍵盤輸入任何浮點數值（突破 3.0 上限）
可即時切換無建築穩定性、背包負重、經驗值倍率、法術冷卻、耐力與生存消耗等
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QScrollArea, QFrame
)
from qfluentwidgets import (
    CardWidget, SubtitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    PrimaryPushButton, PushButton, TransparentPushButton,
    ComboBox, DoubleSpinBox, SwitchButton, InfoBar, InfoBarPosition,
    FluentIcon, MessageBox
)

from src.save_manager import (
    list_save_files, read_save_settings, write_save_settings,
    DIFFICULTY_META, get_save_games_dir
)


class SaveEditorDialog(QDialog):
    """世界存檔自訂難度設定對話框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("世界存檔自訂設定編輯器 (突破 3.0 上限 & 自由輸入)")
        self.resize(880, 680)

        self.current_sav_path: Optional[str] = None
        self.current_settings: Dict[str, float] = {}
        self.input_widgets: Dict[str, Any] = {}

        self._init_ui()
        self._load_saves()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(16)

        # 1. 頂部標題與說明卡片
        header_card = CardWidget(self)
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(18, 14, 18, 14)
        h_layout.setSpacing(6)

        title = SubtitleLabel("🌍 世界存檔自訂難度與規則設定", header_card)
        tip = CaptionLabel(
            "提示：此工具直接修改本機 .sav 存檔，支援手動鍵盤精準輸入任意數字（可突破官方滑桿 3.0 最大值，如 5.0, 10.0, 50.0），"
            "儲存前會自動在存檔目錄產生帶時間戳記的 .bak 備份檔案，保障存檔安全。",
            header_card
        )
        tip.setStyleSheet("color: #888888;")
        h_layout.addWidget(title)
        h_layout.addWidget(tip)
        root_layout.addWidget(header_card)

        # 2. 存檔選擇列
        sel_card = CardWidget(self)
        s_layout = QHBoxLayout(sel_card)
        s_layout.setContentsMargins(16, 12, 16, 12)
        s_layout.setSpacing(12)

        s_layout.addWidget(StrongBodyLabel("選擇存檔：", sel_card))

        self.save_combo = ComboBox(sel_card)
        self.save_combo.setMinimumWidth(320)
        self.save_combo.currentIndexChanged.connect(self._on_save_selected)
        s_layout.addWidget(self.save_combo, 1)

        self.btn_refresh = PushButton("重新整理", sel_card, FluentIcon.SYNC)
        self.btn_refresh.clicked.connect(self._load_saves)
        s_layout.addWidget(self.btn_refresh)

        self.btn_open_folder = PushButton("開啟存檔資料夾", sel_card, FluentIcon.FOLDER)
        self.btn_open_folder.clicked.connect(self._open_saves_folder)
        s_layout.addWidget(self.btn_open_folder)

        root_layout.addWidget(sel_card)

        # 3. 中間滾動設定面板
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(14)
        scroll.setWidget(self.content_widget)
        root_layout.addWidget(scroll, 1)

        # 4. 底部按鈕
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.status_label = CaptionLabel("", self)
        bottom_bar.addWidget(self.status_label, 1)

        self.btn_cancel = PushButton("關閉", self)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_save = PrimaryPushButton("💾 儲存修改至存檔", self)
        self.btn_save.clicked.connect(self._save_changes)
        bottom_bar.addWidget(self.btn_save)

        root_layout.addLayout(bottom_bar)

    def _load_saves(self):
        """載入本機世界存檔列表"""
        self.save_combo.clear()
        saves = list_save_files()
        # 過濾非世界存檔
        world_saves = []
        for s in saves:
            if s["filename"] in ("EnhancedInputUserSettings.sav", "UserSettings.sav"):
                continue
            world_saves.append(s)

        if not world_saves:
            self.save_combo.addItem("未偵測到任何世界存檔 (.sav)", "")
            self.btn_save.setEnabled(False)
            self._clear_settings_ui()
            return

        self.btn_save.setEnabled(True)
        for s in world_saves:
            text = f"{s['world_name']}  ({s['mtime']} | {s['size'] // 1024} KB)"
            self.save_combo.addItem(text, s["path"])

        # 預設選取第一項
        self.save_combo.setCurrentIndex(0)

    def _on_save_selected(self, index: int):
        sav_path = self.save_combo.currentData()
        if not sav_path or not os.path.exists(sav_path):
            self._clear_settings_ui()
            return

        self.current_sav_path = sav_path
        try:
            res = read_save_settings(sav_path)
            self.current_settings = res.get("settings", {})
            self._populate_settings_ui()
            self.status_label.setText(f"目前存檔: {Path(sav_path).name} (包含 {len(self.current_settings)} 項設定)")
        except Exception as e:
            self._clear_settings_ui()
            InfoBar.error(
                title="讀取存檔失敗",
                content=str(e),
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                parent=self
            )

    def _clear_settings_ui(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.input_widgets.clear()

    def _populate_settings_ui(self):
        """根據分類建立 UI 設定卡片"""
        self._clear_settings_ui()

        # 分組整理
        categories: Dict[str, list] = {}
        for tag, meta in DIFFICULTY_META.items():
            cat = meta.get("category", "其他設定")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((tag, meta))

        # 其他未在常用對照表的標籤放入「進階 AI 與細部標籤」
        unmapped = []
        for tag, val in self.current_settings.items():
            if tag not in DIFFICULTY_META:
                unmapped.append((tag, {
                    "name": tag.replace("Difficulty.", ""),
                    "category": "⚙️ 其他細部標籤",
                    "type": "float",
                    "default": 1.0,
                    "desc": tag
                }))
        if unmapped:
            categories["⚙️ 其他細部標籤"] = unmapped

        # 按分類建立 CardWidget
        for cat_name, items in categories.items():
            cat_card = CardWidget(self.content_widget)
            cat_layout = QVBoxLayout(cat_card)
            cat_layout.setContentsMargins(18, 14, 18, 14)
            cat_layout.setSpacing(10)

            # 分類標題
            cat_header = StrongBodyLabel(cat_name, cat_card)
            cat_header.setStyleSheet("color: #0078D4; font-size: 15px; font-weight: bold;")
            cat_layout.addWidget(cat_header)

            grid = QGridLayout()
            grid.setSpacing(12)
            row = 0

            for tag, meta in items:
                curr_val = self.current_settings.get(tag, meta.get("default", 1.0))
                label_name = meta.get("name", tag)
                desc = meta.get("desc", "")
                is_bool = (meta.get("type") == "bool")

                lbl_col = QVBoxLayout()
                lbl_col.setSpacing(2)
                item_lbl = BodyLabel(label_name, cat_card)
                lbl_col.addWidget(item_lbl)
                if desc:
                    desc_lbl = CaptionLabel(desc, cat_card)
                    desc_lbl.setStyleSheet("color: #777777;")
                    lbl_col.addWidget(desc_lbl)

                grid.addLayout(lbl_col, row, 0)

                # 輸入元件
                if is_bool:
                    switch = SwitchButton(cat_card)
                    switch.setChecked(bool(curr_val >= 0.5))
                    grid.addWidget(switch, row, 1, Qt.AlignRight)
                    self.input_widgets[tag] = ("bool", switch)
                else:
                    spin = DoubleSpinBox(cat_card)
                    spin.setRange(0.0, 9999.0)
                    spin.setDecimals(2)
                    spin.setSingleStep(0.5)
                    spin.setMinimumWidth(120)
                    spin.setValue(float(curr_val))
                    grid.addWidget(spin, row, 1, Qt.AlignRight)
                    self.input_widgets[tag] = ("float", spin)

                row += 1

            cat_layout.addLayout(grid)
            self.content_layout.addWidget(cat_card)

        self.content_layout.addStretch(1)

    def _save_changes(self):
        """將所有輸入的設定寫回存檔"""
        if not self.current_sav_path or not os.path.exists(self.current_sav_path):
            InfoBar.warning(
                title="警告",
                content="請先選擇有效之存檔檔案！",
                parent=self
            )
            return

        new_settings = dict(self.current_settings)
        for tag, (wtype, widget) in self.input_widgets.items():
            if wtype == "bool":
                new_settings[tag] = 1.0 if widget.isChecked() else 0.0
            else:
                new_settings[tag] = float(widget.value())

        try:
            bak_path = write_save_settings(self.current_sav_path, new_settings)
            bak_name = Path(bak_path).name
            InfoBar.success(
                title="存檔設定儲存成功！",
                content=f"已成功寫入 {Path(self.current_sav_path).name}！\n已在原目錄建立備份: {bak_name}",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )
            self.current_settings = new_settings
        except Exception as e:
            InfoBar.error(
                title="儲存失敗",
                content=f"寫入存檔時發生錯誤: {str(e)}",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )

    def _open_saves_folder(self):
        """在檔案總管開啟存檔目錄"""
        sdir = get_save_games_dir()
        if sdir and sdir.exists():
            os.startfile(str(sdir))
        else:
            InfoBar.warning(
                title="提示",
                content="未找到存檔目錄！",
                parent=self
            )
