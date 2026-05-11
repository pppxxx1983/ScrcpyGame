"""YOLO class management: normalization, deduplication, merging."""
from __future__ import annotations

import re
import json
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set

# Common game-UI element mapping: Chinese / pinyin / variants -> canonical English snake_case
CANONICAL_MAP: Dict[str, str] = {
    # 通用UI
    "按钮": "button",
    "按键": "button",
    "按鈕": "button",
    "anniu": "button",
    "btn": "button",
    "确认": "confirm_button",
    "确定": "confirm_button",
    "queding": "confirm_button",
    "取消": "cancel_button",
    "quxiao": "cancel_button",
    "关闭": "close_button",
    "guanbi": "close_button",
    "返回": "back_button",
    "fanhui": "back_button",
    "菜单": "menu_button",
    "caidan": "menu_button",
    "设置": "settings_button",
    "shezhi": "settings_button",
    "开始": "start_button",
    "kaishi": "start_button",
    "开始游戏": "start_button",
    "继续": "continue_button",
    "jixu": "continue_button",
    "暂停": "pause_button",
    "zanting": "pause_button",
    "退出": "quit_button",
    "tuichu": "quit_button",
    # 游戏元素
    "角色": "character",
    "juese": "character",
    "英雄": "hero",
    "yingxiong": "hero",
    "敌人": "enemy",
    "diren": "enemy",
    "怪物": "enemy",
    "guaiwu": "enemy",
    "怪物": "monster",
    "道具": "item",
    "daoju": "item",
    "物品": "item",
    "金币": "coin",
    "jinbi": "coin",
    "钻石": "gem",
    "zuanshi": "gem",
    "宝箱": "chest",
    "baoxiang": "chest",
    "血条": "health_bar",
    "xuetiao": "health_bar",
    "能量条": "energy_bar",
    "nengliangtiao": "energy_bar",
    "技能": "skill_icon",
    "jineng": "skill_icon",
    "地图": "map_icon",
    "ditu": "map_icon",
    "任务": "quest_icon",
    "renwu": "quest_icon",
    "商店": "shop_icon",
    "shangdian": "shop_icon",
    "聊天": "chat_icon",
    "liaotian": "chat_icon",
    # 植物大战僵尸特定
    "植物": "plant",
    "zhiwu": "plant",
    "僵尸": "zombie",
    "jiangshi": "zombie",
    "阳光": "sun",
    "yangguang": "sun",
    "卡片": "card",
    "kapian": "card",
    "铲子": "shovel",
    "chanzi": "shovel",
    "草地": "lawn",
    "caodi": "lawn",
    # 通用文本/输入
    "文本": "text_label",
    "wenben": "text_label",
    "文字": "text_label",
    "输入框": "input_field",
    "shurukuang": "input_field",
    "标题": "title",
    "biaoti": "title",
    # 其他常见
    "tap_target": "tap_target",
    "ui_element": "ui_element",
    "icon": "icon",
    "avatar": "avatar",
    "progress_bar": "progress_bar",
    "slider": "slider",
    "toggle": "toggle",
    "checkbox": "checkbox",
    "radio": "radio_button",
    "tab": "tab",
    "list_item": "list_item",
    "grid_cell": "grid_cell",
    "notification": "notification",
    "popup": "popup",
    "dialog": "dialog",
    "banner": "banner",
    "ad": "ad_banner",
}

# Plural / suffix stripping helpers
SUFFIXES = ["_button", "_icon", "_label", "_bar", "_field", "_item", "_cell"]


def _to_pinyin(text: str) -> str:
    """Naive pinyin-ish fallback: strip tones, keep latin."""
    # This is a lightweight approximation; for real pinyin use pypinyin.
    # We keep it dependency-free by using the canonical map as primary source.
    return re.sub(r"[^a-zA-Z0-9_]", "", text).lower()


def normalize_class_name(name: str) -> str:
    """
    Normalize a raw class name to canonical English snake_case.
    1. Exact match in CANONICAL_MAP
    2. Case-insensitive match
    3. Strip common suffixes and retry
    4. Fallback: sanitize to snake_case ASCII
    """
    raw = str(name or "").strip()
    if not raw:
        return "ui_element"

    # 1. Exact
    if raw in CANONICAL_MAP:
        return CANONICAL_MAP[raw]

    # 2. Case-insensitive exact
    lower = raw.lower()
    if lower in CANONICAL_MAP:
        return CANONICAL_MAP[lower]

    # 3. Strip suffixes and retry
    for suffix in SUFFIXES:
        if lower.endswith(suffix):
            base = lower[: -len(suffix)]
            if base in CANONICAL_MAP:
                mapped = CANONICAL_MAP[base]
                return mapped + suffix

    # 4. Sanitize to ASCII snake_case
    # Remove non-alphanumeric, collapse underscores
    safe = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", raw).strip("_")
    # If still contains CJK, try character-by-character approximate mapping
    # (simplified: just transliterate known substrings)
    for cn, en in CANONICAL_MAP.items():
        if len(cn) > 1 and cn in safe:
            safe = safe.replace(cn, en)
    # Any remaining CJK -> "cjk" placeholder or keep if we want human review
    safe = re.sub(r"[^0-9A-Za-z_]", "_", safe)
    safe = re.sub(r"_+", "_", safe).strip("_").lower()[:32]
    return safe or "ui_element"


def compute_similarity(a: str, b: str) -> float:
    """Return 0.0-1.0 similarity using SequenceMatcher."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


@dataclass
class ClassMergeSuggestion:
    keep: str
    merge: str
    similarity: float
    reason: str


@dataclass
class YoloClassManager:
    classes_txt: Path
    alias_json: Path = field(default=None)  # type: ignore[assignment]
    names: List[str] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.alias_json is None:
            self.alias_json = self.classes_txt.with_name("class_aliases.json")
        self._load()

    def _load(self):
        if self.classes_txt.exists():
            self.names = [
                line.strip()
                for line in self.classes_txt.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            self.names = ["tap_target"]
        if self.alias_json.exists():
            try:
                self.aliases = json.loads(self.alias_json.read_text(encoding="utf-8"))
            except Exception:
                self.aliases = {}
        else:
            self.aliases = {}

    def save(self):
        self.classes_txt.parent.mkdir(parents=True, exist_ok=True)
        self.classes_txt.write_text("\n".join(self.names) + "\n", encoding="utf-8")
        self.alias_json.write_text(
            json.dumps(self.aliases, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def resolve(self, raw_name: str) -> str:
        """Return canonical name for a raw class name, updating aliases if new."""
        canonical = normalize_class_name(raw_name)
        # Check explicit aliases first
        if raw_name in self.aliases:
            return self.aliases[raw_name]
        # If canonical already in names, map raw -> canonical
        if canonical in self.names:
            if raw_name != canonical:
                self.aliases[raw_name] = canonical
            return canonical
        # If raw itself is in names but different from canonical, create alias
        if raw_name in self.names and raw_name != canonical:
            self.aliases[raw_name] = canonical
            # We should migrate raw_name to canonical in the future
            return canonical
        return canonical

    def ensure(self, raw_name: str) -> int:
        """Like _ensure_yolo_class but with normalization and dedup."""
        canonical = self.resolve(raw_name)
        if canonical not in self.names:
            self.names.append(canonical)
            self.save()
        return self.names.index(canonical)

    def suggest_merges(self, threshold: float = 0.75) -> List[ClassMergeSuggestion]:
        """Find pairs of classes that look like duplicates."""
        suggestions: List[ClassMergeSuggestion] = []
        seen = set()
        for i, a in enumerate(self.names):
            for b in self.names[i + 1 :]:
                if b in seen:
                    continue
                sim = compute_similarity(a, b)
                if sim >= threshold:
                    # Determine which is more "canonical"
                    keep, merge = (a, b) if len(a) <= len(b) else (b, a)
                    suggestions.append(
                        ClassMergeSuggestion(
                            keep=keep,
                            merge=merge,
                            similarity=sim,
                            reason=f"similarity={sim:.2f}",
                        )
                    )
        # Also check alias inversions
        for raw, can in list(self.aliases.items()):
            if raw in self.names and can in self.names:
                suggestions.append(
                    ClassMergeSuggestion(
                        keep=can,
                        merge=raw,
                        similarity=1.0,
                        reason="alias_duplicate",
                    )
                )
        return suggestions

    def merge(self, merge_name: str, into_name: str, labels_dir: Path | None = None):
        """Merge one class into another, optionally rewriting label files."""
        if merge_name not in self.names:
            raise ValueError(f"Class to merge '{merge_name}' not found")
        if into_name not in self.names:
            raise ValueError(f"Target class '{into_name}' not found")
        if merge_name == into_name:
            return

        merge_id = self.names.index(merge_name)
        into_id = self.names.index(into_name)

        # Update all aliases pointing to merge_name
        for raw, can in list(self.aliases.items()):
            if can == merge_name:
                self.aliases[raw] = into_name

        # Remove from list
        self.names.remove(merge_name)
        self.save()

        # Rewrite labels
        if labels_dir and labels_dir.exists():
            for txt_file in labels_dir.rglob("*.txt"):
                lines = txt_file.read_text(encoding="utf-8").splitlines()
                new_lines = []
                changed = False
                for line in lines:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    try:
                        cid = int(parts[0])
                    except ValueError:
                        new_lines.append(line)
                        continue
                    if cid == merge_id:
                        parts[0] = str(into_id)
                        new_lines.append(" ".join(parts))
                        changed = True
                    elif cid > merge_id:
                        parts[0] = str(cid - 1)
                        new_lines.append(" ".join(parts))
                        changed = True
                    else:
                        new_lines.append(line)
                if changed:
                    txt_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def rebuild_from_labels(self, labels_dir: Path) -> Dict[int, str]:
        """Scan labels to discover actual class IDs used, warn about orphans."""
        max_id = -1
        for txt_file in labels_dir.rglob("*.txt"):
            for line in txt_file.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if parts:
                    try:
                        cid = int(parts[0])
                        max_id = max(max_id, cid)
                    except ValueError:
                        pass
        # Ensure list covers all IDs
        while len(self.names) <= max_id:
            self.names.append(f"class_{len(self.names)}")
        self.save()
        return {i: n for i, n in enumerate(self.names)}

    def to_data_yaml(self) -> str:
        lines = ["path: .", "train: images/train", "val: images/train", "names:"]
        lines.extend(f"  {idx}: {name}" for idx, name in enumerate(self.names))
        return "\n".join(lines) + "\n"
