# -*- coding: utf-8 -*-
"""
RuneScape: Dragonwilds 模組同步與智慧安裝核心引擎 (Mod Manager Core)
支援：
1. 自動從 GitHub 儲存庫拉取 / Clone 最新壓縮檔模組庫 (方案 B：原封不動上傳壓縮檔至 Git)
2. 固定雙核心前置套件優先部署：
   - UE4SS = "UE4SS Steam (latest) 4 3.0.1-gf6d5f942 2026-09-16T16-30Z xEKUeeFss"
   - RuneSchema = "RuneSchema (Steam) 570 0.8.0.3 2026-10-30T20-06Z AMadvv1Fj"
3. 四階段智慧模組結構識別與安裝：
   - 根目錄直通型 / 單層外殼包裝型 (RSDragonwilds/...)
   - RuneSchema 數據載入器型 (assets, blueprints, raw, recipes 等 JSON 模組 -> ue4ss/Mods/RuneSchema/mods/)
   - Unreal Engine 5.6 Pak 資源模組 (.pak, .ucas, .utoc -> Content/Paks/~mods/)
   - UE4SS Lua 腳本模組 (Scripts/main.lua, enabled.txt -> ue4ss/Mods/ 並寫入 mods.txt)
"""

import os
import re
import sys
import json
import shutil
import zipfile
import winreg
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable

# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.json"

# GitHub 雲端模組儲存庫設定
REPO_OWNER = "JiaSai67"
REPO_NAME = "modsloader-runescape"
REPO_CLONE_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"

# 固定版本核心套件名稱常數
UE4SS_FIXED_KEY = "UE4SS Steam (latest) 4 3.0.1-gf6d5f942 2026-09-16T16-30Z xEKUeeFss"
UE4SS_FIXED_VER = "3.0.1-gf6d5f942"

RUNESCHEMA_FIXED_KEY = "RuneSchema (Steam) 570 0.8.0.3 2026-10-30T20-06Z AMadvv1Fj"
RUNESCHEMA_FIXED_VER = "0.8.0.3"

# RuneSchema 官方支援的資料夾載入器清單 (對應 RuneSchema/settings/settings.ini [loaders])
RUNESCHEMA_LOADERS = {
    "assets", "blueprints", "buildings", "courses", "dialogue", "effects",
    "enums", "equipment", "events", "journal", "lore", "nameplates",
    "niagara", "npc", "players", "quests", "registry", "raw", "recipes",
    "spawns", "strings", "vendors"
}

# UE4SS 內建模組與系統目錄排除清單
UE4SS_BUILTINS = {
    "shared", "custom_mod_data", "vgui", "consolescriptmod",
    "actordumpermod", "bpml_genericfunctions", "bpmodloadermod",
    "cheatmanagerenablermod", "consolecommandsmod", "consoleenablermod",
    "keybinds", "linetracemod", "splitscreenmod", "jsbluaprofilermod", "core"
}

# 壓縮檔內容清單記憶體快取: {archive_path: (mtime, size, entries_list)}
_ARCHIVE_ENTRIES_CACHE: Dict[str, Tuple[float, int, List[str]]] = {}


def get_silent_subprocess_kwargs() -> dict:
    """確保在 Windows 執行外部命令 (git / tar / 7z) 時 100% 不彈出黑窗"""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    return kwargs


# =========================================================================
# 1. 設定檔與 Steam 遊戲路徑自動偵測
# =========================================================================

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def is_valid_game_dir(path: str) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
        return (p / "RSDragonwilds.exe").exists() and (p / "RSDragonwilds").is_dir()
    except Exception:
        return False


def get_steam_path() -> Optional[str]:
    """從 Windows 登錄檔讀取 Steam 安裝路徑"""
    reg_targets = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for root_key, sub_key, val_name in reg_targets:
        try:
            with winreg.OpenKey(root_key, sub_key) as key:
                steam_path, _ = winreg.QueryValueEx(key, val_name)
                if steam_path and os.path.exists(steam_path):
                    return os.path.abspath(steam_path)
        except Exception:
            continue
    return None


def get_steam_libraries(steam_path: Optional[str]) -> List[str]:
    """解析 libraryfolders.vdf 並結合常見磁碟機 SteamLibrary 路徑"""
    libraries = []
    if steam_path and os.path.exists(steam_path):
        libraries.append(os.path.abspath(steam_path))
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                paths = re.findall(r'"path"\s+"([^"]+)"', content)
                for p in paths:
                    normalized = os.path.abspath(p.replace("\\\\", "\\"))
                    if os.path.exists(normalized) and normalized not in libraries:
                        libraries.append(normalized)
            except Exception:
                pass

    # 掃描本機所有磁碟機的常見 Steam 遊戲庫位置作為備援
    for drive_letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive_root = f"{drive_letter}:\\"
        if not os.path.exists(drive_root):
            continue
        for rel_cand in [
            "SteamLibrary",
            "Steam",
            r"Games\Steam",
            r"Program Files (x86)\Steam",
            r"Program Files\Steam",
        ]:
            cand = os.path.join(drive_root, rel_cand)
            if os.path.exists(cand) and cand not in libraries:
                libraries.append(cand)

    return libraries


def detect_game_path() -> str:
    """自動尋找 RSDragonwilds 遊戲根目錄"""
    # 1. 優先檢查使用者曾經手動指定並儲存的有效路徑
    cfg = load_config()
    saved_path = cfg.get("game_path", "")
    if is_valid_game_dir(saved_path):
        return os.path.abspath(saved_path)

    # 2. 檢查工具是否直接放在遊戲目錄內或子目錄內
    for parent in [ROOT_DIR, ROOT_DIR.parent, ROOT_DIR.parent.parent]:
        if is_valid_game_dir(str(parent)):
            return str(parent.resolve())

    # 3. 透過 Steam 登錄檔與全磁碟庫掃描
    steam_path = get_steam_path()
    libs = get_steam_libraries(steam_path)
    for lib in libs:
        cand = os.path.join(lib, "steamapps", "common", "RSDragonwilds")
        if is_valid_game_dir(cand):
            save_config({**cfg, "game_path": os.path.abspath(cand)})
            return os.path.abspath(cand)

    return saved_path if saved_path else ""


def get_mods_source_dir() -> Path:
    """取得存放待安裝壓縮檔的本地目錄 (優先使用 mods/，次選 1101mods/)"""
    mods_dir = ROOT_DIR / "mods"
    fallback_dir = ROOT_DIR / "1101mods"

    # 若 mods/ 不存在或為空，且 1101mods/ 存在，則自動將 1101mods/ 複製初始化至 mods/
    if fallback_dir.is_dir():
        os.makedirs(mods_dir, exist_ok=True)
        existing = [f for f in os.listdir(mods_dir) if f.lower().endswith((".zip", ".rar", ".7z"))]
        if not existing:
            for item in os.listdir(fallback_dir):
                src_file = fallback_dir / item
                if src_file.is_file() and item.lower().endswith((".zip", ".rar", ".7z")):
                    shutil.copy2(src_file, mods_dir / item)

    os.makedirs(mods_dir, exist_ok=True)
    return mods_dir


# =========================================================================
# 2. Git 模組庫同步 (Clone / Pull 最新壓縮檔)
# =========================================================================

def sync_mods_from_git(progress_callback: Optional[Callable[[int, str], None]] = None) -> Tuple[bool, str]:
    """
    從 GitHub (JiaSai67/modsloader-runescape) 同步最新模組壓縮檔至本地 mods/ 目錄。
    - 若當前專案為 Git 倉庫，優先執行 git fetch + git pull / checkout 更新 mods/。
    - 若當前環境非 Git 倉庫，則透過暫存區 git clone --depth 1 拉取最新 mods/ 檔案並同步回來。
    """
    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    _report(5, "正在連線至 GitHub 檢查最新模組壓縮檔...")
    kw = get_silent_subprocess_kwargs()
    mods_dir = get_mods_source_dir()

    # 檢查系統是否有 git
    if not shutil.which("git"):
        return False, "系統未安裝 Git，直接採用本地現有模組包安裝。"

    git_dir = ROOT_DIR / ".git"
    if git_dir.is_dir():
        try:
            _report(10, "正在從 Git 遠端倉庫同步最新模組包 (git fetch)...")
            res_fetch = subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                **kw
            )
            if res_fetch.returncode == 0:
                _report(15, "正在更新本地 mods/ 壓縮檔清單...")
                res_co = subprocess.run(
                    ["git", "checkout", "origin/main", "--", "mods"],
                    cwd=str(ROOT_DIR),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    **kw
                )
                if res_co.returncode == 0:
                    return True, "已從 GitHub 同步最新模組包 (git fetch)"
        except Exception:
            pass

    # 備援 1：透過 GitHub REST API 比對遠端 mods/ 清單，僅針對新增或變更的壓縮檔極速下載
    try:
        import urllib.request
        _report(12, "正在比對 GitHub 雲端 mods/ 檔案清單...")
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/mods"
        req = urllib.request.Request(api_url, headers={"User-Agent": "modsloader-runescape"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            remote_items = json.loads(resp.read().decode("utf-8"))
        if isinstance(remote_items, list):
            updated_cnt = 0
            for r_item in remote_items:
                r_name = r_item.get("name", "")
                r_size = r_item.get("size", 0)
                dl_url = r_item.get("download_url", "")
                if not r_name.lower().endswith((".zip", ".rar", ".7z")) or not dl_url:
                    continue
                local_f = mods_dir / r_name
                if not local_f.exists() or local_f.stat().st_size != r_size:
                    _report(15, f"正在從 GitHub 下載更新模組: {r_name}...")
                    dl_req = urllib.request.Request(dl_url, headers={"User-Agent": "modsloader-runescape"})
                    with urllib.request.urlopen(dl_req, timeout=30) as dl_resp:
                        with open(local_f, "wb") as out_f:
                            out_f.write(dl_resp.read())
                    updated_cnt += 1
            return True, f"已與 GitHub 雲端模組庫同步完成 (更新 {updated_cnt} 項)"
    except Exception:
        pass

    # 備援：使用臨時目錄 git clone --depth 1 同步 mods/ 資料夾
    try:
        _report(10, "正在從 GitHub 克隆最新模組壓縮檔 (git clone --depth 1)...")
        with tempfile.TemporaryDirectory(prefix="rs_git_sync_") as tmp_clone:
            res_clone = subprocess.run(
                ["git", "clone", "--depth", "1", REPO_CLONE_URL, tmp_clone],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                **kw
            )
            if res_clone.returncode == 0:
                remote_mods = Path(tmp_clone) / "mods"
                if not remote_mods.is_dir():
                    remote_mods = Path(tmp_clone) / "1101mods"
                if remote_mods.is_dir():
                    _report(16, "正在同步雲端模組壓縮檔至本地...")
                    synced = 0
                    for item in os.listdir(remote_mods):
                        src_f = remote_mods / item
                        if src_f.is_file() and item.lower().endswith((".zip", ".rar", ".7z")):
                            shutil.copy2(src_f, mods_dir / item)
                            synced += 1
                    return True, f"已從 GitHub 成功同步 {synced} 個模組壓縮檔"
    except Exception:
        pass

    return False, "離線或遠端尚未變更，使用本地模組庫進行安裝"


# =========================================================================
# 3. 壓縮檔結構解析與安裝狀態檢測
# =========================================================================

def list_archive_entries(archive_path: str) -> List[str]:
    """快速讀取壓縮檔 (.zip / .rar / .7z) 內部檔案路徑清單 (含記憶體快取)"""
    try:
        st = os.stat(archive_path)
        cache_key = os.path.abspath(archive_path)
        if cache_key in _ARCHIVE_ENTRIES_CACHE:
            c_mtime, c_size, c_entries = _ARCHIVE_ENTRIES_CACHE[cache_key]
            if c_mtime == st.st_mtime and c_size == st.st_size:
                return c_entries
    except Exception:
        return []

    ext = os.path.splitext(archive_path)[1].lower()
    entries = []
    kw = get_silent_subprocess_kwargs()

    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                entries = [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]
        except Exception:
            pass

    if not entries:
        # 使用 Windows 10/11 內建的 tar.exe (libarchive 支援 .rar / .7z / .zip)
        tar_exe = r"C:\Windows\System32\tar.exe"
        if os.path.exists(tar_exe):
            try:
                res = subprocess.run(
                    [tar_exe, "-tf", archive_path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=10, **kw
                )
                if res.returncode == 0:
                    entries = [
                        line.strip().replace("\\", "/")
                        for line in res.stdout.splitlines()
                        if line.strip() and not line.strip().endswith("/")
                    ]
            except Exception:
                pass

    if not entries:
        # 備援：嘗試 7-Zip
        for p7z in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe", "7z"]:
            if p7z == "7z" and not shutil.which("7z"):
                continue
            if p7z != "7z" and not os.path.exists(p7z):
                continue
            try:
                res = subprocess.run(
                    [p7z, "l", "-ba", archive_path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=10, **kw
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if len(line) > 53:
                            attr = line[20:25]
                            name = line[53:].strip().replace("\\", "/")
                            if "D" not in attr and name:
                                entries.append(name)
                    break
            except Exception:
                continue

    try:
        _ARCHIVE_ENTRIES_CACHE[os.path.abspath(archive_path)] = (st.st_mtime, st.st_size, entries)
    except Exception:
        pass
    return entries


def parse_nexus_filename(filename: str) -> Tuple[str, str, str]:
    """
    解析 NexusMods 壓縮檔命名格式：
    例如 'Mod Menu 2.0.2 548 2.0.2 2026-10-25T14-44Z 8qyOxxdG3.zip'
    回傳 (clean_name, mod_id, version)
    """
    base, _ = os.path.splitext(filename)
    m = re.match(r"^(.+?)\s+(\d+)\s+([^\s]+)\s+(\d{4}-\d{2}-\d{2}T[\d\-]+Z)\s+([A-Za-z0-9]+)$", base)
    if m:
        raw_title, mod_id, ver, _, _ = m.groups()
        return raw_title.strip(), mod_id, ver.strip()
    return base.strip(), "", "1.0"


def analyze_mod_archive(archive_path: str, game_path: str = "") -> Dict:
    """
    解析單一壓縮檔的模組名稱、版本、分類、目標相對路徑，並檢查是否已安裝於 game_path。
    """
    fname = os.path.basename(archive_path)
    base, _ = os.path.splitext(fname)
    raw_title, mod_id, ver = parse_nexus_filename(fname)

    info = {
        "filename": fname,
        "filepath": archive_path,
        "name": raw_title,
        "mod_id": mod_id,
        "version": ver,
        "category": "一般模組",
        "is_core": False,
        "core_type": None,
        "target_rel": "",
        "installed": False,
    }

    # 1. 檢查是否為固定雙核心之一：UE4SS 或 RuneSchema
    if base.startswith(UE4SS_FIXED_KEY) or "ue4ss steam" in base.lower():
        info.update({
            "name": "UE4SS Steam (latest)",
            "version": UE4SS_FIXED_VER if base.startswith(UE4SS_FIXED_KEY) else ver,
            "category": "核心框架",
            "is_core": True,
            "core_type": "ue4ss",
            "target_rel": "RSDragonwilds/Binaries/Win64/dwmapi.dll",
        })
        if is_valid_game_dir(game_path):
            gp = Path(game_path)
            has_dll = (gp / "RSDragonwilds" / "Binaries" / "Win64" / "dwmapi.dll").exists()
            has_ue4ss = (gp / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "UE4SS.dll").exists()
            info["installed"] = has_dll and has_ue4ss
        return info

    if base.startswith(RUNESCHEMA_FIXED_KEY) or "runeschema (steam)" in base.lower():
        info.update({
            "name": "RuneSchema (Steam)",
            "version": RUNESCHEMA_FIXED_VER if base.startswith(RUNESCHEMA_FIXED_KEY) else ver,
            "category": "核心框架",
            "is_core": True,
            "core_type": "runeschema",
            "target_rel": "RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema/dlls/main.dll",
        })
        if is_valid_game_dir(game_path):
            gp = Path(game_path)
            has_rs = (gp / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "dlls" / "main.dll").exists()
            info["installed"] = has_rs
        return info

    entries = list_archive_entries(archive_path)

    # 2. 檢查內部是否含有 RSDragonwilds/... 標準路徑
    for e in entries:
        parts = e.split("/")
        if "RSDragonwilds" in parts:
            idx = parts.index("RSDragonwilds")
            rel = "/".join(parts[idx:])
            lower_parts = [p.lower() for p in parts]
            if "/ue4ss/" in rel.lower() and ("main.lua" in rel.lower() or "enabled.txt" in rel.lower()):
                if "mods" in lower_parts:
                    m_idx = lower_parts.index("mods")
                    if m_idx + 1 < len(parts):
                        mod_folder = parts[m_idx + 1]
                        target_rel = f"RSDragonwilds/Binaries/Win64/ue4ss/Mods/{mod_folder}"
                        info.update({
                            "category": "Lua 模組",
                            "target_rel": target_rel,
                        })
                        if is_valid_game_dir(game_path):
                            info["installed"] = (Path(game_path) / target_rel).exists()
                        return info
            if rel.lower().endswith(".pak"):
                info.update({
                    "category": "Pak 模組",
                    "target_rel": rel,
                })
                if is_valid_game_dir(game_path):
                    # 同時檢查完整相對路徑或 ~mods 扁平路徑
                    gp = Path(game_path)
                    pak_flat = gp / "RSDragonwilds" / "Content" / "Paks" / "~mods" / os.path.basename(rel)
                    info["installed"] = (gp / rel).exists() or pak_flat.exists()
                return info

    # 3. 檢查是否為 RuneSchema 數據模組 (含有 assets, blueprints, raw 等載入器目錄)
    for e in entries:
        parts = e.split("/")
        for i, p in enumerate(parts[:-1]):
            if p.lower() in RUNESCHEMA_LOADERS:
                mod_folder = parts[i - 1] if i > 0 else raw_title.split()[0]
                target_rel = f"RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema/mods/{mod_folder}"
                info.update({
                    "category": "RuneSchema 模組",
                    "target_rel": target_rel,
                })
                if is_valid_game_dir(game_path):
                    info["installed"] = (Path(game_path) / target_rel).exists()
                return info

    # 4. 檢查是否為一般 Pak 模組
    for e in entries:
        if e.lower().endswith(".pak"):
            pak_name = os.path.basename(e)
            target_rel = f"RSDragonwilds/Content/Paks/~mods/{pak_name}"
            info.update({
                "category": "Pak 模組",
                "target_rel": target_rel,
            })
            if is_valid_game_dir(game_path):
                info["installed"] = (Path(game_path) / target_rel).exists()
            return info

    # 5. 檢查是否為一般 UE4SS Lua 模組
    for e in entries:
        parts = e.split("/")
        lower_parts = [p.lower() for p in parts]
        if "scripts" in lower_parts:
            s_idx = lower_parts.index("scripts")
            mod_folder = parts[s_idx - 1] if s_idx > 0 else raw_title
            target_rel = f"RSDragonwilds/Binaries/Win64/ue4ss/Mods/{mod_folder}"
            info.update({
                "category": "Lua 模組",
                "target_rel": target_rel,
            })
            if is_valid_game_dir(game_path):
                info["installed"] = (Path(game_path) / target_rel).exists()
            return info

    return info


def scan_all_mods(game_path: str = "") -> List[Dict]:
    """
    掃描本地 mods/ 資料夾內的所有壓縮檔，
    固定將 UE4SS 排在第一位、RuneSchema 排在第二位，其餘依名稱排序。
    """
    mods_dir = get_mods_source_dir()
    files = [
        f for f in sorted(os.listdir(mods_dir))
        if f.lower().endswith((".zip", ".rar", ".7z"))
    ]

    all_items = [analyze_mod_archive(str(mods_dir / f), game_path) for f in files]

    core_ue4ss = [m for m in all_items if m["core_type"] == "ue4ss"]
    core_rs = [m for m in all_items if m["core_type"] == "runeschema"]
    others = [m for m in all_items if not m["is_core"]]

    return core_ue4ss + core_rs + others


def get_overall_status(game_path: str = "") -> Dict:
    """
    回傳頂部狀態確認所需的彙整資訊：
    - game_valid: 是否找到遊戲目錄
    - ue4ss_installed / ue4ss_version
    - runeschema_installed / runeschema_version
    - total_mods (不含 2 個核心框架的擴充模組總數)
    - installed_mods (已安裝的擴充模組數)
    - items: 完整 30 項清單
    """
    items = scan_all_mods(game_path)
    game_valid = is_valid_game_dir(game_path)

    ue4ss_item = next((m for m in items if m["core_type"] == "ue4ss"), None)
    rs_item = next((m for m in items if m["core_type"] == "runeschema"), None)
    addon_items = [m for m in items if not m["is_core"]]

    ue4ss_installed = bool(ue4ss_item and ue4ss_item["installed"]) if game_valid else False
    rs_installed = bool(rs_item and rs_item["installed"]) if game_valid else False
    installed_addons = sum(1 for m in addon_items if m["installed"]) if game_valid else 0

    return {
        "game_valid": game_valid,
        "game_path": game_path,
        "ue4ss_installed": ue4ss_installed,
        "ue4ss_version": UE4SS_FIXED_VER,
        "runeschema_installed": rs_installed,
        "runeschema_version": RUNESCHEMA_FIXED_VER,
        "total_addons": len(addon_items),
        "installed_addons": installed_addons,
        "total_all": len(items),
        "installed_all": (1 if ue4ss_installed else 0) + (1 if rs_installed else 0) + installed_addons,
        "items": items,
    }


# =========================================================================
# 4. 解壓縮與四階段智慧安裝核心
# =========================================================================

def extract_archive(archive_path: str, extract_to: str) -> bool:
    """支援 .zip / .rar / .7z 解壓縮 (優先使用 Python zipfile 與 Windows 內建 tar.exe)"""
    ext = os.path.splitext(archive_path)[1].lower()
    os.makedirs(extract_to, exist_ok=True)
    kw = get_silent_subprocess_kwargs()

    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_to)
            return True
        except Exception:
            pass

    # Windows 10/11 內建 System32\tar.exe (原生支援 .rar / .7z / .zip)
    tar_exe = r"C:\Windows\System32\tar.exe"
    if os.path.exists(tar_exe):
        try:
            res = subprocess.run([tar_exe, "-xf", archive_path, "-C", extract_to], capture_output=True, timeout=30, **kw)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 7-Zip 備援
    for p7z in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe", "7z"]:
        if p7z == "7z" and not shutil.which("7z"):
            continue
        if p7z != "7z" and not os.path.exists(p7z):
            continue
        try:
            res = subprocess.run([p7z, "x", archive_path, f"-o{extract_to}", "-y"], capture_output=True, timeout=30, **kw)
            if res.returncode == 0:
                return True
        except Exception:
            continue

    # WinRAR 備援
    for prar in [r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files\WinRAR\rar.exe", "rar", "unrar"]:
        if prar in ("rar", "unrar") and not shutil.which(prar):
            continue
        if prar not in ("rar", "unrar") and not os.path.exists(prar):
            continue
        try:
            res = subprocess.run([prar, "x", "-y", archive_path, extract_to + "\\"], capture_output=True, timeout=30, **kw)
            if res.returncode == 0:
                return True
        except Exception:
            continue

    return False


def merge_folders(src: str, dst: str):
    """遞迴合併複製目錄內容"""
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            merge_folders(s, d)
        else:
            shutil.copy2(s, d)


def enable_mod_in_txt(txt_path: str, mod_name: str):
    """確保 mod_name : 1 被啟用並寫入指定的 mods.txt 或 runeschema.txt"""
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    lines = []
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            lines = []

    updated = False
    for idx, line in enumerate(lines):
        if ":" in line:
            key = line.strip().split(":", 1)[0].strip()
            if key.lower() == mod_name.lower():
                lines[idx] = f"{mod_name} : 1\n"
                updated = True
                break

    if updated:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        with open(txt_path, "a", encoding="utf-8") as f:
            if lines and not lines[-1].endswith("\n"):
                f.write("\n")
            f.write(f"{mod_name} : 1\n")


def _find_ue4_root_parent(extracted_path: str) -> Optional[str]:
    """尋找解壓目錄第 0 層或第 1 層是否含有 RSDragonwilds 資料夾"""
    if os.path.isdir(os.path.join(extracted_path, "RSDragonwilds")):
        return extracted_path
    for d in os.listdir(extracted_path):
        cand = os.path.join(extracted_path, d)
        if os.path.isdir(cand) and os.path.isdir(os.path.join(cand, "RSDragonwilds")):
            return cand
    return None


def install_single_archive(archive_path: str, game_path: str) -> Tuple[bool, str]:
    """
    智慧安裝單一模組壓縮檔至 game_path。
    """
    fname = os.path.basename(archive_path)
    base, _ = os.path.splitext(fname)

    with tempfile.TemporaryDirectory(prefix="rs_mod_ext_") as ext_dir:
        if not extract_archive(archive_path, ext_dir):
            return False, f"解壓縮失敗: {fname}"

        ue4ss_dir = os.path.join(game_path, "RSDragonwilds", "Binaries", "Win64", "ue4ss")
        ue4ss_mods_dir = os.path.join(ue4ss_dir, "Mods")
        mods_txt_path = os.path.join(ue4ss_mods_dir, "mods.txt")

        # 階段 1：檢查是否含有 RSDragonwilds 根目錄結構 (含 UE4SS、RuneSchema、ModMenu、FastTomes、LedgerRange、x50 Stacks)
        ue4_root_parent = _find_ue4_root_parent(ext_dir)
        if ue4_root_parent:
            src_rs = os.path.join(ue4_root_parent, "RSDragonwilds")
            dst_rs = os.path.join(game_path, "RSDragonwilds")

            # 若安裝的是 UE4SS 本體，先備份現有 mods.txt 中的自訂模組，避免覆蓋遺失
            existing_mods_lines = []
            is_ue4ss_core = base.startswith(UE4SS_FIXED_KEY) or "ue4ss steam" in base.lower()
            if is_ue4ss_core and os.path.exists(mods_txt_path):
                try:
                    with open(mods_txt_path, "r", encoding="utf-8", errors="ignore") as f:
                        existing_mods_lines = f.readlines()
                except Exception:
                    pass

            # 檢查此壓縮檔是否在 ue4ss/Mods (或 mods) 下新增了頂層模組資料夾
            top_lua_mods = []
            for m_dir_name in ("Mods", "mods"):
                cand_mods = os.path.join(src_rs, "Binaries", "Win64", "ue4ss", m_dir_name)
                if os.path.isdir(cand_mods):
                    for item in os.listdir(cand_mods):
                        if os.path.isdir(os.path.join(cand_mods, item)) and item.lower() not in UE4SS_BUILTINS:
                            if item not in top_lua_mods:
                                top_lua_mods.append(item)

            # 只合併 RSDragonwilds 資料夾，彻底隔絕壓縮檔外層的 Readme.txt / INSTALL.txt 污染遊戲根目錄
            merge_folders(src_rs, dst_rs)

            # 若為 UE4SS 核心，寫入版本標記並還原先前已啟用的自訂模組紀錄
            if is_ue4ss_core:
                try:
                    with open(os.path.join(ue4ss_dir, "ue4ss_version.txt"), "w", encoding="utf-8") as f:
                        f.write(UE4SS_FIXED_VER)
                except Exception:
                    pass
                for line in existing_mods_lines:
                    if ":" in line:
                        m_name, m_val = [x.strip() for x in line.split(":", 1)]
                        if m_val == "1" and m_name.lower() not in UE4SS_BUILTINS:
                            enable_mod_in_txt(mods_txt_path, m_name)

            # 為所有新合併的頂層 Lua / C++ 模組寫入 mods.txt 與 enabled.txt
            for mod_name in top_lua_mods:
                enable_mod_in_txt(mods_txt_path, mod_name)
                en_file = os.path.join(ue4ss_mods_dir, mod_name, "enabled.txt")
                if not os.path.exists(en_file):
                    try:
                        open(en_file, "w", encoding="utf-8").close()
                    except Exception:
                        pass

            return True, f"已合併安裝 {fname}"

        # 階段 2：檢查是否為 RuneSchema 數據模組 (assets / blueprints / raw 等載入器目錄)
        rs_mods_found = []
        for root, dirs, _ in os.walk(ext_dir):
            lower_dirs = {d.lower() for d in dirs}
            if lower_dirs & RUNESCHEMA_LOADERS:
                mod_name = os.path.basename(root)
                if os.path.abspath(root) == os.path.abspath(ext_dir):
                    mod_name = parse_nexus_filename(fname)[0].split()[0]
                rs_mods_found.append((mod_name, root))
                dirs[:] = []  # 不再向下遞迴

        if rs_mods_found:
            rs_target_base = os.path.join(ue4ss_mods_dir, "RuneSchema", "mods")
            rs_txt = os.path.join(rs_target_base, "runeschema.txt")
            for mod_name, mod_root in rs_mods_found:
                merge_folders(mod_root, os.path.join(rs_target_base, mod_name))
                enable_mod_in_txt(rs_txt, mod_name)
            return True, f"已安裝 RuneSchema 模組: {', '.join(m[0] for m in rs_mods_found)}"

        # 階段 3：檢查是否含有 Pak 模組檔案 (.pak, .ucas, .utoc)
        pak_files = []
        for root, _, files in os.walk(ext_dir):
            for file in files:
                if file.lower().endswith((".pak", ".ucas", ".utoc")):
                    pak_files.append(os.path.join(root, file))

        if pak_files:
            paks_mods_dir = os.path.join(game_path, "RSDragonwilds", "Content", "Paks", "~mods")
            os.makedirs(paks_mods_dir, exist_ok=True)
            for pf in pak_files:
                shutil.copy2(pf, os.path.join(paks_mods_dir, os.path.basename(pf)))

        # 階段 4：檢查是否含有 UE4SS Lua 腳本模組 (忽略大小寫比對 Scripts / main.lua / enabled.txt)
        lua_mod_folders = []
        exclude_names = UE4SS_BUILTINS | {"mods", "ue4ss", "win64", "binaries", "engine", "rsdragonwilds", "scripts"}
        for root, dirs, files in os.walk(ext_dir):
            lower_dirs = {d.lower() for d in dirs}
            lower_files = {f.lower() for f in files}
            if "scripts" in lower_dirs or "main.lua" in lower_files or "enabled.txt" in lower_files:
                mod_name = os.path.basename(root)
                if mod_name.lower() not in exclude_names:
                    if not any(root.startswith(ep + os.sep) or root == ep for _, ep in lua_mod_folders):
                        lua_mod_folders.append((mod_name, root))

        if lua_mod_folders:
            for mod_name, mod_root in lua_mod_folders:
                dst_mod_dir = os.path.join(ue4ss_mods_dir, mod_name)
                merge_folders(mod_root, dst_mod_dir)
                enable_mod_in_txt(mods_txt_path, mod_name)
                en_file = os.path.join(dst_mod_dir, "enabled.txt")
                if not os.path.exists(en_file):
                    try:
                        open(en_file, "w", encoding="utf-8").close()
                    except Exception:
                        pass

        if pak_files or lua_mod_folders:
            return True, f"已安裝 {fname}"

        return False, f"無法識別壓縮檔結構: {fname}"


def install_all_mods(
    game_path: str,
    selected_filenames: Optional[List[str]] = None,
    sync_git: bool = True,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Tuple[bool, str, int, int]:
    """
    一鍵執行完整同步與安裝流程：
    1. 從 Git 同步最新壓縮檔至本地 mods/
    2. 強制優先安裝固定版 UE4SS 與 RuneSchema
    3. 依序安裝所有勾選的擴充模組
    回傳 (success, summary_msg, installed_count, total_count)
    """
    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    if not is_valid_game_dir(game_path):
        return False, "遊戲路徑無效，請先確認 RSDragonwilds 安裝目錄！", 0, 0

    # Step 1: 同步 Git
    git_msg = ""
    if sync_git:
        _, git_msg = sync_mods_from_git(progress_callback)

    # Step 2: 掃描並排序所有壓縮檔 (確保 UE4SS 第一、RuneSchema 第二)
    all_mods = scan_all_mods(game_path)
    if not all_mods:
        return False, "mods 目錄中沒有找到任何模組壓縮檔！", 0, 0

    if selected_filenames is not None:
        selected_set = set(selected_filenames)
        # 核心框架 (UE4SS & RuneSchema) 永遠強制納入安裝以保障環境完整
        target_mods = [m for m in all_mods if m["is_core"] or m["filename"] in selected_set]
    else:
        target_mods = all_mods

    total = len(target_mods)
    success_count = 0

    # 預先清理舊版扁平 UE4SS 遺留檔案，避免與新版 ue4ss/ 子目錄結構衝突
    win64_dir = os.path.join(game_path, "RSDragonwilds", "Binaries", "Win64")
    for legacy_file in ("UE4SS.dll", "UE4SS-settings.ini", "UE4SS.log", "Changelog.md", "README.md"):
        p = os.path.join(win64_dir, legacy_file)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    for idx, mod_info in enumerate(target_mods, 1):
        pct = 20 + int((idx / max(1, total)) * 78)
        display_name = mod_info["name"]
        _report(pct, f"正在安裝 ({idx}/{total}): {display_name} (v{mod_info['version']})...")
        ok, _ = install_single_archive(mod_info["filepath"], game_path)
        if ok:
            success_count += 1

    _report(100, f"安裝完成！成功部署 {success_count}/{total} 項套件與模組。")
    summary = f"{git_msg}\n成功安裝 {success_count} / {total} 項套件與擴充模組！".strip()
    return True, summary, success_count, total


def uninstall_all_mods(game_path: str) -> Tuple[bool, str]:
    """一鍵清除遊戲目錄內的 UE4SS、RuneSchema 與所有 Pak / Lua 模組，還原純淨遊戲狀態"""
    if not is_valid_game_dir(game_path):
        return False, "遊戲路徑無效！"

    removed = []
    win64_dir = Path(game_path) / "RSDragonwilds" / "Binaries" / "Win64"
    paks_mods_dir = Path(game_path) / "RSDragonwilds" / "Content" / "Paks" / "~mods"

    dwmapi = win64_dir / "dwmapi.dll"
    if dwmapi.exists():
        try:
            dwmapi.unlink()
            removed.append("dwmapi.dll")
        except Exception as e:
            return False, f"無法移除 dwmapi.dll (請確認遊戲是否已關閉): {e}"

    ue4ss_dir = win64_dir / "ue4ss"
    if ue4ss_dir.exists():
        try:
            shutil.rmtree(ue4ss_dir)
            removed.append("ue4ss/")
        except Exception as e:
            return False, f"無法移除 ue4ss 目錄: {e}"

    if paks_mods_dir.exists():
        try:
            shutil.rmtree(paks_mods_dir)
            removed.append("Content/Paks/~mods/")
        except Exception as e:
            return False, f"無法移除 ~mods 目錄: {e}"

    if not removed:
        return True, "目前遊戲目錄已經是純淨無模組狀態。"
    return True, f"已成功清除所有模組與核心框架 ({', '.join(removed)})，遊戲已恢復純淨狀態！"
