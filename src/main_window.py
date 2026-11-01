# -*- coding: utf-8 -*-
"""
RuneScape: Dragonwilds 模組同步安裝器 - 現代化極簡 Fluent GUI
參考 AIToolLauncher 與 SteamManifestUpdater (SMU) 視覺設計規範：
- 支援系統深淺色主題自動適配 (setTheme(Theme.AUTO)) 與手動快速切換
- 頂部品牌卡片 + 4 格狀態確認矩陣 (遊戲路徑、固定版 UE4SS、固定版 RuneSchema、擴充模組同步數)
- 一鍵從 Git 同步並安裝按鈕 + 即時進度條
- 可展開 / 收合的詳細模組清單 (TreeWidget 分類全展開 + 動態條紋色彩)
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFileDialog, QHeaderView, QTreeWidgetItem, QFrame
)
from qfluentwidgets import (
    setTheme, Theme, isDarkTheme, setThemeColor,
    CardWidget, StrongBodyLabel, BodyLabel, CaptionLabel, SubtitleLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, ToolButton,
    ProgressBar, TreeWidget, InfoBar, InfoBarPosition, FluentIcon, MessageBox
)

from src.theme_utils import get_state_color, get_app_font, get_rounded_pixmap
from src import mod_manager


class InstallWorker(QThread):
    """背景執行 Git 同步與 30 項套件/模組解壓安裝的 Worker 執行緒"""
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str, int, int)

    def __init__(self, game_path: str, selected_filenames: Optional[List[str]] = None, sync_git: bool = True):
        super().__init__()
        self.game_path = game_path
        self.selected_filenames = selected_filenames
        self.sync_git = sync_git

    def run(self):
        try:
            ok, msg, cnt, tot = mod_manager.install_all_mods(
                game_path=self.game_path,
                selected_filenames=self.selected_filenames,
                sync_git=self.sync_git,
                progress_callback=lambda pct, text: self.progress_signal.emit(pct, text),
            )
            self.finished_signal.emit(ok, msg, cnt, tot)
        except Exception as e:
            self.finished_signal.emit(False, f"安裝過程發生未預期異常: {e}", 0, 0)


class StatusMetricCard(CardWidget):
    """狀態確認四宮格小卡 (比照 SMU / AIToolLauncher 狀態確認卡片設計)"""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self.lbl_title = CaptionLabel(title, self)
        self.lbl_title.setFont(get_app_font(9, False))

        self.lbl_value = StrongBodyLabel("檢測中...", self)
        self.lbl_value.setFont(get_app_font(11, True))

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_status(self, text: str, state: str = "text"):
        color = get_state_color(state)
        self.lbl_value.setText(text)
        self.lbl_value.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.lbl_title.setStyleSheet(f"color: {get_state_color('muted')};")


class MainWindow(QWidget):
    COLLAPSED_HEIGHT = 355
    EXPANDED_HEIGHT = 720
    WINDOW_WIDTH = 860

    def __init__(self, version: str = "2.0.0"):
        super().__init__()
        self.version = version
        self.is_list_expanded = False
        self.worker: Optional[InstallWorker] = None
        self.current_status = {}

        # 預設跟隨系統深淺色主題，並設定高質感主題色
        setTheme(Theme.AUTO)
        setThemeColor("#0078D4")

        self.setWindowTitle(f"modsloader - runescape v{self.version}")
        self.resize(self.WINDOW_WIDTH, self.COLLAPSED_HEIGHT)
        self.setMinimumWidth(780)
        self.setMinimumHeight(self.COLLAPSED_HEIGHT)

        # 載入視窗圖示
        self.icon_path = mod_manager.ROOT_DIR / "assets" / "icon.png"
        if self.icon_path.exists():
            self.setWindowIcon(QIcon(str(self.icon_path)))

        self._init_ui()
        self._apply_adaptive_theme()

        # 自動偵測遊戲路徑並刷新狀態
        detected = mod_manager.detect_game_path()
        self.game_path = detected
        self.refresh_status()

    def _init_ui(self):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 16, 18, 16)
        self.root_layout.setSpacing(12)

        # =====================================================================
        # 1. 頂部品牌與遊戲路徑橫幅卡片 (Hero Header Card)
        # =====================================================================
        self.header_card = CardWidget(self)
        header_layout = QHBoxLayout(self.header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(14)

        # 圓角 Dragonwilds 圖示
        self.lbl_logo = QLabel(self.header_card)
        self.lbl_logo.setFixedSize(56, 56)
        if self.icon_path.exists():
            pix = QPixmap(str(self.icon_path))
            self.lbl_logo.setPixmap(get_rounded_pixmap(pix, 56, 0.22))
        header_layout.addWidget(self.lbl_logo)

        # 標題與路徑資訊
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.lbl_app_title = SubtitleLabel("RuneScape: Dragonwilds 模組同步安裝器", self.header_card)
        self.lbl_app_title.setFont(get_app_font(14, True))
        self.lbl_ver_badge = CaptionLabel(f"v{self.version}", self.header_card)
        self.lbl_ver_badge.setFont(get_app_font(9, True))
        title_row.addWidget(self.lbl_app_title)
        title_row.addWidget(self.lbl_ver_badge)
        title_row.addStretch(1)

        self.lbl_game_path = CaptionLabel("正在自動掃描 Steam 遊戲安裝路徑...", self.header_card)
        self.lbl_game_path.setFont(get_app_font(9, False))

        title_col.addLayout(title_row)
        title_col.addWidget(self.lbl_game_path)
        header_layout.addLayout(title_col, 1)

        # 右側工具按鈕組 (變更路徑 / 開啟目錄 / 切換深淺主題)
        btn_col = QHBoxLayout()
        btn_col.setSpacing(6)

        self.btn_browse = PushButton(FluentIcon.FOLDER_ADD, "變更路徑", self.header_card)
        self.btn_browse.setFixedHeight(32)
        self.btn_browse.clicked.connect(self.on_browse_game_path)

        self.btn_open_dir = ToolButton(FluentIcon.FOLDER, self.header_card)
        self.btn_open_dir.setFixedSize(32, 32)
        self.btn_open_dir.setToolTip("開啟遊戲安裝資料夾")
        self.btn_open_dir.clicked.connect(self.on_open_game_dir)

        self.btn_theme = ToolButton(FluentIcon.CONSTRACT, self.header_card)
        self.btn_theme.setFixedSize(32, 32)
        self.btn_theme.setToolTip("切換深色 / 淺色主題")
        self.btn_theme.clicked.connect(self.on_toggle_theme)

        btn_col.addWidget(self.btn_browse)
        btn_col.addWidget(self.btn_open_dir)
        btn_col.addWidget(self.btn_theme)
        header_layout.addLayout(btn_col)

        self.root_layout.addWidget(self.header_card)

        # =====================================================================
        # 2. 狀態確認四宮格矩陣 (Status Confirmation Grid)
        # =====================================================================
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        self.card_stat_game = StatusMetricCard("🎮 遊戲主程式狀態", self)
        self.card_stat_ue4ss = StatusMetricCard("⚡ UE4SS 核心載入器 (固定版)", self)
        self.card_stat_rs = StatusMetricCard("🧩 RuneSchema 擴充框架 (固定版)", self)
        self.card_stat_mods = StatusMetricCard("📦 擴充模組安裝狀態", self)

        grid_layout.addWidget(self.card_stat_game, 0, 0)
        grid_layout.addWidget(self.card_stat_ue4ss, 0, 1)
        grid_layout.addWidget(self.card_stat_rs, 0, 2)
        grid_layout.addWidget(self.card_stat_mods, 0, 3)

        self.root_layout.addLayout(grid_layout)

        # =====================================================================
        # 3. 核心一鍵安裝與狀態回饋控制卡 (One-Click Install Bar)
        # =====================================================================
        self.action_card = CardWidget(self)
        action_layout = QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(16, 14, 16, 14)
        action_layout.setSpacing(10)

        top_action_row = QHBoxLayout()
        top_action_row.setSpacing(12)

        status_text_col = QVBoxLayout()
        status_text_col.setSpacing(4)
        self.lbl_action_title = StrongBodyLabel("☁️ 雲端 Git 模組庫已就緒", self.action_card)
        self.lbl_action_title.setFont(get_app_font(11, True))
        self.lbl_action_sub = CaptionLabel(
            "點擊右側按鈕將自動從 Git 拉取最新壓縮檔，並依序安裝固定版 UE4SS、RuneSchema 與所有勾選模組。",
            self.action_card
        )
        self.lbl_action_sub.setFont(get_app_font(9, False))
        status_text_col.addWidget(self.lbl_action_title)
        status_text_col.addWidget(self.lbl_action_sub)
        top_action_row.addLayout(status_text_col, 1)

        # 重新檢測按鈕
        self.btn_refresh = PushButton(FluentIcon.SYNC, "重新檢測", self.action_card)
        self.btn_refresh.setFixedHeight(38)
        self.btn_refresh.clicked.connect(self.refresh_status)

        # 清除模組按鈕
        self.btn_uninstall = PushButton(FluentIcon.DELETE, "清除模組", self.action_card)
        self.btn_uninstall.setFixedHeight(38)
        self.btn_uninstall.setToolTip("一鍵移除遊戲目錄內的 UE4SS、RuneSchema 與所有模組，恢復純淨原版")
        self.btn_uninstall.clicked.connect(self.on_uninstall_all)

        # 一鍵同步並安裝主按鈕
        self.btn_install = PrimaryPushButton(FluentIcon.DOWNLOAD, "一鍵同步並安裝模組", self.action_card)
        self.btn_install.setFixedSize(210, 38)
        self.btn_install.setFont(get_app_font(10, True))
        self.btn_install.clicked.connect(self.on_start_install)

        top_action_row.addWidget(self.btn_refresh)
        top_action_row.addWidget(self.btn_uninstall)
        top_action_row.addWidget(self.btn_install)
        action_layout.addLayout(top_action_row)

        # 進度條
        self.progress_bar = ProgressBar(self.action_card)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        action_layout.addWidget(self.progress_bar)

        self.root_layout.addWidget(self.action_card)

        # =====================================================================
        # 4. 展開 / 關閉的詳細模組清單 (Collapsible Detailed Mod List)
        # =====================================================================
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(2, 0, 2, 0)

        self.btn_toggle_list = TransparentPushButton(
            FluentIcon.DOWN,
            "展開詳細模組清單 (載入中...)",
            self
        )
        self.btn_toggle_list.setFont(get_app_font(10, True))
        self.btn_toggle_list.clicked.connect(self.on_toggle_mod_list)
        toggle_row.addWidget(self.btn_toggle_list)
        toggle_row.addStretch(1)

        self.btn_select_all = TransparentPushButton("全選擴充模組", self)
        self.btn_select_all.setFont(get_app_font(9, False))
        self.btn_select_all.clicked.connect(lambda: self._set_all_addons_checked(True))
        self.btn_select_all.hide()

        self.btn_deselect_all = TransparentPushButton("取消全選", self)
        self.btn_deselect_all.setFont(get_app_font(9, False))
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_addons_checked(False))
        self.btn_deselect_all.hide()

        toggle_row.addWidget(self.btn_select_all)
        toggle_row.addWidget(self.btn_deselect_all)

        self.root_layout.addLayout(toggle_row)

        # 詳細模組清單容器卡片 (預設收合隱藏)
        self.list_card = CardWidget(self)
        list_layout = QVBoxLayout(self.list_card)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(6)

        self.tree_mods = TreeWidget(self.list_card)
        self.tree_mods.setColumnCount(5)
        self.tree_mods.setHeaderLabels(["模組名稱 (可勾選安裝)", "版本", "類型", "當前狀態", "目標相對路徑"])
        self.tree_mods.setFont(get_app_font(9, False))
        self.tree_mods.setIndentation(18)
        self.tree_mods.setRootIsDecorated(True)

        header = self.tree_mods.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # 最後一欄 Stretch 填滿畫面
        self.tree_mods.setColumnWidth(0, 290)

        list_layout.addWidget(self.tree_mods, 1)
        self.list_card.hide()
        self.root_layout.addWidget(self.list_card, 1)

    # =========================================================================
    # 主題與語意色彩更新
    # =========================================================================

    def _apply_adaptive_theme(self):
        bg_root = get_state_color("bg_stripe_1")
        text_color = get_state_color("text")
        muted_color = get_state_color("muted")
        accent_color = get_state_color("accent")

        self.setStyleSheet(f"MainWindow {{ background-color: {bg_root}; }}")
        self.lbl_app_title.setStyleSheet(f"color: {text_color}; font-weight: 700;")
        self.lbl_ver_badge.setStyleSheet(
            f"color: {accent_color}; background: {get_state_color('card_sub_bg')}; "
            f"border: 1px solid {get_state_color('border')}; border-radius: 6px; padding: 2px 8px;"
        )
        self.lbl_game_path.setStyleSheet(f"color: {muted_color};")
        self.lbl_action_title.setStyleSheet(f"color: {text_color}; font-weight: 700;")
        self.lbl_action_sub.setStyleSheet(f"color: {muted_color};")

    def on_toggle_theme(self):
        if isDarkTheme():
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.DARK)
        self._apply_adaptive_theme()
        self.refresh_status()

    # =========================================================================
    # 展開 / 收合詳細模組清單
    # =========================================================================

    def on_toggle_mod_list(self):
        self.is_list_expanded = not self.is_list_expanded
        total_cnt = self.current_status.get("total_all", 30)
        addons_cnt = self.current_status.get("total_addons", 28)

        if self.is_list_expanded:
            self.list_card.show()
            self.btn_select_all.show()
            self.btn_deselect_all.show()
            self.btn_toggle_list.setIcon(FluentIcon.UP)
            self.btn_toggle_list.setText(f"收合詳細模組清單 (共 {total_cnt} 項：2 核心框架 + {addons_cnt} 擴充模組)")
            self.setMinimumHeight(560)
            self.resize(self.width(), self.EXPANDED_HEIGHT)
            self.tree_mods.expandAll()
        else:
            self.list_card.hide()
            self.btn_select_all.hide()
            self.btn_deselect_all.hide()
            self.btn_toggle_list.setIcon(FluentIcon.DOWN)
            self.btn_toggle_list.setText(f"展開詳細模組清單 (共 {total_cnt} 項：2 核心框架 + {addons_cnt} 擴充模組)")
            self.setMinimumHeight(self.COLLAPSED_HEIGHT)
            self.resize(self.width(), self.COLLAPSED_HEIGHT)

    # =========================================================================
    # 狀態檢測與清單渲染
    # =========================================================================

    def refresh_status(self):
        # 記住目前已取消勾選的項目
        unchecked_files = self._get_unchecked_filenames()

        st = mod_manager.get_overall_status(self.game_path)
        self.current_status = st

        # 1. 更新路徑與遊戲主程式狀態
        if st["game_valid"]:
            self.lbl_game_path.setText(f"📍 遊戲安裝目錄: {self.game_path}")
            self.lbl_game_path.setStyleSheet(f"color: {get_state_color('muted')};")
            self.card_stat_game.set_status("🟢 已定位遊戲目錄", "success")
        else:
            if self.game_path:
                self.lbl_game_path.setText(f"⚠️ 找不到 RSDragonwilds.exe: {self.game_path}")
            else:
                self.lbl_game_path.setText("⚠️ 尚未定位遊戲資料夾，請點擊右上角「變更路徑」指定 RSDragonwilds 目錄")
            self.lbl_game_path.setStyleSheet(f"color: {get_state_color('error')};")
            self.card_stat_game.set_status("🔴 未找到遊戲目錄", "error")

        # 2. 更新固定版 UE4SS 狀態
        if st["ue4ss_installed"]:
            self.card_stat_ue4ss.set_status(f"🟢 已安裝 (v{st['ue4ss_version']})", "success")
        else:
            self.card_stat_ue4ss.set_status(f"🔴 未安裝 (v{st['ue4ss_version']})", "error")

        # 3. 更新固定版 RuneSchema 狀態
        if st["runeschema_installed"]:
            self.card_stat_rs.set_status(f"🟢 已安裝 (v{st['runeschema_version']})", "success")
        else:
            self.card_stat_rs.set_status(f"🔴 未安裝 (v{st['runeschema_version']})", "error")

        # 4. 更新擴充模組安裝狀態
        inst_add = st["installed_addons"]
        tot_add = st["total_addons"]
        if not st["game_valid"]:
            self.card_stat_mods.set_status(f"⚪ 待定位 (0 / {tot_add})", "muted")
        elif inst_add == tot_add and tot_add > 0:
            self.card_stat_mods.set_status(f"🟢 全部就緒 ({inst_add} / {tot_add})", "success")
        elif inst_add > 0:
            self.card_stat_mods.set_status(f"🟡 部分安裝 ({inst_add} / {tot_add})", "warning")
        else:
            self.card_stat_mods.set_status(f"🔴 尚未安裝 (0 / {tot_add})", "error")

        # 更新展開/收合按鈕文字
        total_cnt = st["total_all"]
        prefix = "收合詳細模組清單" if self.is_list_expanded else "展開詳細模組清單"
        self.btn_toggle_list.setText(f"{prefix} (共 {total_cnt} 項：2 核心框架 + {tot_add} 擴充模組)")

        # 5. 重新渲染詳細模組樹狀清單
        self._populate_tree(st["items"], unchecked_files)

    def _populate_tree(self, items: List[dict], unchecked_files: set):
        self.tree_mods.clear()

        categories = [
            ("核心框架", "🛡️ 核心前置框架 (固定必裝版本)"),
            ("Lua 模組", "📜 UE4SS Lua 腳本模組"),
            ("Pak 模組", "📦 Pak 資源模組"),
            ("RuneSchema 模組", "🧬 RuneSchema 數據模組"),
        ]

        stripe_1 = QBrush(QColor(get_state_color("bg_stripe_1")))
        stripe_2 = QBrush(QColor(get_state_color("bg_stripe_2")))
        text_brush = QBrush(QColor(get_state_color("text")))
        muted_brush = QBrush(QColor(get_state_color("muted")))
        succ_brush = QBrush(QColor(get_state_color("success")))
        err_brush = QBrush(QColor(get_state_color("error")))
        accent_brush = QBrush(QColor(get_state_color("accent")))

        for cat_key, cat_title in categories:
            cat_items = [m for m in items if m["category"] == cat_key]
            if not cat_items:
                continue

            inst_in_cat = sum(1 for m in cat_items if m["installed"])
            cat_node = QTreeWidgetItem(self.tree_mods)
            cat_node.setText(0, f"{cat_title} ({inst_in_cat}/{len(cat_items)})")
            cat_node.setFont(0, get_app_font(9, True))
            cat_node.setForeground(0, accent_brush)
            cat_node.setFirstColumnSpanned(False)

            for idx, m in enumerate(cat_items):
                row_node = QTreeWidgetItem(cat_node)
                row_node.setData(0, Qt.UserRole, m["filename"])
                row_node.setData(0, Qt.UserRole + 1, m["is_core"])

                row_node.setText(0, m["name"])
                row_node.setText(1, f"v{m['version']}")
                row_node.setText(2, m["category"])
                row_node.setText(3, "🟢 已安裝" if m["installed"] else "⚪ 未安裝")
                row_node.setText(4, m["target_rel"])

                # 勾選框設定：核心框架固定鎖定勾選，擴充模組可自由勾選
                if m["is_core"]:
                    row_node.setCheckState(0, Qt.Checked)
                    row_node.setFlags(row_node.flags() & ~Qt.ItemIsUserCheckable)
                else:
                    is_checked = m["filename"] not in unchecked_files
                    row_node.setCheckState(0, Qt.Checked if is_checked else Qt.Unchecked)

                bg_brush = stripe_1 if idx % 2 == 0 else stripe_2
                for col in range(5):
                    row_node.setBackground(col, bg_brush)

                row_node.setForeground(0, text_brush)
                row_node.setForeground(1, muted_brush)
                row_node.setForeground(2, muted_brush)
                row_node.setForeground(3, succ_brush if m["installed"] else err_brush)
                row_node.setForeground(4, muted_brush)

        # 預設全展開所有分類節點
        self.tree_mods.expandAll()

    def _get_unchecked_filenames(self) -> set:
        unchecked = set()
        root = self.tree_mods.invisibleRootItem()
        for i in range(root.childCount()):
            cat_node = root.child(i)
            for j in range(cat_node.childCount()):
                row_node = cat_node.child(j)
                fname = row_node.data(0, Qt.UserRole)
                is_core = row_node.data(0, Qt.UserRole + 1)
                if fname and not is_core and row_node.checkState(0) == Qt.Unchecked:
                    unchecked.add(fname)
        return unchecked

    def _get_selected_filenames(self) -> List[str]:
        selected = []
        root = self.tree_mods.invisibleRootItem()
        if root.childCount() == 0:
            return [m["filename"] for m in self.current_status.get("items", [])]

        for i in range(root.childCount()):
            cat_node = root.child(i)
            for j in range(cat_node.childCount()):
                row_node = cat_node.child(j)
                fname = row_node.data(0, Qt.UserRole)
                is_core = row_node.data(0, Qt.UserRole + 1)
                if fname and (is_core or row_node.checkState(0) == Qt.Checked):
                    selected.append(fname)
        return selected

    def _set_all_addons_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        root = self.tree_mods.invisibleRootItem()
        for i in range(root.childCount()):
            cat_node = root.child(i)
            for j in range(cat_node.childCount()):
                row_node = cat_node.child(j)
                if not row_node.data(0, Qt.UserRole + 1):
                    row_node.setCheckState(0, state)

    # =========================================================================
    # 互動事件處理 (變更路徑 / 一鍵同步安裝 / 清除模組)
    # =========================================================================

    def on_browse_game_path(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇 RuneScape: Dragonwilds 遊戲安裝根目錄 (需包含 RSDragonwilds.exe)",
            self.game_path or ""
        )
        if selected:
            self.game_path = os.path.abspath(selected)
            cfg = mod_manager.load_config()
            cfg["game_path"] = self.game_path
            mod_manager.save_config(cfg)
            self.refresh_status()

            if mod_manager.is_valid_game_dir(self.game_path):
                InfoBar.success(
                    title="路徑已設定",
                    content=f"已定位 RSDragonwilds 遊戲目錄：{self.game_path}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    title="目錄驗證提醒",
                    content="該資料夾下未找到 RSDragonwilds.exe，請確認是否為正確的遊戲根目錄。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=self,
                )

    def on_open_game_dir(self):
        if self.game_path and os.path.exists(self.game_path):
            os.startfile(self.game_path)
        else:
            InfoBar.error(
                title="無法開啟目錄",
                content="請先設定有效的遊戲安裝目錄！",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def on_start_install(self):
        if not mod_manager.is_valid_game_dir(self.game_path):
            InfoBar.error(
                title="尚未找到遊戲目錄",
                content="請先點擊右上角「變更路徑」選擇 RSDragonwilds 安裝資料夾！",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        selected_files = self._get_selected_filenames()
        self.btn_install.setEnabled(False)
        self.btn_uninstall.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        self.btn_browse.setEnabled(False)

        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_action_title.setText("⏳ 正在從 Git 同步並部署模組...")

        self.worker = InstallWorker(
            game_path=self.game_path,
            selected_filenames=selected_files,
            sync_git=True,
        )
        self.worker.progress_signal.connect(self._on_install_progress)
        self.worker.finished_signal.connect(self._on_install_finished)
        self.worker.start()

    def _on_install_progress(self, pct: int, text: str):
        self.progress_bar.setValue(pct)
        self.lbl_action_sub.setText(text)

    def _on_install_finished(self, ok: bool, msg: str, cnt: int, tot: int):
        self.btn_install.setEnabled(True)
        self.btn_uninstall.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.btn_browse.setEnabled(True)

        self.refresh_status()

        if ok:
            self.lbl_action_title.setText(f"✅ 模組同步與安裝完成 ({cnt}/{tot})")
            self.lbl_action_sub.setText("所有核心框架 (UE4SS + RuneSchema) 與擴充模組均已配置完畢，可直接啟動遊戲！")
            InfoBar.success(
                title="安裝成功",
                content=f"已成功同步並安裝 {cnt} / {tot} 項套件與模組！",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
        else:
            self.lbl_action_title.setText("❌ 安裝過程發生異常")
            self.lbl_action_sub.setText(msg)
            InfoBar.error(
                title="安裝失敗",
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def on_uninstall_all(self):
        if not mod_manager.is_valid_game_dir(self.game_path):
            InfoBar.warning(
                title="提示",
                content="目前尚未指定有效的遊戲目錄。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        box = MessageBox(
            "確認清除所有模組",
            "確定要移除遊戲目錄內的 UE4SS、RuneSchema 及所有已安裝的 Pak / Lua 模組嗎？\n\n此操作將使遊戲恢復為純淨原版狀態。",
            self
        )
        box.yesButton.setText("確定清除")
        box.cancelButton.setText("取消")
        if not box.exec():
            return

        ok, msg = mod_manager.uninstall_all_mods(self.game_path)
        self.refresh_status()
        if ok:
            self.lbl_action_title.setText("🧹 已還原純淨遊戲目錄")
            self.lbl_action_sub.setText(msg)
            self.progress_bar.hide()
            InfoBar.success(
                title="清除完成",
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
        else:
            InfoBar.error(
                title="清除失敗",
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
