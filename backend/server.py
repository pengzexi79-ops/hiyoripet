# FastAPI + WebSocket conversation service (contracts C2/C6).
import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import box_store
from service_context import get_service_context

app = FastAPI(title="pet-backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
DEFAULT_SYSTEM = "你是桌面上的一只高互动陪伴桌宠，性格活泼、话少而精。用简体中文，每次回复不超过 60 字。"


class ApiConfigInput(BaseModel):
    protocol: str
    base_url: str
    api_key: str = ""
    model: str


class DiscoverInput(BaseModel):
    protocol: str
    base_url: str
    api_key: str = ""


class TestInput(DiscoverInput):
    model: str


class ModelInput(BaseModel):
    id: str
    name: str = ""
    protocol: str = "openai-compatible"
    base_url: str
    api_key: str = ""
    enabled: bool = True
    role: str = "worker"
    capabilities: list[str] = ["text"]
    tasks: list[str] = []


class ModelsInput(BaseModel):
    models: list[ModelInput]


class BoxAddInput(BaseModel):
    path: str
    name: str = ""


class BoxLaunchInput(BaseModel):
    id: str


class BoxCategoryInput(BaseModel):
    category: str


class CollaborationInput(BaseModel):
    enabled: bool = False
    strategy: str = "fallback"
    judge_model_id: str | None = None
    model_ids: list[str] = []


def _system_prompt() -> str:
    return get_service_context().config.agent.get("system_prompt") or DEFAULT_SYSTEM


def _local_reply(text: str, degraded: bool = False) -> str:
    normalized = text.strip().lower()
    if any(word in normalized for word in ("你好", "嗨", "hello", "hi")):
        return "你好呀，我是日和～今天也会在桌面上陪着你。"
    if any(word in normalized for word in ("时间", "几点", "日期", "今天几号")):
        return f"现在是 {datetime.now():%Y年%m月%d日 %H:%M}，别忘了休息一下呀。"
    if any(word in normalized for word in ("累", "困", "烦", "难过", "不开心")):
        return "辛苦啦。先慢慢呼吸一下，我会安静陪着你，也可以再和我说说。"
    if any(word in normalized for word in ("谢谢", "再见", "晚安")):
        return "不用客气～我就在桌面边上，想我时再点一下。"
    if degraded:
        return "API 暂时连接失败，我先用本地陪伴模式陪你。请在右键 API 设置中检查配置。"
    return "我听见啦～现在是本地陪伴模式。可以在右键 API 设置中接入模型。"


def _status_message(status: dict, healthy: bool | None = None) -> dict:
    data = {"type": "api-status", **status}
    if not status["configured"]:
        data["message"] = "当前未接入 API，正在使用本地陪伴模式。"
    elif healthy is False:
        data["message"] = "API 调用失败，请检查接口地址、密钥和模型名称。"
    return data


@app.get("/health")
async def health():
    status = get_service_context().api_status()
    return {"status": "ok", "llm": "remote" if status["configured"] else "local"}


@app.get("/api/config")
async def get_api_config():
    return get_service_context().api_status()


@app.post("/api/config")
async def save_api_config(payload: ApiConfigInput):
    try:
        return get_service_context().save_api(payload.protocol, payload.base_url, payload.api_key, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/config")
async def delete_api_config():
    return get_service_context().clear_api()


@app.post("/api/discover")
async def discover_api_models(payload: DiscoverInput):
    try:
        return await get_service_context().discover(payload.protocol, payload.base_url, payload.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/test")
async def test_api_connection(payload: TestInput):
    try:
        return await get_service_context().test_connection(payload.protocol, payload.base_url, payload.api_key, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/models")
async def get_model_catalog():
    return {"models": get_service_context().public_models()}


@app.post("/api/models")
async def save_model_catalog(payload: ModelsInput):
    try:
        models = [item.model_dump() for item in payload.models]
        return {"models": get_service_context().save_models(models)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/collaboration")
async def get_collaboration():
    return get_service_context().collaboration()


@app.post("/api/collaboration")
async def save_collaboration(payload: CollaborationInput):
    try:
        return get_service_context().save_collaboration(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/box")
async def get_box():
    return {"items": box_store.list_items()}


@app.post("/api/box")
async def add_box_item(payload: BoxAddInput):
    try:
        item = box_store.add_item(payload.path, payload.name)
        sc = get_service_context()
        if sc.api_status().get("configured"):
            async def _classify() -> str:
                prompt = (
                    "请把下面这个应用/文件归入一个简洁的中文分类（不超过6字，例如：游戏/办公文档/影音图片/工具应用/学习资料），"
                    f"只回复分类名本身。名称={item['name']} 路径={item['path']} 参考分类={item['category']}"
                )
                acc = ""
                async for piece in sc.chat_iter([{"role": "user", "content": prompt}], "scene"):
                    acc += piece
                return acc.strip()

            try:
                answer = await asyncio.wait_for(_classify(), 6)
                cat = answer.splitlines()[0].strip() if answer else ""
                if 0 < len(cat) <= 8:
                    updated = box_store.set_category(item["id"], cat)
                    item = next((entry for entry in updated if entry.get("id") == item["id"]), item)
            except Exception:
                pass
        return {"item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/box/{item_id}")
async def update_box_category(item_id: str, payload: BoxCategoryInput):
    try:
        return {"items": box_store.set_category(item_id, payload.category)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/box/export")
async def export_box_item(payload: BoxLaunchInput):
    try:
        return box_store.export_shortcut(payload.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/box/{item_id}")
async def delete_box_item(item_id: str):
    return {"items": box_store.remove_item(item_id)}


@app.post("/api/box/launch")
async def launch_box_item(payload: BoxLaunchInput):
    try:
        return box_store.launch_item(payload.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    sc = get_service_context()
    await ws.send_json(_status_message(sc.api_status()))
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON 解析失败"})
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await ws.send_json({"type": "pong"})
            elif mtype == "text-input":
                await _handle_text(ws, sc, (msg.get("text") or "").strip(), msg.get("image"), msg.get("task"))
            elif mtype == "audio-end":
                await ws.send_json({"type": "error", "message": "本地 ASR 暂未启用，请先直接输入文字。"})
            elif mtype != "interrupt":
                await ws.send_json({"type": "error", "message": f"未知消息类型: {mtype}"})
    except WebSocketDisconnect:
        pass


async def _handle_text(ws: WebSocket, sc, text: str, image=None, task=None):
    if not text and not image:
        await ws.send_json({"type": "error", "message": "请输入想说的话"})
        return
    task = task if task in {"chat", "vision", "scene"} else "chat"
    if image:
        task = "vision"
        if not str(image).startswith("data:"):
            await ws.send_json({"type": "error", "message": "图片必须是 data URL"})
            return
    for item in sc.history:
        item.pop("image", None)
    user_message = {"role": "user", "content": text or "请看这张图片并简短回应。"}
    if image:
        user_message["image"] = str(image)
    sc.history.append(user_message)
    status = sc.api_status()
    if not status["configured"]:
        await ws.send_json(_status_message(status))
        reply = _local_reply(text)
        sc.history.append({"role": "assistant", "content": reply})
        await ws.send_json({"type": "ai-response", "text": reply, "emotion": "normal"})
        return
    messages = [{"role": "system", "content": _system_prompt()}] + sc.history[-20:]
    try:
        acc = ""
        async for piece in sc.chat_iter(messages, task):
            acc += piece
            await ws.send_json({"type": "ai-response", "text": piece, "emotion": "normal"})
        if not acc:
            raise RuntimeError("empty API response")
        sc.history.append({"role": "assistant", "content": acc})
    except Exception:
        await ws.send_json(_status_message(status, healthy=False))
        reply = _local_reply(text, degraded=True)
        sc.history.append({"role": "assistant", "content": reply})
        await ws.send_json({"type": "ai-response", "text": reply, "emotion": "normal"})
