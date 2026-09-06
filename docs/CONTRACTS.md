# CONTRACTS.md — 接口契约（单一事实源）

> AI 实现任何模块前，先确认本文件里的类型/接口签名。新增接口必须在这里登记。

## C1 前端 `Live2d` 单例（`src/core/live2d.ts`）

```ts
export interface ModelExpression {
  name: string;
  file: string;
}

export interface ModelMeta {
  width: number;
  height: number;
  motions: Record<string, unknown[]>;        // 动作组，键为组名（如 Idle / TapBody），值为该组动作定义数组
  expressions: ModelExpression[];            // 表情（name 取自 .exp3.json 的 Name）
}

export type PetPose =
  | 'idle' | 'walk' | 'lie' | 'kneel' | 'duck-sit'
  | 'happy' | 'angry' | 'cute' | 'surprised' | 'sleepy';

// 约束：walk/lie/kneel/duck-sit 是基于当前模型参数的参数化表现；只有资源实际声明的
// .motion3.json 才可作为原生动作播放，不得伪造不存在的 Live2D 动作文件。

export class Live2d {
  private app: Application | null = null;   // PIXI.Application
  private model: Live2DModel | null = null; // pixi-live2d-display 实例

  initApp(canvas: HTMLCanvasElement): void;                 // backgroundAlpha:0, resizeTo:window, resolution:devicePixelRatio
  async load(path: string): Promise<ModelMeta>;             // 扫描 .model3.json；资源路径经 convertFileSrc 转 asset://
  destroy(): void;                                         // 必须彻底释放，防内存泄漏
  resizeModel(size: ModelMeta): void;                      // 缩放居中
  // ── 渲染/驱动 ──
  async playMotion(group: string, index: number): Promise<void>;
  async playExpressions(index: number): Promise<void>;
  getParameterRange(id: string): { min: number; max: number };
  setParameterValue(id: string, value: number | boolean): void;
  // ── M2 互动 ──
  hitTest(x: number, y: number): string[];                 // 返回命中的 hit area 名称数组（model3.json HitAreas.Name）
  containsPoint(x: number, y: number): boolean;            // 精确命中：点是否落在模型不透明轮廓内
  getBounds(): { x: number; y: number; width: number; height: number }; // world-space 包围盒
  getPosition(): { x: number; y: number };                 // 模型中心点（world space）
  setPosition(x: number, y: number): void;                 // 在画布内设置模型中心点
  getMotionGroups(): string[];                             // 列出所有动作组名
  async playMotionRandom(group: string): Promise<void>;    // 随机播组内某动作
  async playExpressionRandom(): Promise<void>;             // 随机播表情
  applyPose(pose: PetPose, durationMs?: number): void;     // 参数化姿态/情绪，平滑进入并自动回落
  get zoom(): number;                                      // 相对初始 contain 尺寸的缩放
  setZoom(z: number): void;                                // [0.35, 3]，浏览器预览使用；桌面端由窗口尺寸配合
}
```

约束：
- `load` 接受**任意** `.model3.json` 目录，不写死模型名（见 DECISIONS D3）。
- `destroy` 后必须从 PIXI stage 移除并 `model.destroy()`，否则切换模型内存上涨。
- **坐标语义**：`hitTest`/`containsPoint` 入参均为 **world space（canvas CSS 像素）**。
  `Live2DModel.hitTest` 内部已调 `toModelPosition()` 自行转换，**调用方不要重复转换**。
- **精确命中约定**：互动判定应为 `hitTest(x,y).length > 0 || containsPoint(x,y)`；`containsPoint` 只能基于模型不透明区域，禁止使用完整包围盒。
  原因：Hiyori 的 HitAreas 仅 `Body` 一个且边界紧，但透明区域也不能拦截桌面鼠标。
- **拖动与互动不互斥**：`onPointerDown` 里判定互动后**仍要调** `startDragging()`，
  保证任意位置都能拖动窗口（点在模型上也能拖着走）。

## C2 WebSocket 消息协议（前端 ↔ 后端）

```ts
// 前端 → 后端
type ClientMsg =
  | { type: 'ping' }
  | { type: 'audio-chunk';   data: number[] }       // 采样率固定 16000，M3 后续（JSON 传输，二进制帧待优化）
  | { type: 'audio-end' }
  | { type: 'text-input';    text: string; image?: string }
  | { type: 'interrupt' }
  | { type: 'switch-character'; confUid: string };

// 后端 → 前端
type ServerMsg =
  | { type: 'pong' }
  | { type: 'ai-response';   text: string; audio?: string; volumes?: number[]; emotion: string }
  | { type: 'transcription'; text: string }
  | { type: 'tool-status';   tool: string; status: string }
  | { type: 'error';         message: string };
```

约束：
- 音频采样率全局固定 **16000 Hz**（见 AGENTS.md 规则 10）。
- `ai-response.text` 为**流式增量（delta）**，前端按会话累加为完整字幕。
- `ping`/`pong` 用于心跳保活，前端每 15s 发一次 `ping`。

## C3 后端能力接口（`backend/*/`）—— 工厂 + Protocol 模式

```python
# backend/asr/asr_interface.py
class ASRInterface(Protocol):
    async def transcribe_np(self, audio: np.ndarray) -> str: ...

# backend/llm/llm_interface.py
class LLMInterface(Protocol):
    async def chat_iter(self, messages: list[dict]) -> AsyncIterator[str]: ...

# backend/tts/tts_interface.py
class TTSInterface(Protocol):
    async def generate_audio(self, text: str, **kwargs) -> tuple[str, list[float]]:
        """返回 (音频文件路径, 逐帧音量包)。音量包用于口型同步。"""
        ...
```

约束：
- 每个能力通过 `*_factory.py` 实例化，配置驱动（`conf.yaml`）。
- 新增后端只改 `conf.yaml` + 注册到工厂，不动业务调用方。

## C4 配置 schema（`backend/conf.yaml` + `config_manager/`）

- 用 Pydantic 校验，启动时校验失败即退出。
- 支持 `${ENV_VAR}` 环境变量替换。
- LLM 默认项示例（见 DECISIONS D4）：
  ```yaml
  llm_configs:
    foxtoken:
      provider: openai-compatible
      base_url: https://foxtoken.top/v1
      api_key: ${FOXTOKEN_KEY}
      model: gpt-5.5
  ```
- 密钥只走环境变量，**不写进仓库**。

## C4 桌宠扩展动作事件（前端窗口 API）

外部脚本或后续 API 适配器可调用 `window.petApi?.dispatch(action)`，不直接依赖 Live2D 实例：

```ts
type PetApiAction =
  | { type: 'motion'; group: string }
  | { type: 'face'; name: 'smile' | 'surprise' | 'blush' | 'wink' }
  | { type: 'say'; text: string };
```

动作/表情不在设置面板展示，由场景、状态、空闲行为或此扩展事件触发。未知动作组静默忽略。

## C5 桌面发布与后端 sidecar 生命周期

```text
Tauri resource: $RESOURCE/backend/pet-backend.exe
WebSocket:       ws://127.0.0.1:8000/ws
Health:          GET http://127.0.0.1:8000/health
```

约束：
- `backend/main.py` 是 PyInstaller 入口；发布构建使用 `--onefile --noconsole`，`conf.yaml` 必须作为数据文件打入。
- Tauri 启动时由 `src-tauri/src/backend.rs` 启动 sidecar，并传入 `PET_PARENT_PID=<Tauri PID>`；禁止要求用户手动启动 Python/Uvicorn。
- 正常退出时 Tauri 必须终止整个 sidecar 进程树；Tauri 崩溃或被强制结束时，sidecar 的父进程监视器必须自行退出。
- `/health` 返回 `{ "status": "ok", "llm": "remote" | "local" }`。没有 `FOXTOKEN_KEY` 或远端调用失败时，文本消息仍返回 `ai-response`，使用本地陪伴回复，不把桌宠降级成不可用错误页。
- 前端允许在 sidecar 解压启动期间短暂重连；发布包不得依赖 Vite `devUrl` 或端口 1420。

## C6 单实例、隐藏与运行时 API 配置（2026-09-05）

### Windows 单实例
- 同一用户会话只允许一个 `HiyoriPet` 进程；再次启动不得创建第二只宠物。
- 第二次启动要唤醒既有窗口并触发 `pet-opened`，不得再启动第二个后端 sidecar。
- 托盘必须同时提供“显示宠物”和“隐藏宠物”；聊天气泡内保留明确的“隐藏桌宠”入口。

### 桌宠窗口与聊天气泡
- 右键打开 API 面板后，桌宠窗口位置和游走目标冻结；关闭面板后恢复行为计时。
- 桌面游走边界使用当前显示器 `workArea` 与窗口外部尺寸计算，目标位置必须保证整个窗口留在工作区内。
- 滚轮缩放使用单一待处理目标与 `requestAnimationFrame` 合帧；同一帧最多提交一次原生窗口尺寸更新，缩放期间保持人物 contain 可见。
- 聊天气泡只包含日和的对话、输入和隐藏桌宠命令，不显示 API 状态或 API 管理按钮。
- 气泡锚定模型头部上方，按左右剩余空间选择方向，并限制在窗口视口内；打开约 3 秒后缓慢淡出。输入、发送、回复流式更新期间保持可见。

### API 配置
本地后端提供：
```text
GET  /api/config  -> { configured, protocol, base_url, model, source }
POST /api/config  <- { protocol, base_url, api_key, model }
                   -> { configured, protocol, base_url, model, source }
DELETE /api/config -> 清除用户配置并回到本地模式
POST /api/discover <- { protocol, base_url, api_key }
                    -> { connected, protocol, base_url, models: [{ id, name, owned_by? }], error? }
POST /api/test     <- { protocol, base_url, api_key, model }
                    -> { connected, latency_ms?, model, error? }
GET  /api/models   -> { models: [{ id, name, protocol, base_url, enabled, role }] }
POST /api/models  <- { models: [{ id, name, protocol, base_url, api_key?, enabled, role }] }
                    -> { models: [{ id, name, protocol, base_url, enabled, role }] }
GET/POST /api/collaboration
                    -> { enabled, strategy, judge_model_id?, model_ids[] }
```
- `protocol` 支持 `openai-compatible`、`anthropic-messages`、`gemini`；`base_url` 与 `model` 由用户填写，不绑定供应商名单，兼容对应协议的官方地址及中转地址。
- API key 不回传前端、不进仓库；Windows 发布版使用当前用户 DPAPI 加密后写入 `%APPDATA%/HiyoriPet/api.json`。
- `/api/discover` 优先使用协议对应的模型列表端点，不发送生成请求；不支持发现的中转必须返回可读错误，不伪造模型列表。
- `/api/test` 是显式用户操作，可能产生一次计费请求；前端在按钮旁明确提示，后端不记录或返回密钥。
- API key 不回传前端、不进仓库；Windows 发布版使用当前用户 DPAPI 加密后写入 `%APPDATA%/HiyoriPet/api.json`。多模型配置同样只保存加密密钥。
- 启用多个模型时，`strategy=parallel` 表示并行生成后合并文本；`strategy=fallback` 表示按启用顺序故障转移；未启用协作时只使用当前主模型。
- 未配置 API 时，WS 在本地回复前发送 `{ type: "api-status", configured: false, message }`；远端调用失败时发送同类型状态并回退本地回复。
- 前端聊天气泡不显示 API 状态；API 状态、发现结果、连接测试和模型启停只在右键 API 面板中展示。

## C7 识别、导入与场景路由（2026-09-06）

`/api/discover` 返回的模型可以带能力标记；未知能力必须保守标为 `text`，不能伪造视觉能力：
```json
{ "id": "model-id", "name": "…", "owned_by": "…", "capabilities": ["text", "vision"] }
```

模型目录扩展字段：
```ts
type ModelCapability = 'text' | 'vision' | 'audio';
type ModelTask = 'chat' | 'vision' | 'scene';
interface ModelProfile {
  id: string; name: string; protocol: string; base_url: string;
  enabled: boolean; role: 'primary' | 'worker' | 'judge';
  capabilities: ModelCapability[]; tasks: ModelTask[];
}
```
- 识别结果提供“全部启用并启动”和“取消本次识别”；前者导入识别到的模型、启用协作并立即成为运行目录，后者只撤销本次未保存的识别结果。
- API 面板支持导入 JSON 模型配置；导入只接受 `models` 数组和可选 `collaboration`，API key 仍只在本地 DPAPI 加密保存。
- WebSocket `text-input` 可带 `image`（data URL）和 `task`：`chat`、`vision`、`scene`。带图片时前端必须使用 `vision`。
- OpenAI-compatible、Anthropic Messages、Gemini 适配器都要把图片转为各自官方请求格式；不支持图片的模型不能被路由到视觉任务。
- 多模型协作按任务路由：只选 `enabled=true` 且声明该 task 的模型；无匹配时才回退到全部启用模型。`fallback` 按主模型/协作顺序尝试，`parallel` 并行汇总。

## C8 应用收纳箱（2026-09-06）
- 存储：`%APPDATA%/HiyoriPet/box.json`，条目 `{ id, name, path, category, added_at }`；不含密钥类敏感信息。
- REST：
  - `GET /api/box` → `{ items: [...] }`
  - `POST /api/box` ← `{ path, name? }` → `{ item }`（路径不存在报 400；重复路径返回已存在条目）
  - `DELETE /api/box/{id}` → `{ items }`
  - `POST /api/box/launch` ← `{ id }` → `{ launched }`（原始文件不存在报 400）
- 分类启发式：游戏 / 浏览器 / 影音图片 / 办公文档 / 工具应用 / 文件夹（按文件名关键词与扩展名）。
- 交互：长按宠物 650ms 打开收纳箱面板；拖拽文件/快捷方式投放到日和身上触发“吃掉”入库并播报分类；面板内可打开（`os.startfile`）或删除条目。
- 前端扩展事件：`window.petApi.dispatch({ type: 'box-add', path })` 与拖喂同链路，供脚本冒烟。

## C8 补充（2026-09-06 晚）
- `PUT /api/box/{id}` ← `{ category }` → `{ items }`：用户自主改分类（1-12 字）。
- `POST /api/box/export` ← `{ id }` → `{ shortcut }`：在桌面生成 `.lnk` 快捷方式（PowerShell WScript.Shell COM）。
- `POST /api/box` 在已接入 API 时先启发式分类、再请模型复核分类（6s 超时，失败回退启发式）；响应始终为 `{ item: 单条目 }`。
- 拖喂命中判定使用 CSS 像素（拖放坐标按 devicePixelRatio 换算），投放到收纳箱面板内同样接收入库；拖入悬停时日和给出惊讶反馈。

## C8 补充 2：右键长按开箱与头部锚定气泡（2026-09-06）
- 收纳箱打开方式改为**右键长按 650ms**；原"左键长按 650ms"逻辑删除。右键短按（<650ms）行为不变：收纳箱开着时关闭收纳箱，否则切换 API 面板。
- 右键长按触发后必须吞掉随后的 `contextmenu`（`rightLongPressFired` 标志），防止长按开箱后又弹出 API 面板；右键按下后移动 >7px 视为取消。
- 消息气泡只允许出现在日和头部左侧或右侧：水平位置锚定模型**不透明区域顶部带（包围盒顶部 32%）**的左右边缘（`headAnchor()`），垂直中心对准头部带中心，箭头指向头部；删除原 top/bottom 回退分支。
- 已修复 bug：侧边扩展窗口向左扩展（side='left'）时，气泡原实现固定写在 `baseWidth/dpr+8`，会直接压在人物身上；现按扩展列方向锚定头部边缘。
- 拖喂：`enter/over` 时日和眼睛跟随光标（`pet.focus`）+ 张嘴（surprised 姿态，150ms 节流）+ 光标处反馈标记（700ms 节流）；`drop` 支持一次吃掉多个文件（`Promise.allSettled` 逐个入库），成功后"张嘴接住(650ms)→开心咀嚼→播报"。
- "吃掉"语义扩展到桌面 `.url` 快捷方式：`original_target` 记录 URL，导出时以 `[InternetShortcut]` INI 还原 `.url`；`.exe`/普通文件仍只按引用收纳，不移动不删除（避免拖离同目录缺 DLL）。
