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


def _icons_dir() -> Path:
    return _box_path().parent / "icons"


def _desktop_dir() -> Path | None:
    import ctypes

    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf) == 0:
            return Path(buf.value)
    except Exception:
        pass
    return Path.home() / "Desktop"


def _lnk_target(lnk: Path) -> str | None:
    import subprocess

    script = f"$w=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); Write-Output $w.TargetPath"
    try:
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15, creationflags=0x08000000)
        value = (proc.stdout or "").strip().splitlines()
        return value[-1] if value else None
    except Exception:
        return None


def _url_target(url_file: Path) -> str | None:
    """读取 .url 快捷方式的 URL（INI 格式：[InternetShortcut] URL=...）。"""
    try:
        for line in url_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("url="):
                value = line[4:].strip()
                return value or None
    except Exception:
        return None
    return None


def ensure_icon(item: dict[str, Any]) -> str | None:
    """提取 exe/lnk 关联图标为 PNG，返回路径；失败返回 None（前端回退占位图）。"""
    import subprocess

    target = Path(str(item.get("path", "")))
    if not target.exists():
        return None
    icons = _icons_dir()
    icons.mkdir(parents=True, exist_ok=True)
    png = icons / f"{item.get('id')}.png"
    if png.exists():
        return str(png)
    script = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$i=[System.Drawing.Icon]::ExtractAssociatedIcon('{target}'); "
        f"$i.ToBitmap().Save('{png}')"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=20, creationflags=0x08000000)
    except Exception:
        return None
    return str(png) if png.exists() else None


def _parse_items(text: str) -> list[dict[str, Any]]:
    raw = json.loads(text)
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    return [item for item in items if isinstance(item, dict) and item.get("path")]


def _read() -> list[dict[str, Any]]:
    path = _box_path()
    for candidate in (path, path.with_suffix(".json.bak")):
        try:
            return _parse_items(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
    return []


def _write(items: list[dict[str, Any]]) -> None:
    path = _box_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    if items:
        # 非空写入留一份备份，异常清空时可回退，避免用户收纳数据丢失。
        try:
            (path.with_suffix(".json.bak")).write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


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
        ensure_icon(entry)
        # "吃掉"语义：桌面快捷方式（.lnk/.url）入库后从桌面移除，导出时可按原目标还原。
        # 普通文件/exe 只按引用收纳，不移动不删除（exe 拖离同目录会缺 DLL，文档类交还用户管理）。
        desktop = _desktop_dir()
        suffix = target.suffix.lower()
        if suffix in (".lnk", ".url") and desktop and target.parent == desktop:
            entry["original_target"] = (_lnk_target(target) if suffix == ".lnk" else _url_target(target)) or str(target)
            try:
                target.unlink(missing_ok=True)
                entry["consumed"] = True
            except Exception:
                entry["consumed"] = False
        _write(items)
        return entry


def remove_item(item_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        items = [item for item in _read() if item.get("id") != item_id]
        _write(items)
        return items


def set_category(item_id: str, category: str) -> list[dict[str, Any]]:
    category = category.strip()
    if not category or len(category) > 12:
        raise ValueError("分类名称需为 1-12 个字符")
    with _LOCK:
        items = _read()
        for item in items:
            if item.get("id") == item_id:
                item["category"] = category
        _write(items)
        return items


def export_shortcut(item_id: str) -> dict[str, Any]:
    import subprocess

    items = {item.get("id"): item for item in list_items()}
    item = items.get(item_id)
    if not item:
        raise ValueError("收纳箱中找不到该条目")
    target = Path(str(item.get("path", "")))
    original = str(item.get("original_target") or "")
    desktop = _desktop_dir() or Path.home() / "Desktop"
    name = Path(str(item.get("name") or target.name)).stem
    # .url 快捷方式还原：优先读存量 .url 文件里的 URL；已吃掉的用记录的原始目标。
    url: str | None = None
    if target.exists() and target.suffix.lower() == ".url":
        url = _url_target(target)
    elif original.lower().startswith(("http://", "https://")):
        url = original
    if url:
        restored = desktop / (name + ".url")
        restored.write_text("[InternetShortcut]\nURL=" + url + "\n", encoding="utf-8")
        return {"shortcut": str(restored)}
    if not target.exists():
        if not original or not Path(original).exists():
            raise ValueError("原始文件已不存在")
        target = Path(original)
    lnk = desktop / (name + ".lnk")
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('" + str(lnk) + "'); "
        "$s.TargetPath='" + str(target) + "'; "
        "$s.WorkingDirectory='" + str(target.parent) + "'; $s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=20, creationflags=0x08000000)
    return {"shortcut": str(lnk)}


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
