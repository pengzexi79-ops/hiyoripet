"""应用收纳箱：用户拖喂给桌宠的应用/文件快捷存储（契约 C8）。"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

GAME_KEYS = ("game", "steam", "epic", "wegame", "原神", "崩坏", "minecraft", "lol", "dota")
MEDIA_KEYS = ("vlc", "potplayer", "qq音乐", "netease", "bilibili", "video", "music", "player")
OFFICE_KEYS = ("word", "excel", "powerpoint", "wps", "office", "ppt", "doc", "xls", "pdf")
BROWSER_KEYS = ("chrome", "edge", "firefox", "browser", "浏览器")
MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".mp3", ".flac", ".wav", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
OFFICE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt", ".md"}


def _box_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return root / "HiyoriPet" / "box.json"


def _read() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_box_path().read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        return [item for item in items if isinstance(item, dict) and item.get("path")]
    except Exception:
        return []


def _write(items: list[dict[str, Any]]) -> None:
    path = _box_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def categorize(path: str) -> str:
    p = Path(path)
    name = p.stem.lower()
    if p.is_dir():
        return "文件夹"
    ext = p.suffix.lower()
    if any(key in name for key in GAME_KEYS):
        return "游戏"
    if any(key in name for key in BROWSER_KEYS):
        return "浏览器"
    if any(key in name for key in MEDIA_KEYS) or ext in MEDIA_EXTS:
        return "影音图片"
    if any(key in name for key in OFFICE_KEYS) or ext in OFFICE_EXTS:
        return "办公文档"
    return "工具应用"


def list_items() -> list[dict[str, Any]]:
    with _LOCK:
        return _read()


def add_item(path: str, name: str = "") -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise ValueError("文件不存在，无法收纳")
    with _LOCK:
        items = _read()
        for item in items:
            if str(item.get("path", "")).lower() == str(target).lower():
                return item
        entry = {
            "id": uuid.uuid4().hex[:10],
            "name": name.strip() or target.name,
            "path": str(target),
            "category": categorize(str(target)),
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }
        items.append(entry)
        _write(items)
        return entry


def remove_item(item_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        items = [item for item in _read() if item.get("id") != item_id]
        _write(items)
        return items


def launch_item(item_id: str) -> dict[str, Any]:
    items = {item.get("id"): item for item in list_items()}
    item = items.get(item_id)
    if not item:
        raise ValueError("收纳箱中找不到该条目")
    path = str(item.get("path", ""))
    if not Path(path).exists():
        raise ValueError("原始文件已不存在")
    os.startfile(path)  # type: ignore[attr-defined]
    return {"launched": path}
