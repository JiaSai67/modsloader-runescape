# MLRS (ModsLoader - RuneScapes) v1.0.0

**RuneScape: Dragonwilds** 現代化極簡 Git 雲端模組同步、版本更新檢查與一鍵安裝器（符合 AI Tool Standard 規範）。

## 核心功能
- **開啟自動檢查 Git 版本狀況**：啟動程式時於背景非阻塞檢查 GitHub 遠端儲存庫 (`JiaSai67/modsloader-runescape`) 最新 Commit SHA 與雲端 `mods/` 模組版本清單。
- **模組版本更新追蹤機制**：透過 `mlrs_installed_versions.json` 記錄遊戲目錄內已安裝的各模組版本，自動比對雲端與本地最新壓縮檔版本，於介面標示 `🟡 可更新 (v舊 → v新)`，並於同步時自動淘汰舊版壓縮檔。
- **固定雙核心優先部署**：
  - `UE4SS Steam (latest)` (`v3.0.1-gf6d5f942`)
  - `RuneSchema (Steam)` (`v0.8.0.3`)
- **四階段智慧模組安裝引擎**：
  1. `RSDragonwilds` 根目錄結構直通合併（自動過濾外部說明檔，並保留既有 `mods.txt` 設定）
  2. `RuneSchema` 數據載入器模組（`assets`, `blueprints`, `raw` 等自動部署至 `ue4ss/Mods/RuneSchema/mods/` 並寫入 `runeschema.txt`）
  3. Unreal Engine 5.6 `Pak` 資源模組（自動部署 `.pak` / `.ucas` / `.utoc` 至 `RSDragonwilds/Content/Paks/~mods/`）
  4. `UE4SS` Lua 腳本模組（自動部署至 `ue4ss/Mods/<ModName>/`，建立 `enabled.txt` 並啟用於 `mods.txt`）
- **極簡 Fluent 介面**：支援系統深淺色主題自動適配、4 宮格狀態確認卡片與可展開/收合的 30 項分類樹狀模組清單。

## 啟動方式
```bash
python main.py
```
