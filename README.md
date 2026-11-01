# modsloader - runescape (v2.0.0)

**RuneScape: Dragonwilds 現代化極簡 Git 模組同步安裝器**

專為《RuneScape: Dragonwilds》打造的極簡化一鍵模組同步與安裝工具，符合 `AIToolLauncher` 標準規範。

## ✨ 核心特色

- **極簡化 Fluent 介面**：僅保留最關鍵的「四格狀態確認」、「一鍵同步並安裝按鈕」與「可展開 / 收合的詳細模組清單」，支援 Windows 11 深色 / 淺色主題自動適配。
- **Git 雲端壓縮檔直裝 (方案 B)**：所有模組壓縮檔（`.zip` / `.rar`）原封不動存放於 Git 倉庫的 `mods/` 目錄，工具點擊安裝時自動同步並解壓部署。
- **雙核心固定版本優先部署**：
  1. **UE4SS Steam (latest)**：`v3.0.1-gf6d5f942` (`UE4SS Steam (latest) 4 3.0.1-gf6d5f942 2026-09-16T16-30Z xEKUeeFss`)
  2. **RuneSchema (Steam)**：`v0.8.0.3` (`RuneSchema (Steam) 570 0.8.0.3 2026-10-30T20-06Z AMadvv1Fj`)
- **四階段智慧模組識別引擎**：
  - 自動識別含外層包裝目錄的 `RSDragonwilds` 結構（避免破壞 `RuneSchema` 內建插件 Pak）。
  - 自動識別 `RuneSchema` JSON 數據模組（如 `BuffDuration10x`、`Extended Enemy Drops`）並安裝至 `ue4ss/Mods/RuneSchema/mods/`。
  - 自動分類安裝 `.pak/.ucas/.utoc` 模組至 `Content/Paks/~mods/`。
  - 自動安裝 UE4SS Lua 模組至 `ue4ss/Mods/` 並同步寫入 `mods.txt` 與 `enabled.txt`。
