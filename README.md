# MLRS (ModsLoader - RuneScapes) v1.0.2

**RuneScape: Dragonwilds** 現代化極簡 Git 雲端模組同步、版本更新檢查、全模組零衝突・零輪詢優化與遊戲內文本漢化安裝器（符合 AI Tool Standard 規範）。

## 核心功能
- **開啟自動檢查 Git 版本狀況**：啟動程式時於背景非阻塞檢查 GitHub 遠端儲存庫 (`JiaSai67/modsloader-runescape`) 最新 Commit SHA、雲端 `mods/` 模組版本清單與已下架衝突模組殘留狀態。
- **模組版本更新追蹤與自動淘汰清理**：透過 `mlrs_installed_versions.json` 記錄遊戲目錄內已安裝的各模組版本，自動比對雲端與本地最新壓縮檔版本，於介面標示 `🟡 可更新 (v舊 → v新)`；一鍵同步時自動淘汰下架的衝突/冗餘模組（如 `LedgerRange`、`NoEatingDelay`、`RSDSFreedom`）並清理遊戲目錄殘留。
- **精選 27 項零衝突・零輪詢模組顯示清單與即時篩選**：開啟 MLRS 即預設展開全 27 項模組（2 項核心框架 + 25 項擴充模組），全面移除背景高頻輪詢計時器（改為事件驅動零卡頓架構），提供繁體中文譯名、英文原名、完整功能效果說明、關鍵字搜尋與 4 大分類快速篩選按鈕。
- **遊戲內模組介面與設定選單繁體中文化 (`🌐`)**：一鍵安裝時自動將 `Mod Menu`、`Station Feeder`、`Stashlink`、`QuickStack`、`Greater Farming`、`Don't Replant`、`Fast Eating and Sleeping`、`Farm Yield`、`Home Teleport No Cooldown`、`RuneSchema` 等模組的 `modmenu.json` / `modmenu.txt` 設定選單與遊戲內 UMG 介面文字全面轉換為繁體中文。
- **固定雙核心優先部署**：
  - `UE4SS Steam (latest)` (`v3.0.1-gf6d5f942`)
  - `RuneSchema (Steam)` (`v0.8.0.3`)
- **四階段智慧模組安裝引擎**：
  1. `RSDragonwilds` 根目錄結構直通合併（自動過濾外部說明檔，並保留既有 `mods.txt` 設定）
  2. `RuneSchema` 數據載入器模組（`assets`, `blueprints`, `raw` 等自動部署至 `ue4ss/Mods/RuneSchema/mods/` 並寫入 `runeschema.txt`）
  3. Unreal Engine 5.6 `Pak` 資源模組（自動部署 `.pak` / `.ucas` / `.utoc` 至 `RSDragonwilds/Content/Paks/~mods/`）
  4. `UE4SS` Lua 腳本模組（自動部署至 `ue4ss/Mods/<ModName>/`，建立 `enabled.txt` 並啟用於 `mods.txt`）

## 精選 27 項零衝突・零輪詢模組繁體中文圖鑑清單

| # | 分類 | 繁體中文名稱 | 英文原名 | 版本 | 遊戲內漢化 | 功能與效果說明 |
|---|---|---|---|:---:|:---:|---|
| 1 | 核心框架 | UE4SS 核心腳本與藍圖載入器 | `UE4SS Steam (latest)` | `3.0.1-gf6d5f942` | — | 所有 Lua 腳本與藍圖模組必備的核心底層載入器，提供遊戲執行期 Hook 與 UMG 介面繪製支援。 |
| 2 | 核心框架 | RuneSchema 數據與資產擴充框架 | `RuneSchema (Steam)` | `0.8.0.3` | 🌐 | 支援動態載入 JSON 格式的遊戲資料表（掉落表、Buff 時間、配方與藍圖參數），內建 Helpy 工具與存檔清理設定。 |
| 3 | RuneSchema 模組 | 增益狀態時間 10 倍延長 | `BuffDuration10x` | `1` | — | 將所有藥水、料理食物與技能附魔的增益狀態（Buff）持續時間延長為原本的 10 倍。 |
| 4 | RuneSchema 模組 | 敵人與寶箱掉落物全面擴充 | `Extended Enemy Drops` | `2.1` | — | 擴充各類怪物、鳥巢與世界寶箱的戰利品掉落表，提高稀有素材、符文精華與專屬武器的掉落機率與數量。 |
| 5 | Lua 模組 | 多人連線儲物箱超遠距連動 | `ChestLink Multiplayer PC` | `0.2.1` | — | 將多人連線與單人模式的已連結儲物箱建造與製作讀取範圍擴展至 1,000 公里（事件驅動零輪詢不卡頓；按 F7 可手動重整快取）。 |
| 6 | Lua 模組 | 農作收成自動免費重播種 | `Don't Replant` | `2` | 🌐 | 農作物收成後自動於原農地免費重新播種（不消耗種子），保留完整產量與農耕經驗值，單次堆肥可維持 2 次收成。 |
| 7 | Lua 模組 | 農作物收成產量倍增 | `FarmYield` | `1` | 🌐 | 將農地作物的收成產量預設提升為 3 倍（可透過遊戲內 Mod Menu 自由調整 1x 至 10x 收成倍率）。 |
| 8 | Lua 模組 | 快速進食飲水與秒睡過夜 | `Fast Eating and Sleeping` | `1.1.0` | 🌐 | 移除進食、飲水與喝藥水之間的 2 秒冷卻等待；夜晚睡眠過夜縮短至 0.5 秒完成，白天躺床小憩恢復體力速度提升為 3 倍。 |
| 9 | Lua 模組 | 技能經驗典籍無延遲秒讀 | `Fast Tomes` | `1.0.0` | — | 移除閱讀經驗值技能典籍（Skill Tomes）之間的 2 秒使用延遲，可連續快速閱讀全部 28 種技能書。 |
| 10 | Lua 模組 | 磁石地圖好友快速傳送 | `Friend Fast Travel` | `1.0.1` | — | 站在已啟用的磁石（Lodestone）旁開啟地圖時，可直接點擊隊友或好友標記並消耗法則符文瞬間傳送至好友身邊。 |
| 11 | Lua 模組 | 全能農耕與探索法術強化 | `Greater Farming` | `2.1.2` | 🌐 | 擴大堆肥術、濕潤術、碎木術與飛斧投射範圍；擴大敏捷光球拾取範圍 3 倍；符文祭壇單次製作上限提升至 1,000（純事件觸發零輪詢）。 |
| 12 | Lua 模組 | 返家傳送術無冷卻 | `HomeTeleportNoCooldown` | `1.1.1` | 🌐 | 移除「返家傳送（Home Teleport）」法術的冷卻時間（預設 0 秒，可於遊戲內 Mod Menu 自訂秒數，純事件驅動零輪詢）。 |
| 13 | Lua 模組 | 遊戲內模組設定選單 (Mod Menu) | `Mod Menu` | `2.0.2` | 🌐 | 在遊戲暫停選單（Esc）新增「模組設定 (MODS)」按鈕與 F4 快捷面板，可在遊戲中即時調整各模組參數、檢查按鍵衝突與運行狀態。 |
| 14 | Lua 模組 | 背包一鍵快速堆疊至鄰近箱子 | `QuickStack` | `1.3.1` | 🌐 | 開啟背包時按 Y 鍵（或手把長按 Y）即可將背包物品一鍵快速堆疊至周圍 15 公尺內的箱子；按滑鼠中鍵可鎖定排除特定欄位物品。 |
| 15 | Lua 模組 | 儲物帳本銀行化總管介面 (Stashlink) | `Stashlink` | `1.1.6` | 🌐 | 在儲物帳本按 F（或 F6）開啟大型分類銀行介面，整合基地內所有已連結儲物箱，支援 10 大自動分類、關鍵字搜尋與批次存取。 |
| 16 | Lua 模組 | 加工站自動補料與配方載入面板 | `Station Feeder` | `1.8.2` | 🌐 | 開啟熔爐、鋸木機、紡車、製革架等 13 種加工站時，自動從鄰近箱子補滿原料與燃料，並提供一鍵「載入並啟動」配方側邊欄。 |
| 17 | Pak 模組 | 物品 50 倍堆疊上限且零負重 | `x50 Stacks No Weight` | `1.0.1` | — | 所有可堆疊物品的單格堆疊上限提升為 50 倍（最高 9,999 個），且所有堆疊物資重量設為 0。 |
| 18 | Pak 模組 | 世界寶箱快速重生 | `FasterChestRespawn` | `1.0` | — | 大幅縮短野外與地城中戰利品寶箱的重新生成冷卻時間，方便重複探索收集物資。 |
| 19 | Pak 模組 | 強化濕潤魔法 Lv.3 | `GreaterHumidify Level 3` | `3.4` | — | 強化「濕潤（Humidify）」實用魔法至最高等級效果，大幅提升澆灌農田與裝填水容器的效率與範圍。 |
| 20 | Pak 模組 | 強化快速生長魔法 Lv.3 | `GreaterRapidGrowth Level 3` | `1.4` | — | 強化「快速生長（Rapid Growth）」農業魔法至最高等級效果，大幅加速農田作物的生長階段。 |
| 21 | Pak 模組 | 鏟子瞬間挖掘 | `InstantSpade` | `1.0` | — | 移除使用鏟子（Spade）挖掘地面、農田或樹根時的蓄力與動作等待時間，實現瞬間挖掘。 |
| 22 | Pak 模組 | 個人儲物箱容量擴充 +++ | `MorePersonalChestStorage3` | `1.0.1` | — | 大幅擴充個人儲物箱（Personal Chest）的存放格數上限，解決基地物資儲存空間不足問題。 |
| 23 | Pak 模組 | 施放魔法期間自由移動 | `MoveWithMagic` | `1.0.1` | — | 解除施放各類法術與實用魔法時的原地定身限制，讓角色在詠唱與施法過程中仍可自由移動閃避。 |
| 24 | Pak 模組 | 裝備與工具永不損耗耐久度 | `NoDurabilityLoss` | `1.0` | — | 所有武器、防具與採集工具在使用與戰鬥時均不會扣除耐久度，免除頻繁維修裝備的困擾。 |
| 25 | Pak 模組 | 全法術技能零冷卻時間 | `NoSpellCooldown` | `1.0` | — | 移除戰鬥與實用魔法技能的冷卻時間限制，可連續施放法術。 |
| 26 | Pak 模組 | 傳送魔法免消耗符文 | `NoTeleportCost` | `1.0` | — | 使用磁石網路或傳送類魔法時免除符文（Runes）消耗，實現免費自由傳送。 |
| 27 | Pak 模組 | 無限衝刺閃避 (Unlimited Surge) | `UnlimitedSurge` | `1.0` | — | 移除「衝刺（Surge）」位移技能的冷卻限制，提供高速跑圖與靈活戰鬥閃避體驗。 |

## 啟動方式
```bash
python main.py
```
