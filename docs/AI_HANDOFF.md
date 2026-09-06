# HiyoriPet / 日和桌宠 —— AI 开发交接手册

> 目的：把当前项目交给下一位 AI 继续开发。本文以仓库实际文件、Git 历史和已记录的验证结果为依据；没有重新执行的测试，不在本文中伪装成“本轮已通过”。
>
> 当前核对日期：**2026-09-06（中国标准时间）**。

## 1. 项目与仓库

- 项目：Windows PC 高互动桌宠 **HiyoriPet / 日和桌宠**。
- 当前工作目录：`D:\codex\pet-next`。
- GitHub 开发仓库：`pengzexi79-ops/hiyoripet`。
- 当前分支：`master`。
- 当前 HEAD：`d56b9b0b61ba50fb0f0d4c59312bbd297173786b`，提交时间为 **2026-09-06 13:56:08 +08:00**。
- 本次交接前已核对：本地 `master` 与 `origin/master` 一致，工作区干净。
- 旧版冻结存档：`D:\codex\pet`，对应仓库 `hiyoripet-archive`，标签 `archive/hiyoripet-0.1.3`。
- 本仓库是公开仓库；公开前仍需自行确认 Live2D 样例模型和 Cubism Core 的授权范围。

## 2. 最近进展（以 2026-09-06 为截止）

### 最新提交序列

1. `98d4bb6`：从旧项目 `pet` 导入 HiyoriPet 0.1.3，作为新开发仓库起点。
2. `d46c8cc`：修复缩放、点击稳定性和 API 面板滚动，版本推进到 0.1.4。
3. `ed2f8dd`：加入应用收纳箱 MVP，支持长按打开、拖拽喂入和收纳数据接口；修复缩放裁剪伪影。
4. `88222d5`：加入模型目录/公开仓库方向、缩放上限与整区缩放、收纳箱 AI 分类/改分类/导出、步态与跳跃。
5. `d56b9b0`：加入侧边扩展列布局、Win32 命中区域自愈、桌面快捷方式吞噬/恢复、图标卡片、弹簧摆动和收纳数据备份。

### 当前已实现的可交付能力

- Tauri 2 透明桌面窗口，Vue 3 + TypeScript + PIXI.js + Live2D 渲染。
- FastAPI 后端与前端 WebSocket 文本通道；无 API key 时有本地规则回复。
- OpenAI-compatible、Anthropic Messages、Gemini 配置入口；模型发现、连接测试、多模型目录与协作策略已接入代码。
- Hiyori 模型点击互动、拖拽、空闲动作、滚轮缩放、步态、跳跃、参数化表情和弹簧摆动。
- 右键 API 面板；聊天气泡；隐藏/恢复；托盘退出；单实例唤醒。
- 应用收纳箱：长按 650ms 打开；拖入桌面 `.lnk` 会“吃掉”快捷方式并记录原目标；按类别显示图标卡片；可打开、删除、改分类、导出桌面快捷方式。
- 收纳数据写入 `box.json` 时保留 `box.json.bak`；主文件读取失败时回退备份。
- 侧边面板与气泡统一申请扩展空间，避免覆盖人物；命中区域失败会重试并定时自愈。

## 3. 历史阶段与关键问题

- **M0**：Tauri 2 透明窗口、托盘、拖拽和 GNU 编译链。
- **M1**：Live2D Cubism 4 Hiyori 渲染与模型加载。
- **M2**：命中测试、点击动作、拖动和空闲自播。
- **M3**：FastAPI + WebSocket + LLM/TTS/ASR 工厂；当前文本通道可用，真实语音链路未完成。
- **M4**：收敛桌宠 UX，隐藏调试 HUD，聊天气泡、API 配置、缩放和主动行为。
- **M5**：PyInstaller 后端 sidecar、Tauri Release/NSIS、自动启动与回收、桌面游走。
- **0.1.4 后续**：收纳箱、模型识别/导入、场景路由、多模型协作、动态缩放区域、步态和数据保护。

曾定位并修复的典型问题：

- 每帧 WebGL 回读和 GDI `CombineRgn` 造成缩放卡顿；改为缓存/降频、批量区域和缩放期间整窗命中区域。
- `SetWindowRgn` 去抖滞后导致透明窗口旧区域裁剪人物，表现为乱码、条带或点击失效；改为缩放中同步、静止后恢复精确区域。
- Hiyori 实际只有紧范围 `HitArea:Body`，造成“点不动”；增加模型包围盒兜底，且点击与拖动不再互斥。
- API 面板的 `input { width: 100% }` 泄漏到复选框，造成逐字换行和大片空白；已恢复复选框宽度并限制内部滚动。
- TTS/LLM/ASR 工厂曾按配置标签而非内部 `provider` 分发，造成 `edge`/`edge-tts` 不匹配；现在按 `cfg.provider` 分发。
- 收纳箱 AI 分类返回值曾把单条目覆盖成列表，导致播报 `undefined`；已修复并固定响应为单条目。
- 桌面快捷方式路径不能猜测为 `Path.home()/Desktop`；Windows 侧应使用 `SHGetFolderPath(CSIDL_DESKTOP)`。

## 4. 架构与工作逻辑

```text
Vue 表现层
  -> 交互/状态层
  -> Live2D 渲染单例 + Tauri 窗口 API
  -> WebSocket Client
  -> FastAPI ServiceContext
  -> ASR / Agent / LLM / TTS / SQLite(预留)
```

核心边界：后端不操作窗口，前端不做模型推理；外部能力必须经接口和工厂；配置由 Pydantic 校验；前后端唯一长期耦合点是 WebSocket 和已记录 HTTP 契约。

主要数据流：

- 文本：输入框 → `text-input` → 后端 Agent → 本地回复或 LLM 流式 delta → 前端字幕/气泡。
- 图片：用户显式发图 → 按协议转换为 image data URL → vision 模型；没有隐式采集键盘、文件或浏览内容。
- 收纳：拖放/`petApi.dispatch({ type: 'box-add', path })` → 后端分类与保存 → 桌面 `.lnk` 按规则移除 → UI 卡片；导出时按原目标重建快捷方式。
- 桌宠行为：点击、拖拽、缩放、焦点/可见性和空闲计时器进入行为仲裁；动作、表情、窗口移动和气泡不能互相覆盖人物区域。
- 发布：`HiyoriPet.exe` → Tauri 启动资源中的 `pet-backend.exe` → `127.0.0.1:8000` → 前端连接 `ws://127.0.0.1:8000/ws`。

## 5. 目录与单一事实源

- `src/App.vue`：当前主 UI、交互、面板与窗口行为编排。
- `src/core/live2d.ts`：Live2D 单例、模型加载、参数/动作/命中区域。
- `src/core/api.ts`：HTTP API 类型与调用。
- `src/core/ws.ts`、`src/core/chat.ts`：WebSocket 与聊天流。
- `backend/server.py`：FastAPI 路由和 WebSocket 入口。
- `backend/service_context.py`：配置、API、模型与能力服务编排。
- `backend/box_store.py`：收纳箱持久化、分类、图标、桌面快捷方式与备份。
- `backend/api_provider.py` / `api_catalog.py`：多协议模型连接、发现和测试。
- `src-tauri/src/lib.rs`：窗口、缩放、Win32 命中区域、单实例、sidecar 生命周期。
- `docs/CONTRACTS.md`：接口契约唯一事实源。
- `docs/ARCHITECTURE.md`：分层和目录事实源。
- `docs/DECISIONS.md`：已拍板的架构/工具链/授权决策。
- `docs/PROGRESS.md`：历史进度记录；其中末尾含有 **2026-09-07** 的未来日期段落。当前日期是 2026-09-06，接手 AI 不得把该段当作已发生事实，应先核对 Git 提交和真实测试时间。
- `AGENTS.md`：原项目 AI 协作约束，尤其是契约优先、最小改动、验收门禁、增量提交和不得臆造。

## 6. 已知限制、风险和待办

### 必须优先处理

1. `start-pet.js` 仍把 `PET` 写死为 `D:\codex\pet`，不适用于本仓库；继续开发前应改为 `D:\codex\pet-next` 或改成可靠的脚本目录自发现。
2. `public\models` 和 `public\cubism-core` 被 `.gitignore` 忽略，当前本机存在但不在 Git HEAD；干净克隆不能保证直接运行 Live2D。应制定合法的资产获取/安装步骤，不要把未经确认的受限资产直接公开提交。
3. `release\`、`_verification\`、PyInstaller 构建目录和安装器缓存均被忽略；GitHub 当前是源码仓库，不是二进制发布页。若需要分发安装包，应另做 GitHub Release 并先核对资源授权与文件大小。
4. 当前没有把真实 `FOXTOKEN_KEY` 写入仓库，也没有在本轮进行付费模型调用；真实云端模型、真实 TTS/ASR 仍需用户明确配置并在真机验证。
5. 当前交接只确认源码 HEAD 与远程一致，没有重新执行全套构建；下一位 AI 需在自己的环境重新跑门禁。

### 后续路线

- 修正启动脚本和全新克隆的资源安装/恢复流程。
- 在 Windows 真机复核透明角点穿透、点击、拖拽、缩放极限、多显示器、托盘退出、单实例和 sidecar 回收。
- 完成真实 ASR → Agent → LLM → TTS → 音频播放/音量口型链路；当前 ASR 默认是 stub，TTS 默认关闭。
- 补齐 SQLite 记忆、人格、主动行为的长期策略与隐私开关。
- 为收纳箱补充搜索、用户自定义分类、拖出还原、异常路径和快捷方式权限错误处理。
- 解决模型资产、协议适配、错误提示和 Release 产物的可重复安装问题。
- 公开仓库继续只提交源代码和合法文档；不要提交 API key、个人配置、`box.json`、用户桌面路径快照或本机生成的凭据。

## 7. 环境、工具链和命令

- Windows x64；所有实质开发和运行放在 D 盘。
- Node/pnpm：优先使用已安装的 `D:\node-global\pnpm.cmd`；若 PATH 没有 `node`，使用工作区 bundled Node：`C:\Users\Windows\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`。
- Rust：`stable-x86_64-pc-windows-gnu`，target 为 `x86_64-pc-windows-gnu`。
- MinGW-w64：共享 `D:\codex\pet\.mingw\bin` 和 `D:\codex\pet\.mingw\x86_64-w64-mingw32\bin`；本机不能依赖 MSVC/Visual Studio 安装器。
- 后端历史构建使用 `D:\codex\pet\backend\.venv`；新仓库后续应建立自己的 venv，依赖清单在 `backend\requirements.txt`。

建议在 `D:\codex\pet-next` 执行：

```powershell
pnpm install
pnpm exec tsc --noEmit
pnpm build
python -m compileall backend
cargo check --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-gnu
pnpm tauri build --target x86_64-pc-windows-gnu --bundles nsis
```

若 `pnpm`、`python` 或 `cargo` 不在 PATH，不要猜路径；使用本机已验证的绝对路径，并把真实输出记录到交接文档或提交说明。Tauri GNU 构建可能出现已知的非致命 MinGW `.rsrc merge failure` 警告，但必须确认最终退出码和产物。

## 8. 验证门禁与证据规则

- TypeScript：`pnpm exec tsc --noEmit`。
- 前端构建：`pnpm build`。
- Python：`python -m compileall backend`，再做后端 `/health` 与 WS `ping → pong` 冒烟。
- Rust：GNU target `cargo check`。
- Windows 产物：Tauri GNU Release NSIS；确认资源 sidecar、端口、父子进程回收。
- UI/Win32：必须保存真实截图或脚本输出，区分“代码存在”“构建通过”“桌面真机可见”“用户实际验证”。
- 提交前：`git diff --check`；扫描 API key、token、密码、`.env`、用户数据和本机路径快照；只提交有意修改的文件。
- 推送前：`git fetch origin`、检查远程分支差异；正常合并/变基，禁止 `force-push`、`reset --hard`、无确认的清理工作树。

## 9. 配置、密钥与授权边界

- `backend/conf.yaml` 中 `FOXTOKEN_KEY` 只通过环境变量占位符读取，不能写入源码、日志、Markdown 或 GitHub。
- 桌面 API 配置保存到当前用户 `%APPDATA%\HiyoriPet\api.json`，设计上使用 Windows DPAPI 密文；API key 不回传前端。
- 不要要求用户把 GitHub 密码粘贴到聊天。Git 操作优先复用已授权的 `gh`/凭据管理器，或使用短期、最小权限 token；不要把 token 写入 remote URL、脚本或日志。
- Hiyori 等 Live2D/Cubism 样例资产的代码可验证不等于拥有公开分发权；发布前必须重新核对官方许可，不能在 README 中声称已获商用授权。

## 10. 下一位 AI 的首次接手清单

1. 先读本手册、`AGENTS.md`、`docs/PROGRESS.md`、`docs/CONTRACTS.md`、`docs/ARCHITECTURE.md`、`docs/DECISIONS.md`。
2. 运行 `git status --short --branch`、`git log --oneline -8`、`git remote -v`，确认没有误切到旧项目。
3. 检查资源是否存在：`public\models\Hiyori\Hiyori.model3.json` 和 `public\cubism-core\live2dcubismcore.min.js`；缺失时走合法安装流程，不从聊天或未知来源复制。
4. 在不带真实 key 的本地模式下跑 TypeScript、Vite、Python、Cargo 门禁，再决定是否做真机启动。
5. 先修复 `start-pet.js` 的仓库路径问题，再做真实桌面验收。
6. 每次只做一个可验收子任务：先改契约/文档，再改实现；跑门禁；写清失败和环境；小步提交并推送。
7. 任何涉及 API 付费调用、公开资源、删除桌面快捷方式、修改用户数据或发布安装包的动作，都要先取得明确授权。

**交接结论：**当前源码最新状态已在 GitHub 开发仓库 `pengzexi79-ops/hiyoripet` 的 `master` 上；本次新增本文件用于后续 AI 接手。源码上传不等于全新克隆可直接运行，优先补齐启动脚本和受许可约束的 Live2D 资源恢复方案。
