# -*- coding: utf-8 -*-
"""
RuneScape: Dragonwilds - 世界存檔難度設定管理核心模組 (Save Settings Manager)
負責解析、備份與精確寫入虛幻引擎 SPUD (.sav) 二進位存檔中之自訂難度設定 (CustomDifficultySettings)
支援任意浮點數突破原生 3.0 上限與無建築穩定性 (NoBuildingStability) 開關
"""

import os
import sys
import glob
import struct
import shutil
import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any


# 難度設定項目中文對照表與分類
DIFFICULTY_META: Dict[str, Dict[str, Any]] = {
    # 角色與便利性
    "Difficulty.Player.NoBuildingStability": {
        "name": "無建築穩定性 (免支撐自由懸空搭建)",
        "category": "🌟 角色與便利性",
        "type": "bool",
        "default": 1.0,
        "desc": "啟用後建築不需要地基或柱子支撐，任何結構皆可懸空建造且不會坍塌"
    },
    "Difficulty.Player.InventoryCarryCapacityScale": {
        "name": "背包負重容量倍率",
        "category": "🌟 角色與便利性",
        "type": "float",
        "default": 1.0,
        "desc": "倍率越大，背包可承載重量上限越高 (可設為 3.0, 10.0, 100.0 等)"
    },
    "Difficulty.Player.StaminaScale": {
        "name": "耐力上限倍率",
        "category": "🌟 角色與便利性",
        "type": "float",
        "default": 1.0,
        "desc": "角色的最大耐力值倍率"
    },
    "Difficulty.Player.SpellCooldownScale": {
        "name": "法術冷卻時間倍率",
        "category": "🌟 角色與便利性",
        "type": "float",
        "default": 1.0,
        "desc": "法術冷卻倍率，設為 0.0 代表完全無冷卻時間"
    },
    "Difficulty.Player.SpellCostScale": {
        "name": "法術魔力/符文消耗倍率",
        "category": "🌟 角色與便利性",
        "type": "float",
        "default": 1.0,
        "desc": "施放法術消耗倍率，設為 0.0 代表完全無消耗"
    },
    "Difficulty.Player.TeleportationCostScale": {
        "name": "快速傳送消耗倍率",
        "category": "🌟 角色與便利性",
        "type": "float",
        "default": 1.0,
        "desc": "傳送石碑消耗倍率，設為 0.0 代表免費傳送"
    },

    # 遊戲進程與製作
    "Difficulty.Progression.XPGainScale": {
        "name": "經驗值獲得倍率 (XP Gain)",
        "category": "🚀 進程與製作",
        "type": "float",
        "default": 1.0,
        "desc": "所有技能獲得經驗值之倍率 (可自由輸入 3.0, 5.0, 10.0, 50.0 等，突破 3.0 限制)"
    },
    "Difficulty.Progression.ProcessingSpeedScale": {
        "name": "加工與熔煉精煉速度倍率",
        "category": "🚀 進程與製作",
        "type": "float",
        "default": 1.0,
        "desc": "工作台與熔爐加工物品之速度倍率"
    },
    "Difficulty.Progression.CraftingCostScale": {
        "name": "物品製作材料消耗倍率",
        "category": "🚀 進程與製作",
        "type": "float",
        "default": 1.0,
        "desc": "製作裝備或物品時消耗之材料倍率 (設為 0.1 或 0.0 可大幅節省材料)"
    },
    "Difficulty.Progression.BuildingMaterialCostScale": {
        "name": "建築零件材料消耗倍率",
        "category": "🚀 進程與製作",
        "type": "float",
        "default": 1.0,
        "desc": "建造牆面、屋頂等建築時消耗之材料倍率"
    },

    # 生存消耗
    "Difficulty.SurvivalCore.EnduranceDrainScale": {
        "name": "耐力消耗速率倍率",
        "category": "🍖 生存消耗",
        "type": "float",
        "default": 1.0,
        "desc": "奔跑與動作消耗耐力之速度 (倍率越小消耗越慢，0.0 為不消耗)"
    },
    "Difficulty.SurvivalCore.HydrationDrainScale": {
        "name": "水分消耗速率倍率 (口渴度)",
        "category": "🍖 生存消耗",
        "type": "float",
        "default": 1.0,
        "desc": "口渴值消耗速度 (倍率越小越不易口渴)"
    },
    "Difficulty.SurvivalCore.SustenanceDrainScale": {
        "name": "飽食度消耗速率倍率 (飢餓度)",
        "category": "🍖 生存消耗",
        "type": "float",
        "default": 1.0,
        "desc": "飢餓度消耗速度 (倍率越小越不易飢餓)"
    },
    "Difficulty.Environment.FriendlyFire": {
        "name": "友軍傷害 (Friendly Fire)",
        "category": "🍖 生存消耗",
        "type": "bool",
        "default": 0.0,
        "desc": "是否開啟隊友與自傷傷害 (0.0=關閉, 1.0=開啟)"
    },

    # 戰鬥與敵人倍率
    "Difficulty.AI.Boss.Damage": {
        "name": "首領 (Boss) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "首領怪物造成之傷害倍率"
    },
    "Difficulty.AI.Boss.Resistances": {
        "name": "首領 (Boss) 抗性/防禦倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "首領怪物之防禦與抗性倍率"
    },
    "Difficulty.AI.MiniBoss.Damage": {
        "name": "菁英怪 (MiniBoss) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "菁英怪傷害倍率"
    },
    "Difficulty.AI.MiniBoss.Resistances": {
        "name": "菁英怪 (MiniBoss) 抗性倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "菁英怪抗性倍率"
    },
    "Difficulty.AI.Goblin.Damage": {
        "name": "哥布林 (Goblin) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "哥布林怪物傷害倍率"
    },
    "Difficulty.AI.Skeleton.Damage": {
        "name": "骷髏 (Skeleton) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "骷髏怪物傷害倍率"
    },
    "Difficulty.AI.Undead.Damage": {
        "name": "不死族 (Undead) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "不死族怪物傷害倍率"
    },
    "Difficulty.AI.Beast.Damage": {
        "name": "野獸 (Beast) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "野獸怪物傷害倍率"
    },
    "Difficulty.AI.Garou.Damage": {
        "name": "狼人 (Garou) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "狼人怪物傷害倍率"
    },
    "Difficulty.AI.Kalphite.Damage": {
        "name": "甲蟲 (Kalphite) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "甲蟲怪物傷害倍率"
    },
    "Difficulty.AI.Kothaar.Damage": {
        "name": "寇薩爾 (Kothaar) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "寇薩爾怪物傷害倍率"
    },
    "Difficulty.AI.Zamorak.Damage": {
        "name": "薩莫拉克狂徒 (Zamorak) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "薩莫拉克狂徒傷害倍率"
    },
    "Difficulty.AI.Construct.Damage": {
        "name": "機關人造物 (Construct) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "人造物敵人傷害倍率"
    },
    "Difficulty.AI.Critter.Damage": {
        "name": "小生物 (Critter) 傷害倍率",
        "category": "⚔️ 戰鬥與敵人",
        "type": "float",
        "default": 1.0,
        "desc": "小型生物傷害倍率"
    }
}


def get_save_games_dir() -> Optional[Path]:
    """獲取本機存檔目錄 %LOCALAPPDATA%\\RSDragonwilds\\Saved\\SaveGames"""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    p = Path(local_app_data) / "RSDragonwilds" / "Saved" / "SaveGames"
    return p if p.exists() else None


def list_save_files() -> List[Dict[str, Any]]:
    """掃描所有可用的世界存檔檔案 (.sav)"""
    sdir = get_save_games_dir()
    if not sdir:
        return []

    saves = []
    for fp in sdir.glob("*.sav"):
        # 排除備份檔如 .sav.bak
        if fp.name.endswith(".sav") and not fp.name.endswith(".bak"):
            stat = fp.stat()
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            saves.append({
                "path": str(fp),
                "filename": fp.name,
                "world_name": fp.stem,
                "size": stat.st_size,
                "mtime": mtime
            })
    saves.sort(key=lambda x: x["mtime"], reverse=True)
    return saves


def read_fstring(b: bytes, pos: int) -> Tuple[int, str]:
    """讀取虛幻引擎 FString 二進位字串"""
    if pos + 4 > len(b):
        return pos, ""
    slen, = struct.unpack_from("<i", b, pos)
    pos += 4
    if slen > 0:
        if pos + slen > len(b):
            return pos, ""
        s = b[pos:pos+slen-1].decode("utf-8", errors="replace")
        return pos + slen, s
    elif slen < 0:
        ulen = -slen * 2
        if pos + ulen > len(b):
            return pos, ""
        s = b[pos:pos+ulen-2].decode("utf-16le", errors="replace")
        return pos + ulen, s
    return pos, ""


def write_fstring(s: str) -> bytes:
    """序列化字串為 UE4/5 FString"""
    sb = s.encode("utf-8") + b"\x00"
    return struct.pack("<i", len(sb)) + sb


def read_save_settings(sav_path: str) -> Dict[str, Any]:
    """
    精確讀取 .sav 存檔中之自訂難度設定
    回傳字典：{'world_name': str, 'survival_difficulty': int, 'settings': Dict[str, float]}
    """
    if not os.path.exists(sav_path):
        raise FileNotFoundError(f"找不到存檔: {sav_path}")

    with open(sav_path, "rb") as f:
        buf = f.read()

    if not buf.startswith(b"SAVE"):
        raise ValueError("檔案不是合法的虛幻 SPUD 存檔格式 (缺少 SAVE 標頭)")

    result = {
        "world_name": Path(sav_path).stem,
        "survival_difficulty": 0,
        "settings": {}
    }

    # 1. 尋找 GLOB -> GOBS -> NOBJ -> PROP 尋找 CustomDifficultySettings
    glob_pos = buf.find(b"GLOB")
    gobs_pos = buf.find(b"GOBS", glob_pos) if glob_pos >= 0 else -1
    nobj_pos = buf.find(b"NOBJ", gobs_pos) if gobs_pos >= 0 else -1
    prop_pos = buf.find(b"PROP", nobj_pos) if nobj_pos >= 0 else -1

    if prop_pos >= 0:
        pp = prop_pos + 8
        num_props, = struct.unpack_from("<I", buf, pp)
        offsets = list(struct.unpack_from(f"<{num_props}I", buf, pp + 4))
        data_start = pp + 4 + 4 * num_props

        # 搜尋 CustomDifficultySettings Map
        # 標誌性 pattern: TagName NameProperty
        pattern = b"TagName\x00\r\x00\x00\x00NameProperty\x00"
        match_pos = buf.find(pattern, prop_pos)
        if match_pos >= 0:
            # count 位於 match_pos - 8 之前 4 個 bytes (或在 -4)
            count_pos = match_pos - 8
            count, = struct.unpack_from("<I", buf, count_pos)
            cur = count_pos + 4
            for _ in range(count):
                cur, _ = read_fstring(buf, cur) # TagName
                cur, _ = read_fstring(buf, cur) # NameProperty
                prop_sz, = struct.unpack_from("<Q", buf, cur)
                cur += 9 # 8 bytes size + 1 byte pad
                cur, tag = read_fstring(buf, cur)
                cur, _ = read_fstring(buf, cur) # None
                fval, = struct.unpack_from("<f", buf, cur)
                cur += 4
                result["settings"][tag] = fval

    # 2. 同步檢查 CINF 區段之欄位
    cinf_pos = buf.find(b"CINF")
    if cinf_pos >= 0:
        cp = cinf_pos + 8
        num_fields, = struct.unpack_from("<I", buf, cp)
        cp += 4
        fields = []
        for _ in range(num_fields):
            cp, fn = read_fstring(buf, cp)
            fields.append(fn)
        if cp + 4 <= len(buf):
            num_fields2, = struct.unpack_from("<I", buf, cp)
            cp += 4
            if num_fields == num_fields2:
                field_offsets = list(struct.unpack_from(f"<{num_fields}I", buf, cp))
                val_start = cp + 4 * num_fields
                for i, fn in enumerate(fields):
                    if fn.startswith("Difficulty."):
                        vo = val_start + field_offsets[i]
                        if vo + 4 <= len(buf):
                            fval, = struct.unpack_from("<f", buf, vo)
                            # 若 Map 中沒有該設定，補入
                            if fn not in result["settings"]:
                                result["settings"][fn] = fval

    return result


def write_save_settings(sav_path: str, new_settings: Dict[str, float]) -> str:
    """
    精確重構並寫入存檔之自訂難度設定
    寫入前自動在相同目錄建立帶時間戳記之 .bak 備份檔案
    回傳備份檔案路徑
    """
    if not os.path.exists(sav_path):
        raise FileNotFoundError(f"找不到存檔: {sav_path}")

    # 1. 建立備份
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = f"{sav_path}.bak_{timestamp}"
    shutil.copy2(sav_path, bak_path)

    with open(sav_path, "rb") as f:
        orig = f.read()

    # --- A. 重構 CINF 區段 ---
    cinf_pos = orig.find(b"CINF")
    cinf_sz, = struct.unpack_from("<I", orig, cinf_pos+4)
    cp = cinf_pos + 8
    num_fields, = struct.unpack_from("<I", orig, cp)
    cp += 4

    fields = []
    for _ in range(num_fields):
        cp, fname = read_fstring(orig, cp)
        fields.append(fname)

    num_fields2, = struct.unpack_from("<I", orig, cp)
    cp += 4
    field_offsets = list(struct.unpack_from(f"<{num_fields}I", orig, cp))
    cp += 4 * num_fields
    val_start = cp
    val_end = cinf_pos + 8 + cinf_sz
    val_bytes = orig[val_start:val_end]

    field_values = []
    for i in range(num_fields):
        vo = field_offsets[i]
        next_vo = field_offsets[i+1] if i + 1 < num_fields else len(val_bytes)
        field_values.append(val_bytes[vo:next_vo])

    # 準備新 fields 與 values
    # 保留非 Difficulty 的基本前綴與後綴欄位
    base_pre_fields = []
    base_pre_values = []
    base_post_fields = []
    base_post_values = []

    in_diff_section = False
    for i, fn in enumerate(fields):
        if fn.startswith("Difficulty."):
            in_diff_section = True
            # 跳過舊的 Difficulty 標籤，後面統一按 new_settings 寫入
            continue
        elif not in_diff_section:
            base_pre_fields.append(fn)
            base_pre_values.append(field_values[i])
        else:
            base_post_fields.append(fn)
            base_post_values.append(field_values[i])

    # 組合新 CINF
    final_cinf_fields = list(base_pre_fields)
    final_cinf_values = list(base_pre_values)

    # 排序 new_settings 標籤
    sorted_tags = sorted(new_settings.keys())
    for tag in sorted_tags:
        final_cinf_fields.append(tag)
        final_cinf_values.append(struct.pack("<f", float(new_settings[tag])))

    final_cinf_fields.extend(base_post_fields)
    final_cinf_values.extend(base_post_values)

    new_cinf_body = bytearray()
    new_cinf_body.extend(struct.pack("<I", len(final_cinf_fields)))
    for fn in final_cinf_fields:
        new_cinf_body.extend(write_fstring(fn))
    new_cinf_body.extend(struct.pack("<I", len(final_cinf_fields)))

    cur_val_off = 0
    new_cinf_offsets = []
    for fv in final_cinf_values:
        new_cinf_offsets.append(cur_val_off)
        cur_val_off += len(fv)

    for off in new_cinf_offsets:
        new_cinf_body.extend(struct.pack("<I", off))
    for fv in final_cinf_values:
        new_cinf_body.extend(fv)

    new_cinf_chunk = b"CINF" + struct.pack("<I", len(new_cinf_body)) + new_cinf_body

    info_pos = 8
    info_sz, = struct.unpack_from("<I", orig, info_pos+4)
    info_header_part = orig[info_pos+8 : cinf_pos]
    new_info_body = info_header_part + new_cinf_chunk
    new_info_chunk = b"INFO" + struct.pack("<I", len(new_info_body)) + new_info_body

    # --- B. 重構 GLOB (PROP / NOBJ / GOBS / GLOB) ---
    glob_pos = orig.find(b"GLOB")
    glob_sz, = struct.unpack_from("<I", orig, glob_pos+4)

    gobs_pos = orig.find(b"GOBS", glob_pos)
    gobs_sz, = struct.unpack_from("<I", orig, gobs_pos+4)

    nobj_pos = orig.find(b"NOBJ", gobs_pos)
    nobj_sz, = struct.unpack_from("<I", orig, nobj_pos+4)

    prop_pos = orig.find(b"PROP", nobj_pos)
    prop_sz, = struct.unpack_from("<I", orig, prop_pos+4)

    pp = prop_pos + 8
    num_props, = struct.unpack_from("<I", orig, pp)
    pp += 4
    prop_offsets = list(struct.unpack_from(f"<{num_props}I", orig, pp))
    data_start = pp + 4 * num_props

    # 搜尋 CustomDifficultySettings 起始與結束邊界
    pattern = b"TagName\x00\r\x00\x00\x00NameProperty\x00"
    match_pos = orig.find(pattern, prop_pos)
    if match_pos < 0:
        raise ValueError("存檔中找不到 CustomDifficultySettings 屬性結構")

    map_count_pos = match_pos - 8
    old_count, = struct.unpack_from("<I", orig, map_count_pos)

    # 遍歷跳過舊有的所有 map 條目以求出 map_end
    cur = map_count_pos + 4
    for _ in range(old_count):
        cur, _ = read_fstring(orig, cur)
        cur, _ = read_fstring(orig, cur)
        cur += 9 # uint64 + pad
        cur, _ = read_fstring(orig, cur)
        cur, _ = read_fstring(orig, cur)
        cur += 4 # float
    map_end_pos = cur

    # 建構新的 Map 條目二進位資料
    new_entries_bytes = bytearray()
    for tag in sorted_tags:
        val = float(new_settings[tag])
        tag_fstr = write_fstring(tag)
        entry = (
            write_fstring("TagName") +
            write_fstring("NameProperty") +
            struct.pack("<Q", len(tag_fstr)) +
            b"\x00" +
            tag_fstr +
            write_fstring("None") +
            struct.pack("<f", val)
        )
        new_entries_bytes.extend(entry)

    # 組合新的 PROP 內容
    new_prop_data = bytearray()
    new_prop_data.extend(orig[data_start : map_count_pos])
    new_prop_data.extend(struct.pack("<I", len(sorted_tags))) # 新的 count
    new_prop_data.extend(new_entries_bytes)
    new_prop_data.extend(orig[map_end_pos : prop_pos + 8 + prop_sz])

    # 計算 offset delta
    old_map_len = map_end_pos - (map_count_pos + 4)
    delta = len(new_entries_bytes) - old_map_len

    new_prop_offsets = list(prop_offsets)
    for i in range(9, num_props):
        new_prop_offsets[i] += delta

    new_prop_body = bytearray()
    new_prop_body.extend(struct.pack("<I", num_props))
    for off in new_prop_offsets:
        new_prop_body.extend(struct.pack("<I", off))
    new_prop_body.extend(new_prop_data)

    new_prop_chunk = b"PROP" + struct.pack("<I", len(new_prop_body)) + new_prop_body
    new_nobj_body = orig[nobj_pos+8 : prop_pos] + new_prop_chunk + orig[prop_pos + 8 + prop_sz : nobj_pos + 8 + nobj_sz]
    new_nobj_chunk = b"NOBJ" + struct.pack("<I", len(new_nobj_body)) + new_nobj_body

    new_gobs_body = orig[gobs_pos+8 : nobj_pos] + new_nobj_chunk + orig[nobj_pos + 8 + nobj_sz : gobs_pos + 8 + gobs_sz]
    new_gobs_chunk = b"GOBS" + struct.pack("<I", len(new_gobs_body)) + new_gobs_body

    new_glob_body = orig[glob_pos+8 : gobs_pos] + new_gobs_chunk + orig[gobs_pos + 8 + gobs_sz : glob_pos + 8 + glob_sz]
    new_glob_chunk = b"GLOB" + struct.pack("<I", len(new_glob_body)) + new_glob_body

    # --- C. 組合成完整存檔 ---
    final_save = bytearray()
    final_save.extend(b"SAVE\x00\x00\x00\x00")
    final_save.extend(new_info_chunk)
    final_save.extend(orig[info_pos + 8 + info_sz : glob_pos])
    final_save.extend(new_glob_chunk)
    final_save.extend(orig[glob_pos + 8 + glob_sz :])

    total_sz = len(final_save) - 8
    struct.pack_into("<I", final_save, 4, total_sz)

    # 覆蓋寫入檔案
    with open(sav_path, "wb") as f:
        f.write(final_save)

    return bak_path

