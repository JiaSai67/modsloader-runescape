# -*- coding: utf-8 -*-
"""
MLRS (ModsLoader - RuneScapes) 模組同步、版本更新檢查與智慧安裝核心引擎 (Mod Manager Core)
支援：
1. 開啟程式自動檢查 Git 雲端版本狀態 (Commit SHA、雲端 mods/ 清單與模組版本差異比對)
2. 模組版本更新概念 (透過 mlrs_installed_versions.json 追蹤遊戲內已安裝版本 vs 本地/雲端最新版本)
3. 自動從 GitHub 儲存庫拉取 / 同步最新壓縮檔模組庫，並自動汰換同模組 ID 的舊版壓縮檔
4. 固定雙核心前置套件優先部署：
   - UE4SS = "UE4SS Steam (latest) 4 3.0.1-gf6d5f942 2026-09-16T16-30Z xEKUeeFss"
   - RuneSchema = "RuneSchema (Steam) 570 0.8.0.3 2026-10-30T20-06Z AMadvv1Fj"
5. 四階段智慧模組結構識別與安裝：
   - 根目錄直通型 / 單層外殼包裝型 (RSDragonwilds/...)
   - RuneSchema 數據載入器型 (assets, blueprints, raw, recipes 等 JSON 模組 -> ue4ss/Mods/RuneSchema/mods/)
   - Unreal Engine 5.6 Pak 資源模組 (.pak, .ucas, .utoc -> Content/Paks/~mods/)
   - UE4SS Lua 腳本模組 (Scripts/main.lua, enabled.txt -> ue4ss/Mods/ 並寫入 mods.txt)
"""

import os
import re
import sys
import json
import time
import shutil
import zipfile
import winreg
import tempfile
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Callable

# 專案根目錄與設定檔
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

# 遊戲目錄內的模組版本追蹤帳本相對路徑
INSTALLED_LEDGER_REL = os.path.join("RSDragonwilds", "Binaries", "Win64", "ue4ss", "mlrs_installed_versions.json")

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

# 雲端 Git 模組版本快取: {mod_key: {"filename": str, "version": str, "size": int, "sha": str, "name": str, "mod_id": str}}
_REMOTE_MODS_CACHE: Dict[str, Dict] = {}

# 最近一次 Git 狀態檢查結果快取
_LAST_GIT_STATUS: Dict = {
    "checked": False,
    "online": False,
    "git_up_to_date": True,
    "local_commit": "",
    "remote_commit": "",
    "remote_commit_msg": "",
    "remote_app_version": "",
    "git_updates_count": 0,
    "git_new_count": 0,
    "game_updates_count": 0,
    "total_pending_updates": 0,
    "badge_text": "🔄 檢查 Git 版本中...",
    "badge_state": "muted",
    "summary_title": "🔍 正在檢查 Git 雲端版本與模組更新狀態...",
    "summary_detail": "正在連線至 GitHub (JiaSai67/modsloader-runescape) 比對最新模組版本...",
}


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
# 2. 模組識別鍵、已安裝版本帳本與 Git 雲端版本檢查
# =========================================================================

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
        clean_title = raw_title.strip()
        # 若標題末尾重複附帶了版本號 (例如 'Mod Menu 2.0.2' 且 ver='2.0.2')，移除尾端版本號使模組名稱更乾淨
        if clean_title.endswith(" " + ver.strip()):
            clean_title = clean_title[: -(len(ver.strip()) + 1)].strip()
        return clean_title, mod_id, ver.strip()
    return base.strip(), "", "1.0"


def get_mod_identity_key(filename: str) -> str:
    """
    根據壓縮檔名稱計算模組的唯一身份識別鍵 (Mod Identity Key)，
    讓同一個模組在不同版本壓縮檔之間能夠正確對應並比對版本高低。
    """
    base, _ = os.path.splitext(filename)
    if base.startswith(UE4SS_FIXED_KEY) or "ue4ss steam" in base.lower():
        return "core:ue4ss"
    if base.startswith(RUNESCHEMA_FIXED_KEY) or "runeschema (steam)" in base.lower():
        return "core:runeschema"

    clean_name, mod_id, _ = parse_nexus_filename(filename)
    if mod_id:
        return f"nexus:{mod_id}"
    norm_name = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
    return f"name:{norm_name}"


def load_installed_versions(game_path: str) -> Dict[str, Dict]:
    """讀取遊戲目錄內的 mlrs_installed_versions.json 已安裝模組版本帳本"""
    if not is_valid_game_dir(game_path):
        return {}
    ledger_path = os.path.join(game_path, INSTALLED_LEDGER_REL)
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_installed_version_entry(game_path: str, mod_info: Dict):
    """將單一已安裝模組的版本資訊寫入遊戲目錄的 mlrs_installed_versions.json"""
    if not is_valid_game_dir(game_path):
        return
    ledger_path = os.path.join(game_path, INSTALLED_LEDGER_REL)
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    data = load_installed_versions(game_path)
    mod_key = mod_info.get("mod_key") or get_mod_identity_key(mod_info.get("filename", ""))
    data[mod_key] = {
        "name": mod_info.get("name", ""),
        "mod_id": mod_info.get("mod_id", ""),
        "version": mod_info.get("version", ""),
        "filename": mod_info.get("filename", ""),
        "target_rel": mod_info.get("target_rel", ""),
        "installed_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_local_git_commit() -> str:
    """讀取本地 .git 記錄的最新 Commit SHA (前 7 碼)"""
    head_ref = ROOT_DIR / ".git" / "refs" / "heads" / "main"
    if head_ref.exists():
        try:
            sha = head_ref.read_text(encoding="utf-8", errors="ignore").strip()
            if len(sha) >= 7:
                return sha[:7]
        except Exception:
            pass

    cfg = load_config()
    saved_sha = cfg.get("last_synced_commit", "")
    if len(saved_sha) >= 7:
        return saved_sha[:7]
    return ""


def _update_local_git_commit_ref(full_sha: str):
    """同步更新本地 .git/refs/heads/main 與 config.json 的 Commit SHA 記錄"""
    if not full_sha:
        return
    try:
        for rel in (".git/refs/heads/main", ".git/refs/remotes/origin/main"):
            p = ROOT_DIR / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((full_sha.strip() + "\n").encode("utf-8"))
    except Exception:
        pass
    cfg = load_config()
    cfg["last_synced_commit"] = full_sha.strip()
    cfg["last_git_check_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_config(cfg)


def get_last_git_status() -> Dict:
    """回傳最近一次 Git 版本檢查的快取結果"""
    return dict(_LAST_GIT_STATUS)


def check_git_version_status(game_path: str = "") -> Dict:
    """
    開啟 MLRS 時自動執行：檢查 GitHub 遠端倉庫 (JiaSai67/modsloader-runescape) 版本狀態與模組更新狀況。
    比對三個維度：
    1. Git 遠端最新 Commit SHA vs 本地 Commit SHA
    2. Git 遠端 mods/ 壓縮檔版本與大小 vs 本地 mods/ 壓縮檔
    3. 本地 / 雲端最新模組版本 vs 遊戲目錄內已安裝的模組版本
    """
    global _REMOTE_MODS_CACHE, _LAST_GIT_STATUS

    local_sha = get_local_git_commit()
    remote_sha = ""
    remote_full_sha = ""
    remote_msg = ""
    remote_app_ver = ""
    online = False

    headers = {
        "User-Agent": "MLRS-ModsLoader-RuneScapes/1.0.0",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. 查詢遠端 main 分支最新 Commit
    try:
        commit_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
        req = urllib.request.Request(commit_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            c_data = json.loads(resp.read().decode("utf-8"))
            remote_full_sha = c_data.get("sha", "")
            remote_sha = remote_full_sha[:7] if remote_full_sha else ""
            raw_msg = c_data.get("commit", {}).get("message", "")
            remote_msg = raw_msg.splitlines()[0].strip() if raw_msg else ""
            online = bool(remote_sha)
    except Exception:
        pass

    # 備援：若 GitHub API 連線受限，嘗試透過 git ls-remote 取得遠端 Commit SHA
    if not online and shutil.which("git"):
        try:
            kw = get_silent_subprocess_kwargs()
            res = subprocess.run(
                ["git", "ls-remote", REPO_CLONE_URL, "refs/heads/main"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, **kw
            )
            if res.returncode == 0 and res.stdout.strip():
                remote_full_sha = res.stdout.strip().split()[0]
                remote_sha = remote_full_sha[:7]
                online = True
        except Exception:
            pass

    # 2. 查詢遠端 mods/ 資料夾內的所有模組壓縮檔版本清單
    remote_mods_map: Dict[str, Dict] = {}
    if online:
        try:
            mods_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/mods"
            req = urllib.request.Request(mods_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                r_items = json.loads(resp.read().decode("utf-8"))
            if isinstance(r_items, list):
                for item in r_items:
                    r_fname = item.get("name", "")
                    if not r_fname.lower().endswith((".zip", ".rar", ".7z")):
                        continue
                    r_key = get_mod_identity_key(r_fname)
                    clean_name, mod_id, r_ver = parse_nexus_filename(r_fname)
                    if r_key == "core:ue4ss":
                        clean_name = "UE4SS Steam (latest)"
                        r_ver = UE4SS_FIXED_VER if r_fname.startswith(UE4SS_FIXED_KEY) else r_ver
                    elif r_key == "core:runeschema":
                        clean_name = "RuneSchema (Steam)"
                        r_ver = RUNESCHEMA_FIXED_VER if r_fname.startswith(RUNESCHEMA_FIXED_KEY) else r_ver

                    remote_mods_map[r_key] = {
                        "mod_key": r_key,
                        "filename": r_fname,
                        "name": clean_name,
                        "mod_id": mod_id,
                        "version": r_ver,
                        "size": item.get("size", 0),
                        "sha": item.get("sha", ""),
                        "download_url": item.get("download_url", ""),
                    }
                _REMOTE_MODS_CACHE = remote_mods_map
        except Exception:
            pass

    # 3. 比對本地 mods/ 與遠端 Git 差異
    mods_dir = get_mods_source_dir()
    local_files = [
        f for f in os.listdir(mods_dir)
        if f.lower().endswith((".zip", ".rar", ".7z"))
    ]
    local_mods_map: Dict[str, Tuple[str, str, int]] = {}
    for lf in local_files:
        l_key = get_mod_identity_key(lf)
        _, _, l_ver = parse_nexus_filename(lf)
        if l_key == "core:ue4ss" and lf.startswith(UE4SS_FIXED_KEY):
            l_ver = UE4SS_FIXED_VER
        elif l_key == "core:runeschema" and lf.startswith(RUNESCHEMA_FIXED_KEY):
            l_ver = RUNESCHEMA_FIXED_VER
        l_size = (mods_dir / lf).stat().st_size if (mods_dir / lf).exists() else 0
        local_mods_map[l_key] = (lf, l_ver, l_size)

    git_updates_count = 0
    git_new_count = 0
    if remote_mods_map:
        for r_key, r_info in remote_mods_map.items():
            if r_key not in local_mods_map:
                git_new_count += 1
            else:
                l_fname, l_ver, l_size = local_mods_map[r_key]
                if l_fname != r_info["filename"] or l_size != r_info["size"] or l_ver != r_info["version"]:
                    git_updates_count += 1

    # 若本地尚未紀錄 commit SHA，且遠端所有 mods 檔案與本地完全一致，自動對齊 local_sha
    if online and not local_sha and git_updates_count == 0 and git_new_count == 0 and remote_full_sha:
        _update_local_git_commit_ref(remote_full_sha)
        local_sha = remote_sha

    # 4. 掃描遊戲目錄內已安裝模組是否有版本更新
    scanned_items = scan_all_mods(game_path)
    game_updates_count = sum(1 for m in scanned_items if m.get("has_update", False))

    git_up_to_date = (git_updates_count == 0 and git_new_count == 0)
    if online and local_sha and remote_sha and local_sha != remote_sha and not remote_mods_map:
        git_up_to_date = False

    total_pending = git_updates_count + git_new_count + game_updates_count

    if not online:
        badge_text = "⚪ Git 離線 (本地模組庫)"
        badge_state = "muted"
        summary_title = "📦 離線模式：使用本地模組庫就緒"
        summary_detail = "無法連線至 GitHub 檢查遠端狀態，可直接安裝本地現有的 30 項核心與擴充模組。"
    elif total_pending > 0:
        parts = []
        if git_updates_count > 0 or git_new_count > 0:
            parts.append(f"雲端 Git 有 {git_updates_count + git_new_count} 項模組更新")
        if game_updates_count > 0:
            parts.append(f"遊戲內有 {game_updates_count} 項模組可升級新版本")
        detail_str = "、".join(parts)
        badge_text = f"🟡 發現更新 ({total_pending} 項可更新)"
        badge_state = "warning"
        summary_title = f"🔔 發現模組版本更新！({detail_str})"
        summary_detail = f"遠端最新 Commit: {remote_sha} | 點擊右側「一鍵更新並同步模組」即可拉取最新壓縮檔並升級！"
    else:
        badge_text = f"🟢 Git 已是最新 ({remote_sha})"
        badge_state = "success"
        summary_title = f"☁️ Git 雲端模組庫已同步最新 (Commit: {remote_sha})"
        summary_detail = "經檢查 GitHub 遠端與本地模組版本完全一致，固定版 UE4SS、RuneSchema 與擴充模組均為最新狀態。"

    _LAST_GIT_STATUS = {
        "checked": True,
        "online": online,
        "git_up_to_date": git_up_to_date,
        "local_commit": local_sha or remote_sha,
        "remote_commit": remote_sha,
        "remote_commit_msg": remote_msg,
        "remote_app_version": remote_app_ver,
        "git_updates_count": git_updates_count,
        "git_new_count": git_new_count,
        "game_updates_count": game_updates_count,
        "total_pending_updates": total_pending,
        "badge_text": badge_text,
        "badge_state": badge_state,
        "summary_title": summary_title,
        "summary_detail": summary_detail,
    }
    return dict(_LAST_GIT_STATUS)


# =========================================================================
# 3. Git 模組庫同步 (Clone / Pull 最新壓縮檔 + 舊版壓縮檔自動汰換)
# =========================================================================

def _cleanup_outdated_local_archives(mods_dir: Path, new_filename: str):
    """
    當下載或同步了新版模組壓縮檔 (new_filename) 時，
    自動移除本地 mods/ 中屬於同一個 mod_key (相同 Nexus mod_id) 的舊版壓縮檔，避免新舊並存。
    """
    target_key = get_mod_identity_key(new_filename)
    for f in os.listdir(mods_dir):
        if f == new_filename or not f.lower().endswith((".zip", ".rar", ".7z")):
            continue
        if get_mod_identity_key(f) == target_key:
            try:
                (mods_dir / f).unlink()
            except Exception:
                pass


def sync_mods_from_git(progress_callback: Optional[Callable[[int, str], None]] = None) -> Tuple[bool, str]:
    """
    從 GitHub (JiaSai67/modsloader-runescape) 同步最新模組壓縮檔至本地 mods/ 目錄。
    - 優先透過 GitHub REST API 智慧比對遠端 mods/ 清單，僅下載有更新或新增的壓縮檔，並自動淘汰同模組舊版檔案。
    - 備援使用 git fetch / checkout 或暫存區 git clone --depth 1。
    """
    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    _report(5, "正在連線至 GitHub 檢查最新模組壓縮檔與版本狀態...")
    kw = get_silent_subprocess_kwargs()
    mods_dir = get_mods_source_dir()

    headers = {
        "User-Agent": "MLRS-ModsLoader-RuneScapes/1.0.0",
        "Accept": "application/vnd.github.v3+json",
    }

    # 途徑 1：透過 GitHub REST API 精準比對遠端 mods/ 清單與版本，極速增量同步
    try:
        _report(10, "正在比對 GitHub 雲端 mods/ 模組版本清單...")
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/mods"
        req = urllib.request.Request(api_url, headers=headers)
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
                    _report(14, f"正在從 GitHub 下載更新模組: {r_name}...")
                    dl_req = urllib.request.Request(dl_url, headers={"User-Agent": "MLRS-ModsLoader-RuneScapes/1.0.0"})
                    with urllib.request.urlopen(dl_req, timeout=30) as dl_resp:
                        with open(local_f, "wb") as out_f:
                            out_f.write(dl_resp.read())
                    _cleanup_outdated_local_archives(mods_dir, r_name)
                    updated_cnt += 1

            # 同步更新本地記錄的遠端 Commit SHA
            try:
                commit_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
                c_req = urllib.request.Request(commit_url, headers=headers)
                with urllib.request.urlopen(c_req, timeout=8) as c_resp:
                    c_data = json.loads(c_resp.read().decode("utf-8"))
                    if c_data.get("sha"):
                        _update_local_git_commit_ref(c_data["sha"])
            except Exception:
                pass

            if updated_cnt > 0:
                return True, f"已從 GitHub 雲端更新 {updated_cnt} 項新版模組壓縮檔"
            return True, "GitHub 雲端模組版本檢查完畢 (本地已是最新版本)"
    except Exception:
        pass

    # 途徑 2：若系統有安裝 Git，嘗試 git fetch / clone
    if not shutil.which("git"):
        return False, "離線模式，直接採用本地現有模組包安裝。"

    git_dir = ROOT_DIR / ".git"
    if git_dir.is_dir():
        try:
            _report(12, "正在從 Git 遠端倉庫同步最新模組包 (git fetch)...")
            res_fetch = subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(ROOT_DIR),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, **kw
            )
            if res_fetch.returncode == 0:
                _report(16, "正在更新本地 mods/ 壓縮檔清單...")
                res_co = subprocess.run(
                    ["git", "checkout", "origin/main", "--", "mods"],
                    cwd=str(ROOT_DIR),
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=20, **kw
                )
                if res_co.returncode == 0:
                    return True, "已從 GitHub 同步最新模組包 (git fetch)"
        except Exception:
            pass

    # 途徑 3：使用臨時目錄 git clone --depth 1 同步 mods/ 資料夾
    try:
        _report(12, "正在從 GitHub 克隆最新模組壓縮檔 (git clone --depth 1)...")
        with tempfile.TemporaryDirectory(prefix="rs_git_sync_") as tmp_clone:
            res_clone = subprocess.run(
                ["git", "clone", "--depth", "1", REPO_CLONE_URL, tmp_clone],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=45, **kw
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
                            _cleanup_outdated_local_archives(mods_dir, item)
                            synced += 1
                    return True, f"已從 GitHub 成功同步 {synced} 個模組壓縮檔"
    except Exception:
        pass

    return False, "離線或遠端尚未變更，使用本地模組庫進行安裝"


# =========================================================================
# 4. 壓縮檔結構解析與模組版本狀態檢測
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


def _enrich_version_status(info: Dict, game_path: str, ledger: Dict[str, Dict]) -> Dict:
    """
    為單一模組補充版本比對資訊：
    - installed_version: 遊戲內目前已安裝的版本號
    - remote_version: GitHub 雲端最新版本號
    - has_update: 是否有新版本可更新 (遊戲內版本落後於本地或雲端壓縮檔，或本地壓縮檔落後於雲端)
    - status_text / status_state: UI 顯示用狀態文字與語意顏色鍵值
    """
    mod_key = info["mod_key"]
    local_ver = info["version"]
    installed = info["installed"]

    # 1. 取得遊戲內已安裝的版本號
    ledger_entry = ledger.get(mod_key, {})
    installed_ver = ledger_entry.get("version", "")

    if installed and not installed_ver:
        # 若為 UE4SS 核心，優先檢查 ue4ss_version.txt
        if info["core_type"] == "ue4ss" and is_valid_game_dir(game_path):
            ver_txt = Path(game_path) / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "ue4ss_version.txt"
            if ver_txt.exists():
                try:
                    installed_ver = ver_txt.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    pass
        if not installed_ver:
            installed_ver = local_ver

    # 2. 取得雲端 Git 的版本資訊 (若已執行過雲端檢查)
    remote_entry = _REMOTE_MODS_CACHE.get(mod_key, {})
    remote_ver = remote_entry.get("version", "")
    remote_fname = remote_entry.get("filename", "")
    remote_size = remote_entry.get("size", 0)

    local_size = 0
    try:
        if os.path.exists(info["filepath"]):
            local_size = os.stat(info["filepath"]).st_size
    except Exception:
        pass

    remote_has_update = False
    if remote_entry:
        if remote_ver and remote_ver != local_ver:
            remote_has_update = True
        elif remote_fname and remote_fname != info["filename"]:
            remote_has_update = True
        elif remote_size and local_size and remote_size != local_size:
            remote_has_update = True

    latest_ver = remote_ver if (remote_has_update and remote_ver) else local_ver
    has_game_update = bool(installed and installed_ver and installed_ver != latest_ver)
    has_update = has_game_update or remote_has_update

    info["installed_version"] = installed_ver if installed else ""
    info["remote_version"] = remote_ver or local_ver
    info["latest_version"] = latest_ver
    info["remote_has_update"] = remote_has_update
    info["has_update"] = has_update

    if has_game_update:
        info["status_text"] = f"🟡 可更新 (v{installed_ver} → v{latest_ver})"
        info["status_state"] = "warning"
    elif remote_has_update:
        info["status_text"] = f"🟡 雲端新版 (v{local_ver} → v{latest_ver})"
        info["status_state"] = "warning"
    elif installed:
        info["status_text"] = f"🟢 已安裝 (v{installed_ver})"
        info["status_state"] = "success"
    else:
        info["status_text"] = "⚪ 未安裝"
        info["status_state"] = "error"

    return info


def analyze_mod_archive(archive_path: str, game_path: str = "", ledger: Optional[Dict[str, Dict]] = None) -> Dict:
    """
    解析單一壓縮檔的模組名稱、版本、分類、目標相對路徑，並檢查在 game_path 的安裝與版本更新狀態。
    """
    fname = os.path.basename(archive_path)
    base, _ = os.path.splitext(fname)
    raw_title, mod_id, ver = parse_nexus_filename(fname)
    mod_key = get_mod_identity_key(fname)

    if ledger is None:
        ledger = load_installed_versions(game_path)

    info = {
        "mod_key": mod_key,
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
        "installed_version": "",
        "latest_version": ver,
        "has_update": False,
        "status_text": "⚪ 未安裝",
        "status_state": "error",
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
        return _enrich_version_status(info, game_path, ledger)

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
        return _enrich_version_status(info, game_path, ledger)

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
                        return _enrich_version_status(info, game_path, ledger)
            if rel.lower().endswith(".pak"):
                info.update({
                    "category": "Pak 模組",
                    "target_rel": rel,
                })
                if is_valid_game_dir(game_path):
                    gp = Path(game_path)
                    pak_flat = gp / "RSDragonwilds" / "Content" / "Paks" / "~mods" / os.path.basename(rel)
                    info["installed"] = (gp / rel).exists() or pak_flat.exists()
                return _enrich_version_status(info, game_path, ledger)

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
                return _enrich_version_status(info, game_path, ledger)

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
            return _enrich_version_status(info, game_path, ledger)

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
            return _enrich_version_status(info, game_path, ledger)

    return _enrich_version_status(info, game_path, ledger)


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

    ledger = load_installed_versions(game_path)
    all_items = [analyze_mod_archive(str(mods_dir / f), game_path, ledger=ledger) for f in files]

    core_ue4ss = [m for m in all_items if m["core_type"] == "ue4ss"]
    core_rs = [m for m in all_items if m["core_type"] == "runeschema"]
    others = [m for m in all_items if not m["is_core"]]

    return core_ue4ss + core_rs + others


def get_overall_status(game_path: str = "") -> Dict:
    """
    回傳頂部狀態確認所需的彙整資訊：
    - game_valid: 是否找到遊戲目錄
    - ue4ss_installed / ue4ss_version / ue4ss_has_update
    - runeschema_installed / runeschema_version / runeschema_has_update
    - total_addons (不含 2 個核心框架的擴充模組總數)
    - installed_addons (已安裝的擴充模組數)
    - updatable_addons (有新版本可更新的擴充模組數)
    - git_status: 最近一次 Git 雲端狀態檢查結果
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
    updatable_addons = sum(1 for m in addon_items if m.get("has_update", False))
    updatable_all = sum(1 for m in items if m.get("has_update", False))

    return {
        "game_valid": game_valid,
        "game_path": game_path,
        "ue4ss_installed": ue4ss_installed,
        "ue4ss_version": UE4SS_FIXED_VER,
        "ue4ss_has_update": bool(ue4ss_item and ue4ss_item.get("has_update", False)),
        "runeschema_installed": rs_installed,
        "runeschema_version": RUNESCHEMA_FIXED_VER,
        "runeschema_has_update": bool(rs_item and rs_item.get("has_update", False)),
        "total_addons": len(addon_items),
        "installed_addons": installed_addons,
        "updatable_addons": updatable_addons,
        "updatable_all": updatable_all,
        "total_all": len(items),
        "installed_all": (1 if ue4ss_installed else 0) + (1 if rs_installed else 0) + installed_addons,
        "git_status": get_last_git_status(),
        "items": items,
    }


# =========================================================================
# 5. 解壓縮與四階段智慧安裝核心
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


def install_single_archive(archive_path: str, game_path: str, mod_info: Optional[Dict] = None) -> Tuple[bool, str]:
    """
    智慧安裝單一模組壓縮檔至 game_path，並在成功後將模組版本記錄至 mlrs_installed_versions.json。
    """
    fname = os.path.basename(archive_path)
    base, _ = os.path.splitext(fname)
    if mod_info is None:
        mod_info = analyze_mod_archive(archive_path, game_path)

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

            # 只合併 RSDragonwilds 資料夾，徹底隔絕壓縮檔外層的 Readme.txt / INSTALL.txt 污染遊戲根目錄
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

            save_installed_version_entry(game_path, mod_info)
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
            save_installed_version_entry(game_path, mod_info)
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
            save_installed_version_entry(game_path, mod_info)
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
    3. 依序安裝所有勾選的擴充模組並寫入版本帳本
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
        ok, _ = install_single_archive(mod_info["filepath"], game_path, mod_info=mod_info)
        if ok:
            success_count += 1

    # 安裝完成後更新 Git 狀態快取
    try:
        check_git_version_status(game_path)
    except Exception:
        pass

    _report(100, f"安裝完成！成功部署 {success_count}/{total} 項套件與模組。")
    summary = f"{git_msg}\n成功安裝與更新 {success_count} / {total} 項套件與擴充模組！".strip()
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
