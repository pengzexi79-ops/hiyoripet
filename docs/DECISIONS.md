# DECISIONS.md — 已拍板的架构与方向决策

> 格式：每条决策一行结论 + 理由 + 影响范围。改决策必须先在此记录并说明，再动代码。

## D1 场景定位：陪伴助手（非直播虚拟形象）
- 理由：文档默认定位；直播分支（虚拟摄像头/透明通道/音频路由）工作量独立，且与 douyin-mixcut 的耦合未确认。
- 影响：M0–M5 前端形态为桌面常驻窗口。直播分支预留为 M5 后可选。
- 状态：待用户最终确认（用户说「据实际开发场景进行」，先按此推进）。

## D2 授权路径：开发期「自用不分发」（A）
- 理由：避免触发 Live2D SDK 发行许可证谈判。开发/测试/自用完全免费、无限制。
- 影响：模型先用官方样例（Hiyori/Shizuku，受 Live2D 免费素材协议约束，**非商用**）；发布前再决定是否开放「用户导入自有模型」（属可扩展性 APP，需单独签约）。
- 红线：严禁在 README/发布物里声称已获商用授权。

## D3 模型来源：官方样例优先，架构预留替换
- 理由：零成本起步、可验证渲染管线；不内置任何受版权角色资源。
- 影响：`src/core/live2d.ts` 的 `load(path)` 必须接受任意 `.model3.json` 目录，不写死模型名。

## D4 AI 后端：默认 foxtoken 网关，支持切本地
- 理由：用户已有 foxtoken.top OpenAI 兼容网关（含 GPT-5 系模型），无需新增账号。
- 配置：`backend/conf.yaml` 的 `llm_configs` 里放 `foxtoken` 项，`base_url=https://foxtoken.top/v1`，模型 `gpt-5.5`。
- 影响：ASR/TTS 仍走本地（sherpa-onnx / Edge TTS），降低延迟与成本；LLM 走云端。
- 密钥：放环境变量 `${FOXTOKEN_KEY}`，**不写进仓库**。
- **配置约定（2026-08-31 修正）**：`backend/conf.yaml` 里 `llm_configs`/`tts_configs`/`asr_configs` 的**顶层键**（如 `foxtoken`/`edge`/`stub`）只是「配置标签」，**不是** provider 类型；真实实现由该配置项内部的 `provider` 字段（如 `openai-compatible`/`edge-tts`/`stub`）决定。`build_llm/build_tts/build_asr` 一律按 `cfg.provider` 分发，配置键可自由命名（避免 `edge` ≠ `edge-tts` 这类 `ValueError`）。

## D5 语音链路：M3 再做
- 理由：ASR/TTS/VAD 约占 40% 工作量，且依赖音频设备调试。
- 影响：M0–M2 只做纯交互 + 文本对话预留（WS 协议里先定义 `text-input` 消息，音频通道留桩）。

## D6 工具链：MinGW-w64（winlibs UCRT64）+ Rust GNU —— 环境强制
- 理由：**沙箱安全策略封死 VS 安装器提权服务**（所有 VS Build Tools 安装均 EXITCODE=138，引导器解压到 `%TEMP%` 后即退出），MSVC 路线在本机不可行。
- 决策：用 winlibs 解压版 MinGW-w64（无需提权）+ Rust `x86_64-pc-windows-gnu` target。
- 工具链位置：`D:/codex/pet/.mingw/bin`（加入 PATH）；Rust target `x86_64-pc-windows-gnu`。
- 影响：
  - 编译命令必须走 GNU（cargo 默认 target 改为 gnu，或每次 `cargo build --target x86_64-pc-windows-gnu`）。
  - Tauri 2 在 windows-gnu 下链接 webview2 是已知风险点，需实测；若 `undefined reference to __imp_*` 类错误填不动，降级 Electron（需用户批准，见 AGENTS.md 环境约束）。
- 状态：**MinGW 已就位 + M0 编译通过**（2026-09-03）。webview2 链接 `undefined reference` 实际未发生，见 D8。

## D8 windows-gnu 编译必踩的 6 个坑（已逐一解决，固化防复发）
- 背景：本机唯一可行工具链 = winlibs MinGW-w64 + Rust `x86_64-pc-windows-gnu`（D6）。以下每一条都是 `cargo build` 实际撞到的硬错，按出现顺序：
  1. **rustup 无默认工具链** → `rustup default stable-x86_64-pc-windows-gnu`（否则 `rustup could not choose a version`）。
  2. **Cargo.toml 在 `src-tauri/` 不在仓库根** → 编译用 `cargo build --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-gnu`（从根跑报 `could not find Cargo.toml`）。
  3. **`generate_context!` 缺前端目录** → 预建 `dist/index.html` 占位（正式前端由 `pnpm build` 生成并覆盖；`dist/` 在 .gitignore）。
  4. **`dlltool.exe` 不在 PATH** → GNU target 用 `dlltool` 给 raw-dylib 生成导入库，rustc 按名调用；把 `.mingw/bin` 与 `.mingw/x86_64-w64-mingw32/bin` 持久化进**用户 PATH**（`.NET SetEnvironmentVariable`，避开 setx 1024 截断），编译命令里也显式 export。
  5. **缺 `icons/icon.ico`** → Tauri 2 在 Windows 生成资源文件强制需要 `icon.ico`；用纯标准库 Python `_installers/make_ico.py` 生成多尺寸 BMP 型 ICO（windres 兼容）。
  6. **`ld.exe: error: export ordinal too large`**（~9 万序数，超 PE 16 位上限）→ MinGW `ld` 默认导出所有静态库符号；在 `.cargo/config.toml` 的 `[target.x86_64-pc-windows-gnu]` 加 `rustflags = ["-C","link-arg=-Wl,--exclude-libs=ALL"]`，只保留 crate 自身显式导出符号。
- 良性告警：`.rsrc merge failure: multiple non-default manifests`（Tauri manifest 与 MinGW 默认 manifest 合并提示），**不影响产物**。
- 决策影响：任何在本机跑 `cargo build`（或 `pnpm tauri build`）的会话，都必须带上述 PATH（MinGW bin）且依赖 `.cargo/config.toml` 的 `rustflags`；新建 crate 同此约束。

## D7 渲染库版本锁定：PIXI **v6** + pixi-live2d-display@0.4.0（禁用 v7/v8）
- 理由：`pixi-live2d-display@0.4.0`（4 年前最后稳定版）的 `peerDependencies` **明确写 `@pixi/core`/`@pixi/display`/`@pixi/loaders`/`@pixi/math`/`@pixi/sprite`/`@pixi/utils` 全为 `^6`**。PixiJS **v7 把这些 `@pixi/*` 拆分包合并进了 `pixi.js` 内部包**，导致 `pixi-live2d-display` 的 `import ... from '@pixi/core'` 在 v7 下**根本解析不到包**，编译/运行期直接崩。v8 更是整体重写，更不可行。
- 决策：前端渲染锁定 **`pixi.js@^6.5.10`** + `pixi-live2d-display@0.4.0`（官方样例 Hiyori 是 Cubism 4，走 `/cubism4` 入口，该子路径 export 在 0.4.0 中确实存在）。
- ⚠️ 早期草拟误写"v6/v7 兼容"，已据 `peerDependencies` 实测纠正为 **仅 v6**。凡涉及 pixi 版本之处一律 v6。
- `new PIXI.Application({ view, backgroundAlpha:0, resizeTo, resolution, antialias, autoStart })` 构造器写法在 v6/v7 通用（v8 才改 `await app.init()`），故 `src/core/live2d.ts` 代码无需为降级 v6 改动。
- Cubism 4 运行时硬依赖：需 `live2dcubismcore.min.js`（Cubism Core）暴露为全局 `window.Live2DCubismCore`，由 `pixi-live2d-display/cubism4` 引用。该文件**不在 GitHub 仓库**（框架仓库仅 75 文件、无 `.min.js`），须从 Live2D 官方 SDK 包（`https://cubism.live2d.com/sdk-web/bin/CubismSdkForWeb-*.zip`，已验证可达）解出的 `CubismWebFramework/Core/live2dcubismcore.min.js` vendoring 到 `public/cubism-core/` 并由 `index.html` 的 `<script>` 在模块脚本前预加载。
- 影响：`package.json` 依赖锁 v6；`src/core/live2d.ts` 按 v0.4.0 API 写（`Live2DModel.from` / `model.motion` / `model.expression` / `model.setParameterValue` / `model.internalModel.coreModel`）。
- 状态：pixi 已就位（pixi.js 6.5.x + pixi-live2d-display 0.4.0），`live2d.ts` 的「待核实」API 正在用 `tsc` 核实并修正。


## D10 桌宠交互收敛（2026-09-04）
- 结论：产品内仅加载 Hiyori（日和），移除角色切换、换衣选项和三条杠菜单；点击宠物直接打开可输入聊天气泡，`pet` 标签随窗口打开显示，取消宠物执行隐藏窗口。
- 结论：滚轮缩放在桌面端同步扩大透明原生窗口，模型按初始 contain 基准放大，避免固定窗口裁剪人物。
- 结论：动作/表情改为随机待机、点击、场景状态或 C4 扩展事件触发，不暴露设置按钮。
- 结论：右键不绑定窗口模式切换，也不注册全局鼠标钩子；交互仅由左键、拖动、滚轮与托盘承担。

## D11 Windows 发布形态：Tauri Release + PyInstaller sidecar（2026-09-04）
- 决策：交付物必须由 `pnpm tauri build --target x86_64-pc-windows-gnu --bundles nsis` 生成；Debug `pet.exe` 只服务开发，绝不能作为用户应用，因为它读取 `devUrl=http://localhost:1420`。
- 后端：FastAPI 使用 PyInstaller `--onefile --noconsole` 构建为 `pet-backend.exe`，由 Tauri 资源目录启动；Tauri 正常退出负责杀进程树，后端同时监视 `PET_PARENT_PID` 覆盖崩溃退出场景。
- 可用性：未配置 `FOXTOKEN_KEY` 时默认本地陪伴回复；配置密钥后再走 foxtoken 流式通道，密钥仍只来自环境变量。
- 发布：同时产出 NSIS 安装包和包含 `HiyoriPet.exe + WebView2Loader.dll + backend/` 的便携目录；应用图标使用用户提供的日和图。

## D12 单实例与通用 API 配置（2026-09-05）
- Windows 桌宠使用 Tauri 2 官方 single-instance 插件；重复启动只唤醒已有窗口，并恢复可交互状态。
- 隐藏不是退出：气泡与托盘都提供隐藏入口，托盘负责恢复；退出才终止 Tauri 与 sidecar。
- 运行时 API 不再绑定 `FOXTOKEN_KEY`：UI 可配置 OpenAI-compatible、Anthropic Messages、Gemini 三类协议的任意官方/中转基础地址与模型。
- 用户 API key 仅保存为 Windows DPAPI 密文；不自动测试以避免未经确认的计费调用，真实对话失败时明确提示并回退本地模式。

## D13 最新桌面交互（2026-09-05）
- 左键点击触发命中反馈、动作和表情；按住左键仍可拖动，且点击后按低概率触发自主短句，不把每次点击都变成聊天窗口。
- 右键点击日和打开 API 设置面板，再次右键或点击遮罩/关闭按钮/Esc 关闭；面板始终按宠物位置和当前缩放倍率在窗口内定位。
- 自主对话只由低频空闲、窗口焦点/可见性、拖动和缩放等场景触发；未接入 API 使用本地陪伴句，已接入时才向用户配置的模型发送场景摘要，不采集键盘内容、文件内容或浏览内容。

## D14 识别后一键启用、模型导入与场景路由（2026-09-06）
- 识别结果不再要求逐个勾选才能生效：用户可一键“全部启用并启动”，也可取消本次识别；已存在的模型不会被重复导入。
- 模型目录允许导入 JSON 配置，能力与任务路由是显式字段；未知能力按文本处理，视觉能力由用户或服务端可靠元数据确认后启用。
- 多模态只扩展现有文本通道的 `image` data URL，不新增隐形采集；图片请求按 OpenAI-compatible、Anthropic、Gemini 各自协议转换。
- 多模型按 `chat`、`vision`、`scene` 任务筛选，启用的模型才参与；没有匹配时安全回退到启用目录，避免桌宠因配置不完整失联。

## D15 pet-next 新仓库与共享工具链（2026-09-06）
- 旧仓库 `D:\codex\pet` 冻结为存档（标签 `archive/hiyoripet-0.1.3`），新仓库 `D:\codex\pet-next` 承接后续开发；桌面快捷方式指向新仓库 Release。
- MinGW 工具链继续共享 `D:\codex\pet\.mingw`（体积大不复制），Rust 目标目录共享 `D:\rust\target`；后端 PyInstaller 冻结暂用存档仓库 venv（`D:\codex\pet\backend\.venv`）对本仓库源码构建，依赖清单已固化为 `backend/requirements.txt`，后续可在新仓库自建 venv。
- 命中区域策略：前端缓存 + 去抖提交，Rust 用 `ExtCreateRegion` 批量建区域；禁止再回到逐矩形 `CombineRgn` 或每帧 WebGL 回读。

## D16 收纳箱参考项目与命中测试策略回退（2026-09-06）
- 参考开源项目（仅借鉴思路，不复制代码）：DeskBox（WinUI3 桌面整理/盒子映射）、Dasktop（Windows 轻量整理、图标收纳进 Boxes）、DeskTidy（拖拽吸附/自动隐藏整理）、clever-dock（Windows 开源 dock 启动器）、Shimeji-ee / Shijima-Qt（桌宠拖拽/抱起等互动范式）。
- 命中测试：`WM_NCHITTEST + HTTRANSPARENT` 实测无法跨进程穿透到桌面（仅同线程传递），故回退 `SetWindowRgn` + `ExtCreateRegion` 批量区域；缩放期间用“缓存矩形按倍率比例换算”逐帧同步区域，既消除去抖滞后造成的条带乱码，又避免每帧 WebGL 回读（缩放实测 86-100 FPS）。
- 收纳箱 MVP 不做图标提取/云同步/搜索，后续可扩展分类自定义与拖出还原。

## D17 步态/互动与缩放区域策略 v2（2026-09-06 晚）
- 步态参考 Shimelee-ee / Shijima-Qt 的"相位驱动"思路：行走期间由 ensureParamHook 按时间相位驱动 ParamLeg/ParamArmLA/RA/BodyAngleZ/BodyAngleY（迈步 bob），位移按 |sin(phase)| 调制减少滑步；行走方向驱动 BodyAngleX 倾斜；新增 jump 姿态（双击触发）。
- 缩放期间命中区域提交整窗（不裁剪），静止 300ms 后恢复精确区域；区域提交做去重（相同矩形不重复 SetWindowRgn），缩放上限按当前显示器工作区动态钳制，避免窗口超出屏幕造成"放到最大消失"。
- 收纳箱导出只做桌面快捷方式，不移动/复制原文件，避免大文件拷贝与误删。

## D18 吞噬语义与收纳数据保护（2026-09-07）
- 桌面 `.lnk` 被收纳即从桌面删除（"吃掉"），条目记录 `original_target` 供导出重建；非桌面或非 lnk 文件只登记不移动，避免误删用户数据。
- 桌面路径一律以 `SHGetFolderPath(CSIDL_DESKTOP)` 为准（本机实际桌面在 D: 盘），不得用 `Path.home()/Desktop` 猜测。
- box.json 每次非空写入同步写 `box.json.bak`；读取异常按 主文件→备份 顺序回退，防止收纳数据被意外清空。
- 气泡/收纳箱/API 面板共用同一侧边扩展空间（互斥需求合并为一个 desired 状态），面板永远排在扩展列，禁止覆盖人物区域。

## D19 右键长按开箱 + 头部锚定气泡 + 拖喂反馈重做（2026-09-06）
- 用户裁定：收纳箱打开手势改为右键长按 650ms（旧左键长按删除）；右键短按仍为 API 面板开关。
- 气泡定位从"包围盒 + 固定扩展列偏移"改为"头部不透明带锚定"：复用 getOpaqueRegions 的 WebGL 回读缓存（400ms TTL），不新增回读开销；气泡永远不与人物不透明像素重叠，水平间隙 10px。
- 拖喂交互参考 Shimeji-ee 的注视/接物反馈范式：拖入悬停时视线跟随 + 张嘴等待，drop 后多文件全部入库并按"接住→咀嚼→播报"反馈；单次拖入多个文件逐条调用 POST /api/box。
- 桌面 `.url` 与 `.lnk` 同等对待（吃掉+可还原）；`.exe`/普通文件坚持 D18 的"只登记不移动"决策不变。
