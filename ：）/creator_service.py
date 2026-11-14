"""创世神面板业务门面：三端（Qt / pywebview / Electron）共用。

流程固定为 ``open -> preview -> apply``：
- preview 只读源文件并在内存里构建草稿，返回 token、警告与变更摘要；
- apply 校验 token 绑定的源文件哈希、独占锁、强制备份，再用事务写入；
- 任何一步失败都不会留下“写了一半”的世界。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import uuid as uuidlib
from datetime import datetime
from pathlib import Path

from . import nbt
from .creator_region import (
    RegionArchive,
    RegionError,
    build_region_bytes,
    read_region,
    region_files,
    replace_blocks,
)
from .creator_schema import (
    VanillaCaps,
    apply_player_edits,
    build_item,
    detect_era,
    get_node,
    identify_world,
    validate_number,
)
from .creator_tx import FileTransaction, WorldLock, strict_backup


class PreviewExpired(Exception):
    """预览已失效：源文件被改动，或 token 不存在。"""


class CreatorError(Exception):
    """可直接展示给用户的业务错误。"""


def _plain(node):
    tag, value = node
    if tag == nbt.TAG_COMPOUND:
        return {name: _plain(child) for name, child in value.items()}
    if tag == nbt.TAG_LIST:
        return [_plain(item) for item in value[1]]
    if tag == nbt.TAG_BYTE_ARRAY:
        return list(bytes(value))
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise CreatorError(f"无法读取 {path.name}：{exc}") from exc


def _num(node, default=0):
    if not node:
        return default
    try:
        return node[1]
    except (TypeError, IndexError):
        return default


class CreatorService:
    # 预览 token 必须跨 service 实例共享：Qt / Web 每次操作都可能新建一个 service，
    # 但「预览 → 确认写入」是两次独立调用。
    _PREVIEWS: dict[str, dict] = {}

    def __init__(self, game_dir, backup_root, *, backup_version: str = ""):
        self.game_dir = Path(game_dir)
        self.backup_root = Path(backup_root)
        self.backup_version = backup_version or "creator"
        self._previews = CreatorService._PREVIEWS

    # ------------------------------------------------------------------
    # 打开与读取
    # ------------------------------------------------------------------
    def open(self, world_path) -> dict:
        world = Path(world_path)
        level = world / "level.dat"
        if not level.is_file():
            raise CreatorError("该目录下没有 level.dat，不是可编辑的存档")
        _root_name, root = nbt.load_nbt_typed_file(level)
        if root[0] != nbt.TAG_COMPOUND or "Data" not in root[1]:
            raise CreatorError("level.dat 结构异常，缺少 Data 根节点")
        data = root[1]["Data"]
        identity = identify_world(_plain(data))
        players = [{"uuid": "level", "name": "世界内玩家", "path": str(level)}]
        player_dir = world / "playerdata"
        if player_dir.is_dir():
            for entry in sorted(player_dir.glob("*.dat")):
                players.append({"uuid": entry.stem, "name": entry.stem, "path": str(entry)})
        player_root = None
        player_node = data[1].get("Player")
        if player_node and player_node[0] == nbt.TAG_COMPOUND:
            player_root = player_node
        state = {
            "world": str(world),
            "name": str(_num(data[1].get("LevelName"), world.name)),
            "era": identity.era,
            "data_version": identity.data_version,
            "version_name": identity.version_name,
            "editable": identity.editable,
            "reason": identity.reason,
            "players": players,
            "player_uuid": "level",
            "player": self._read_player(player_root, identity.era) if player_root else None,
            "level": self._read_level(data),
            "backup_root": str(self.backup_root),
            "vanilla_caps": {
                "health": VanillaCaps.health(),
                "food": VanillaCaps.food(),
                "saturation": VanillaCaps.saturation(),
                "food_level": 20,
                "xp_level": VanillaCaps.xp_level(),
                "attribute": VanillaCaps.attribute(),
                "enchant_level": VanillaCaps.enchant_level(),
                "effect_duration": VanillaCaps.effect_duration(),
                "effect_amplifier": 255,
                "max_count": VanillaCaps.max_count(identity.era),
                "border_size": VanillaCaps.world_border_size(),
                "random_tick_speed": VanillaCaps.random_tick_speed(),
            },
        }
        return state

    def read_player(self, world_path, player_uuid: str = "level") -> dict:
        world = Path(world_path)
        era = self._era(world)
        node = self._player_node(world, player_uuid)
        return self._read_player(node, era) or {}

    def _era(self, world: Path) -> str:
        _name, root = nbt.load_nbt_typed_file(world / "level.dat")
        data = root[1]["Data"]
        return identify_world(_plain(data)).era

    def _player_node(self, world: Path, player_uuid: str):
        if player_uuid in ("", "level", None):
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            data = root[1]["Data"][1]
            node = data.get("Player")
            if node and node[0] == nbt.TAG_COMPOUND:
                return node
            return None
        path = world / "playerdata" / f"{player_uuid}.dat"
        if not path.is_file():
            raise CreatorError(f"找不到玩家数据：{path.name}")
        _name, root = nbt.load_nbt_typed_file(path)
        return root

    def _read_player(self, node, era: str) -> dict:
        if node is None or node[0] != nbt.TAG_COMPOUND:
            return {}
        fields = node[1]
        pos = []
        pos_node = fields.get("Pos")
        if pos_node and pos_node[0] == nbt.TAG_LIST:
            pos = [float(item[1]) for item in pos_node[1][1]][:3]
        inventory = self._read_inventory(fields.get("Inventory"), era)
        ender = self._read_inventory(fields.get("EnderItems"), era)
        attributes = []
        attr_node = fields.get("Attributes")
        if attr_node and attr_node[0] == nbt.TAG_LIST:
            for entry in attr_node[1][1]:
                values = entry[1]
                name = str(_num(values.get("Name"), "") or _num(values.get("id"), ""))
                base = float(_num(values.get("Base"), _num(values.get("base"), 0.0)))
                attributes.append(
                    {
                        "name": name,
                        "base": base,
                        "modifiers": self._read_attribute_modifiers(values, era),
                    }
                )
        effects = []
        effect_key = "active_effects" if "active_effects" in fields else "ActiveEffects"
        effect_node = fields.get(effect_key)
        if effect_node and effect_node[0] == nbt.TAG_LIST:
            for entry in effect_node[1][1]:
                values = entry[1]
                effects.append(
                    {
                        "id": int(_num(values.get("Id"), 1)),
                        "amplifier": int(_num(values.get("Amplifier"), 0)),
                        "duration": int(_num(values.get("Duration"), 0)),
                        "ambient": bool(_num(values.get("Ambient"), 0)),
                        "hide_particles": not bool(_num(values.get("ShowParticles"), 1)),
                    }
                )
        return {
            "health": float(_num(fields.get("Health"), 20.0)),
            "food": float(_num(fields.get("foodSaturationLevel"), 5.0)),
            "food_level": int(_num(fields.get("foodLevel"), 20)),
            "xp_level": int(_num(fields.get("XpLevel"), 0)),
            "xp_progress": float(_num(fields.get("XpP"), 0.0)),
            "game_type": int(_num(fields.get("playerGameType"), 0)),
            "dimension": str(_num(fields.get("Dimension"), "minecraft:overworld")),
            "pos": pos,
            "inventory": inventory,
            "ender_items": ender,
            "attributes": attributes,
            "effects": effects,
        }

    @staticmethod
    def _read_attribute_modifiers(fields: dict, era: str) -> list[dict]:
        key = "modifiers" if era == "components" else "Modifiers"
        node = fields.get(key)
        if not node or node[0] != nbt.TAG_LIST:
            return []
        result = []
        for entry in node[1][1]:
            values = entry[1]
            result.append(
                {
                    "name": str(_num(values.get("Name"), "") or _num(values.get("id"), "")),
                    "amount": float(_num(values.get("Amount"), _num(values.get("amount"), 0.0))),
                    "operation": _num(values.get("Operation"), _num(values.get("operation"), "add_value")),
                }
            )
        return result

    def _read_inventory(self, node, era: str) -> list[dict]:
        if not node or node[0] != nbt.TAG_LIST:
            return []
        result = []
        for entry in node[1][1]:
            if entry[0] != nbt.TAG_COMPOUND:
                continue
            fields = entry[1]
            item_id = ""
            id_node = fields.get("id")
            if id_node:
                if id_node[0] == nbt.TAG_SHORT:
                    item_id = self._legacy_name(int(id_node[1]))
                else:
                    item_id = str(id_node[1])
            count_node = fields.get("count") or fields.get("Count")
            count = int(_num(count_node, 1))
            slot_node = fields.get("Slot")
            damage = int(_num(fields.get("Damage"), 0))
            raw_key = "components" if era == "components" else "tag"
            raw_node = fields.get(raw_key)
            if not damage and raw_key == "components" and raw_node and raw_node[0] == nbt.TAG_COMPOUND:
                damage = int(_num(raw_node[1].get("minecraft:damage"), 0))
            tag_json = None
            if raw_node and raw_node[0] == nbt.TAG_COMPOUND:
                from .creator_schema import typed_to_json

                tag_json = typed_to_json(raw_node)
            result.append(
                {
                    "slot": int(_num(slot_node, 0)),
                    "id": item_id,
                    "count": count,
                    "count_tag": count_node[0] if count_node else None,
                    "damage": damage,
                    "enchantments": self._read_enchantments(fields, era),
                    "attributes": self._read_item_attributes(fields, era),
                    "has_tag": raw_node is not None,
                    "tag_json": tag_json,
                }
            )
        return result

    @staticmethod
    def _read_item_attributes(fields: dict, era: str) -> list[dict]:
        result = []
        if era == "components":
            components = fields.get("components")
            if not components or components[0] != nbt.TAG_COMPOUND:
                return result
            node = components[1].get("minecraft:attribute_modifiers")
            if not node or node[0] != nbt.TAG_COMPOUND:
                return result
            modifiers = node[1].get("modifiers")
            if not modifiers or modifiers[0] != nbt.TAG_LIST:
                return result
            for entry in modifiers[1][1]:
                values = entry[1]
                result.append(
                    {
                        "name": str(_num(values.get("type"), "")),
                        "amount": float(_num(values.get("amount"), 0.0)),
                        "operation": str(_num(values.get("operation"), "add_value")),
                        "slot": str(_num(values.get("slot"), "any")),
                    }
                )
            return result
        tag = fields.get("tag")
        if not tag or tag[0] != nbt.TAG_COMPOUND:
            return result
        modifiers = tag[1].get("AttributeModifiers")
        if not modifiers or modifiers[0] != nbt.TAG_LIST:
            return result
        for entry in modifiers[1][1]:
            values = entry[1]
            result.append(
                {
                    "name": str(_num(values.get("AttributeName"), "")),
                    "amount": float(_num(values.get("Amount"), 0.0)),
                    "operation": int(_num(values.get("Operation"), 0)),
                    "slot": str(_num(values.get("Slot"), "any")),
                }
            )
        return result

    @staticmethod
    def _legacy_name(numeric: int) -> str:
        from .creator_schema import LEGACY_ITEM_IDS

        for name, value in LEGACY_ITEM_IDS.items():
            if value == numeric:
                return name
        return f"#{numeric}"

    @staticmethod
    def _read_enchantments(fields: dict, era: str) -> list[dict]:
        from .creator_schema import _LEGACY_ENCHANT_IDS, ENCHANTMENTS

        reverse = {value: key for key, value in _LEGACY_ENCHANT_IDS.items()}
        entries = []
        if era == "components":
            components = fields.get("components")
            if components and components[0] == nbt.TAG_COMPOUND:
                enchant = components[1].get("minecraft:enchantments")
                if enchant and enchant[0] == nbt.TAG_COMPOUND:
                    levels = enchant[1].get("levels")
                    if levels and levels[0] == nbt.TAG_LIST:
                        for item in levels[1][1]:
                            name = str(_num(item[1].get("id"), "minecraft:sharpness"))
                            entries.append({"id": name, "level": int(_num(item[1].get("lvl"), 1))})
            return entries
        tag = fields.get("tag")
        if not tag or tag[0] != nbt.TAG_COMPOUND:
            return []
        enchant = tag[1].get("Enchantments")
        if not enchant or enchant[0] != nbt.TAG_LIST:
            return []
        for item in enchant[1][1]:
            values = item[1]
            id_node = values.get("id")
            level = int(_num(values.get("lvl"), 1))
            if id_node and id_node[0] == nbt.TAG_SHORT:
                name = reverse.get(int(id_node[1]))
                entries.append({"id": f"minecraft:{name}" if name else f"#{int(id_node[1])}", "level": level})
            elif id_node:
                name = str(id_node[1])
                if name in ENCHANTMENTS:
                    entries.append({"id": name, "level": level})
        return entries

    @staticmethod
    def _read_level(data) -> dict:
        fields = data[1]
        rules = {}
        rules_node = fields.get("GameRules")
        if rules_node and rules_node[0] == nbt.TAG_COMPOUND:
            for name, node in rules_node[1].items():
                rules[name] = str(node[1])
        border = {}
        border_node = fields.get("WorldBorder")
        if border_node and border_node[0] == nbt.TAG_COMPOUND:
            border = {
                "size": float(_num(border_node[1].get("Size"), 0.0)),
                "center_x": float(_num(border_node[1].get("CenterX"), 0.0)),
                "center_z": float(_num(border_node[1].get("CenterZ"), 0.0)),
            }
        raining = bool(_num(fields.get("raining"), 0))
        thundering = bool(_num(fields.get("thundering"), 0))
        weather = "thunder" if thundering else ("rain" if raining else "clear")
        return {
            "time": int(_num(fields.get("Time"), 0)),
            "day_time": int(_num(fields.get("DayTime"), 0)),
            "weather": weather,
            "gamerules": rules,
            "border": border,
            "spawn": [
                int(_num(fields.get("SpawnX"), 0)),
                int(_num(fields.get("SpawnY"), 64)),
                int(_num(fields.get("SpawnZ"), 0)),
            ],
            "difficulty": int(_num(fields.get("Difficulty"), 2)),
            "hardcore": bool(_num(fields.get("hardcore"), 0)),
            "allow_commands": bool(_num(fields.get("allowCommands"), 0)),
        }

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def preview(self, request: dict) -> dict:
        world = Path(request.get("world", ""))
        level_path = world / "level.dat"
        if not level_path.is_file():
            raise CreatorError("找不到 level.dat")
        era = self._era(world)
        if era in ("pre_anvil", "unknown"):
            raise CreatorError("该存档无法安全编辑，请先转换为 Anvil 格式")

        player_uuid = str(request.get("player_uuid") or "level")
        player_path = level_path if player_uuid == "level" else world / "playerdata" / f"{player_uuid}.dat"
        if not player_path.is_file():
            raise CreatorError("找不到玩家数据文件")

        _name, level_root = nbt.load_nbt_typed_file(level_path)
        level_root = copy.deepcopy(level_root)
        warnings: list[dict] = []
        changes: list[str] = []

        player_edits = dict(request.get("player") or {})
        safe_teleport = bool(player_edits.pop("safe_teleport", False))
        if safe_teleport:
            pos = list(player_edits.get("pos") or [])
            if len(pos) == 3:
                height = self._surface_height(world, int(float(pos[0])), int(float(pos[2])))
                if height is None:
                    warnings.append(
                        {
                            "code": "safe_teleport_missing_chunk",
                            "field": "Pos",
                            "message": "目标 X/Z 没有已加载区块，无法确定落点，已保留原 Y 坐标",
                        }
                    )
                else:
                    player_edits["pos"] = [pos[0], float(height + 1), pos[2]]
                    changes.append(f"安全传送：落点 Y={height + 1}")
        if player_edits:
            player_root = self._player_node(world, player_uuid)
            if player_root is None:
                player_root = (nbt.TAG_COMPOUND, {})
            player_root = copy.deepcopy(player_root)
            warnings += apply_player_edits(player_root, player_edits, era)
            changes += [f"玩家字段：{', '.join(sorted(player_edits))}"]

        level_edits = dict(request.get("level") or {})
        if level_edits:
            warnings += self._apply_level_edits(level_root, level_edits)
            changes += [f"世界字段：{', '.join(sorted(level_edits))}"]

        token = _sha256_bytes(
            (
                json.dumps(
                    {"world": str(world), "player_uuid": player_uuid, "p": player_edits, "l": level_edits},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
                + str(datetime.now().timestamp())
            ).encode("utf-8")
        )[:32]
        hashes = {str(level_path): _sha256_file(level_path)}
        if player_path != level_path:
            hashes[str(player_path)] = _sha256_file(player_path)
        self._previews[token] = {
            "kind": "save",
            "world": world,
            "era": era,
            "player_uuid": player_uuid,
            "player_edits": player_edits,
            "level_edits": level_edits,
            "hashes": hashes,
            "warnings": warnings,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        return {
            "token": token,
            "warnings": warnings,
            "changes": changes,
            "era": era,
            "backup_required": True,
            "player_uuid": player_uuid,
        }

    @staticmethod
    def _surface_height(world: Path, block_x: int, block_z: int) -> int | None:
        """查询目标列最高非空气方块；没有已加载区块时返回 None。"""
        from .creator_region import surface_y

        for path in region_files(world):
            try:
                archive = read_region(path)
                height = surface_y(archive, block_x, block_z)
            except (OSError, RegionError):
                continue
            if height is not None:
                return int(height)
        return None

    @staticmethod
    def _apply_level_edits(root, edits: dict) -> list[dict]:
        warnings: list[dict] = []
        data = root[1]["Data"][1]
        if "time" in edits:
            data["Time"] = (nbt.TAG_LONG, int(edits["time"]))
        if "day_time" in edits:
            data["DayTime"] = (nbt.TAG_LONG, int(edits["day_time"]))
        if "weather" in edits:
            weather = str(edits["weather"])
            data["raining"] = (nbt.TAG_BYTE, 0 if weather == "clear" else 1)
            data["thundering"] = (nbt.TAG_BYTE, 1 if weather == "thunder" else 0)
        if "gamerules" in edits and isinstance(edits["gamerules"], dict):
            rules_node = data.get("GameRules")
            if not rules_node or rules_node[0] != nbt.TAG_COMPOUND:
                rules_node = (nbt.TAG_COMPOUND, {})
                data["GameRules"] = rules_node
            for name, value in edits["gamerules"].items():
                rules_node[1][str(name)] = (nbt.TAG_STRING, str(value))
                if str(name) == "randomTickSpeed":
                    try:
                        warnings += validate_number(
                            "randomTickSpeed",
                            int(value),
                            VanillaCaps.random_tick_speed(),
                            "int",
                        )
                    except ValueError:
                        raise
        if "border_size" in edits:
            value = float(edits["border_size"])
            warnings += validate_number("WorldBorder.Size", value, VanillaCaps.world_border_size(), "double")
            border = data.get("WorldBorder")
            if not border or border[0] != nbt.TAG_COMPOUND:
                border = (nbt.TAG_COMPOUND, {})
                data["WorldBorder"] = border
            border[1]["Size"] = (nbt.TAG_DOUBLE, value)
        if "border_center" in edits:
            center = list(edits["border_center"])
            if len(center) != 2:
                raise CreatorError("世界边界中心需要 X/Z 两个分量")
            border = data.get("WorldBorder")
            if not border or border[0] != nbt.TAG_COMPOUND:
                border = (nbt.TAG_COMPOUND, {})
                data["WorldBorder"] = border
            border[1]["CenterX"] = (nbt.TAG_DOUBLE, float(center[0]))
            border[1]["CenterZ"] = (nbt.TAG_DOUBLE, float(center[1]))
        if "spawn" in edits:
            spawn = list(edits["spawn"])
            if len(spawn) != 3:
                raise CreatorError("出生点需要 X/Y/Z 三个分量")
            data["SpawnX"] = (nbt.TAG_INT, int(spawn[0]))
            data["SpawnY"] = (nbt.TAG_INT, int(spawn[1]))
            data["SpawnZ"] = (nbt.TAG_INT, int(spawn[2]))
        if "difficulty" in edits:
            data["Difficulty"] = (nbt.TAG_BYTE, int(edits["difficulty"]))
        if "hardcore" in edits:
            data["hardcore"] = (nbt.TAG_BYTE, 1 if edits["hardcore"] else 0)
        if "allow_commands" in edits:
            data["allowCommands"] = (nbt.TAG_BYTE, 1 if edits["allow_commands"] else 0)
        if "level_name" in edits:
            data["LevelName"] = (nbt.TAG_STRING, str(edits["level_name"]))
        return warnings

    # ------------------------------------------------------------------
    # 应用
    # ------------------------------------------------------------------
    def apply(self, token: str, *, confirmations: dict | None = None) -> dict:
        preview = self._previews.pop(str(token), None)
        if not preview:
            raise PreviewExpired("预览已失效，请重新预览后再保存")
        world: Path = preview["world"]
        for path_text, digest in preview["hashes"].items():
            if _sha256_file(Path(path_text)) != digest:
                raise PreviewExpired("源文件在预览后发生变化，请重新打开并预览")

        with WorldLock(world):
            backup = strict_backup(world, self.backup_root, self.backup_version)
            level_path = world / "level.dat"
            _name, level_root = nbt.load_nbt_typed_file(level_path)
            player_uuid = preview["player_uuid"]
            player_path = (
                level_path
                if player_uuid == "level"
                else world / "playerdata" / f"{player_uuid}.dat"
            )
            player_root = None
            if preview["player_edits"]:
                if player_uuid == "level":
                    data_fields = level_root[1]["Data"][1]
                    player_root = data_fields.get("Player")
                    if player_root is None:
                        player_root = (nbt.TAG_COMPOUND, {})
                        data_fields["Player"] = player_root
                else:
                    _n, player_root = nbt.load_nbt_typed_file(player_path)
                    player_root = copy.deepcopy(player_root)
                apply_player_edits(player_root, preview["player_edits"], preview["era"])
            if preview["level_edits"]:
                self._apply_level_edits(level_root, preview["level_edits"])

            tx = FileTransaction(world)
            if preview["level_edits"] or (preview["player_edits"] and player_uuid == "level"):
                tx.add(level_path, nbt.write_nbt_typed("", level_root))
            if preview["player_edits"] and player_uuid != "level":
                tx.add(player_path, nbt.write_nbt_typed("", player_root))
            tx.commit()
        return {
            "backup": str(backup.archive),
            "files": backup.files,
            "warnings": preview["warnings"],
            "player_uuid": preview["player_uuid"],
        }

    # ------------------------------------------------------------------
    # 物品
    # ------------------------------------------------------------------
    def scan_items(self, version_id: str = "", era: str = "") -> list[dict]:
        from .creator_items import scan_item_ids

        return scan_item_ids(self.game_dir, version_id=version_id, era=era)

    # ------------------------------------------------------------------
    # OP / 成就
    # ------------------------------------------------------------------
    @staticmethod
    def read_ops(server_dir) -> list[dict]:
        path = Path(server_dir) / "ops.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CreatorError(f"ops.json 解析失败：{exc}") from exc
        return payload if isinstance(payload, list) else []

    def write_ops(self, server_dir, entries: list[dict]) -> dict:
        server = Path(server_dir)
        path = server / "ops.json"
        if path.is_file():
            existing = {str(item.get("uuid")): item for item in self.read_ops(server)}
        else:
            existing = {}
        merged = []
        for entry in entries:
            uuid_text = str(entry.get("uuid", "")).strip()
            level = int(entry.get("level", 0))
            if not uuid_text:
                raise CreatorError("OP 条目缺少 UUID")
            if level < 0 or level > 4:
                raise CreatorError("OP 权限等级必须在 0 - 4 之间")
            base = dict(existing.get(uuid_text, {}))
            base.update(
                {
                    "uuid": uuid_text,
                    "name": str(entry.get("name", base.get("name", uuid_text))),
                    "level": level,
                    "bypassesPlayerLimit": bool(entry.get("bypasses_player_limit", False)),
                }
            )
            merged.append(base)
        tx = FileTransaction(server)
        tx.add(path, (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        tx.commit()
        return {"path": str(path), "count": len(merged)}

    @staticmethod
    def advancement_path(world, player_uuid: str = "level") -> Path | None:
        folder = Path(world) / "advancements"
        if not folder.is_dir():
            return None
        candidates = [folder / f"{player_uuid}.json"]
        if player_uuid == "level":
            candidates = sorted(folder.glob("*.json"))
        for path in candidates:
            if path.is_file():
                return path
        return None

    def read_advancements(self, world, player_uuid: str = "level") -> dict:
        path = self.advancement_path(world, player_uuid)
        if path is None:
            return {"path": "", "entries": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CreatorError(f"成就文件解析失败：{exc}") from exc
        entries = []
        if isinstance(payload, dict):
            for name, value in payload.items():
                criteria = value.get("criteria") if isinstance(value, dict) else {}
                entries.append(
                    {
                        "id": name,
                        "done": bool(value.get("done")) if isinstance(value, dict) else False,
                        "criteria": len(criteria) if isinstance(criteria, dict) else 0,
                    }
                )
        return {"path": str(path), "entries": sorted(entries, key=lambda item: item["id"])}

    def complete_advancements(
        self, world, player_uuid: str = "level", selected: list[str] | None = None
    ) -> dict:
        path = self.advancement_path(world, player_uuid)
        if path is None:
            raise CreatorError("该世界没有 advancements 数据")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise CreatorError("成就文件结构异常")
        wanted = {str(item) for item in (selected or []) if str(item)}
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S +0000")
        changed = 0
        for name, value in payload.items():
            if not isinstance(value, dict):
                continue
            if wanted and name not in wanted:
                continue
            value["done"] = True
            criteria = value.setdefault("criteria", {})
            if isinstance(criteria, dict):
                for key, when in list(criteria.items()):
                    if not when:
                        criteria[key] = stamp
            changed += 1
        if not changed:
            return {"path": str(path), "count": 0}
        tx = FileTransaction(Path(world))
        tx.add(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        tx.commit()
        return {"path": str(path), "count": changed}

    # ------------------------------------------------------------------
    # 旧格式转换（复用工具箱的存档转换器）
    # ------------------------------------------------------------------
    def convert_world(
        self,
        source,
        target_version: str,
        *,
        source_era: str = "auto",
        output_dir=None,
        workers: int = 0,
    ) -> dict:
        from .world_convert import WorldConvertError, convert

        try:
            return convert(
                source,
                str(target_version),
                source_era=source_era or "auto",
                output_dir=output_dir,
                workers=int(workers or 0),
            )
        except WorldConvertError as exc:
            raise CreatorError(str(exc)) from exc

    # ------------------------------------------------------------------
    # 区块替换
    # ------------------------------------------------------------------
    def preview_region(self, request: dict) -> dict:
        world = Path(request.get("world", ""))
        old_id = request.get("old_id")
        new_id = request.get("new_id")
        if old_id in (None, "") or new_id in (None, ""):
            raise CreatorError("需要填写原方块与目标方块")
        era = self._era(world)
        if era in ("pre_anvil", "unknown"):
            raise CreatorError("该存档不是 Anvil 格式，无法执行区块替换")
        files = region_files(world)
        if not files:
            raise CreatorError("该世界没有 region 目录")
        total = 0
        chunks = 0
        hashes = {}
        for path in files:
            hashes[str(path)] = _sha256_file(path)
            archive = read_region(path)
            stats = replace_blocks(archive, old_id, new_id, era=era)
            total += stats["replaced"]
            chunks += stats["chunks"]
        token = _sha256_bytes(
            (json.dumps({"w": str(world), "o": old_id, "n": new_id}, ensure_ascii=False) + str(datetime.now().timestamp())).encode()
        )[:32]
        self._previews[token] = {
            "kind": "region",
            "world": world,
            "era": era,
            "old_id": old_id,
            "new_id": new_id,
            "files": [str(path) for path in files],
            "hashes": hashes,
            "warnings": [],
        }
        return {
            "token": token,
            "files": len(files),
            "chunks": chunks,
            "replaced": total,
            "warnings": [],
            "backup_required": True,
        }

    def apply_region(self, token: str, *, confirmations: dict | None = None) -> dict:
        preview = self._previews.pop(str(token), None)
        if not preview or preview["kind"] != "region":
            raise PreviewExpired("区块替换预览已失效，请重新扫描")
        world: Path = preview["world"]
        for path_text, digest in preview["hashes"].items():
            if _sha256_file(Path(path_text)) != digest:
                raise PreviewExpired("region 文件在预览后发生变化，请重新扫描")
        with WorldLock(world):
            backup = strict_backup(world, self.backup_root, self.backup_version)
            tx = FileTransaction(world)
            replaced = 0
            for path_text in preview["files"]:
                path = Path(path_text)
                archive = read_region(path)
                stats = replace_blocks(archive, preview["old_id"], preview["new_id"], era=preview["era"])
                replaced += stats["replaced"]
                tx.add(path, build_region_bytes(archive))
            tx.commit()
        return {"backup": str(backup.archive), "replaced": replaced, "warnings": preview["warnings"]}

    # ------------------------------------------------------------------
    # 恢复
    # ------------------------------------------------------------------
    def restore_backup(self, archive_path, world_path) -> dict:
        """把备份 zip 解压覆盖到世界目录（先备份当前状态）。"""
        from .creator_tx import pending_transactions

        archive = Path(archive_path)
        world = Path(world_path)
        if not archive.is_file():
            raise CreatorError("备份文件不存在")
        if pending_transactions(world):
            raise CreatorError("该世界有未完成事务，请先处理 .mikancl-tx 目录")
        with WorldLock(world):
            safety = strict_backup(world, self.backup_root, self.backup_version)
            import zipfile

            with zipfile.ZipFile(archive) as zf:
                prefix = world.name + "/"
                tmp = Path(world) / ".mikancl-restore"
                if tmp.exists():
                    shutil.rmtree(tmp)
                tmp.mkdir()
                for member in zf.namelist():
                    if not member.startswith(prefix):
                        continue
                    target = tmp / member[len(prefix) :]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                for item in sorted(tmp.rglob("*")):
                    if item.is_file():
                        dest = world / item.relative_to(tmp)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(item, dest)
                shutil.rmtree(tmp, ignore_errors=True)
        return {"restored": str(archive), "safety_backup": str(safety.archive)}
