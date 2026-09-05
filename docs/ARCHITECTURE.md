# ARCHITECTURE.md — 分层与目录结构（单一事实源）

> 与本文档冲突时，以本文档为准。改动分层/目录需先写 DECISIONS.md 获批。

## 分层（自上而下，禁止跨层直连）

```
L6 表现层   Vue 组件 / 托盘菜单 / 聊天气泡 / 互动反馈
L5 交互层   useDevice / useDrag / useTray → 行为仲裁 arbiter
L4 状态层   Pinia：model / emotion / config
L3 渲染层   Live2d 单例（PIXI Application + Live2DModel + 参数驱动）
L2 通信层   WebSocket Client（重连 / 心跳 / 序列化）
L1 平台层   Tauri Core：窗口 / 全局输入 / 文件 / 托盘 / 自启
            ↕ WebSocket（前后端唯一耦合点）
后端       FastAPI + ServiceContext → ASR / Agent / LLM / TTS / 记忆（SQLite）
```

**刚性边界**
1. 后端不碰窗口；前端不跑模型推理。
2. 外部能力（ASR/LLM/TTS/渲染）全部走「接口 + 工厂」，换供应商不改业务代码。
3. 配置驱动，Pydantic 强校验；配置错误启动即报，不延迟到运行时。

## 目录结构（实际已创建）

```
D:/codex/pet/
├─ AGENTS.md                     # AI 协作约束
├─ .mingw/                       # MinGW-w64 工具链（winlibs，解压即用）
├─ _installers/                  # 安装器缓存（vs_BuildTools / rustup / mingw.zip）
├─ docs/
│  ├─ ARCHITECTURE.md            # 本文件
│  ├─ CONTRACTS.md               # 接口契约
│  ├─ DECISIONS.md               # 决策记录
│  └─ PROGRESS.md                # 进度看板
├─ src/                          # 前端 Vue 3 + TS
│  ├─ core/live2d.ts             # Live2d 单例（initApp/load/destroy/resizeModel/playMotion/playExpressions/setParameterValue）
│  ├─ stores/{model,emotion,config}.ts   # Pinia
│  ├─ composables/{useDevice,useDrag,useTray}.ts
│  └─ components/                # 气泡 / 字幕 / 互动表现
├─ src-tauri/                    # Rust 侧
│  ├─ Cargo.toml
│  ├─ build.rs
│  ├─ tauri.conf.json
│  ├─ capabilities/default.json  # ⚠️ 权限白名单（缺权限会静默失败）
│  └─ src/{lib.rs, window.rs, input.rs, tray.rs, main.rs}
├─ backend/                      # Python AI 后端
│  ├─ server.py                  # FastAPI + WebSocket
│  ├─ service_context.py         # 服务定位器
│  ├─ conf.yaml                  # 唯一配置入口（${ENV_VAR} 替换）
│  ├─ config_manager/            # Pydantic 配置模型
│  ├─ asr/ llm/ tts/ agent/      # 各含 *_interface.py + *_factory.py
│  └─ memory/                    # SQLite 持久化
└─ (未来) models/                # 用户自有 Live2D 模型目录（不进仓库）
```

## 三条核心数据流

**A. 输入→动作（毫秒级，纯前端，不走后端）**
```
键鼠事件(Rust rdev/Win32) → Tauri event → useDevice → Pinia → arbiter 仲裁 → live2d.setParameterValue / playMotion
```

**B. 语音对话（走后端，M3 起）**
```
麦克风 → VAD 起止 → 音频分片 → WS audio-chunk → 后端 ASR → Agent(人格+记忆+工具) → LLM 流式 → 按句切分 → 并行 TTS → audio-play(音频+音量包+文本+emotion) → 播放+口型(RMS 驱动 mouthOpenY)+表情
```

**C. 主动行为（本地定时）**
```
定时器(空闲 N 秒/时间戳/系统事件) → arbiter 判定 idle → 随机待机动作 + 情绪衰减 + 主动搭话(概率)
```

## M5 实际发布结构（2026-09-04）

```text
src-tauri/src/backend.rs                       # sidecar 启动、隐藏控制台、退出时杀进程树
src-tauri/resources/backend/pet-backend.exe    # 本机构建输入（生成物，不进 Git）
backend/main.py                                # PyInstaller/Uvicorn 入口 + PET_PARENT_PID 监视
release/HiyoriPet/                             # 本地便携交付目录（生成物，不进 Git）
```

发布运行流：
```text
HiyoriPet.exe
  -> Tauri 从 $RESOURCE/backend/pet-backend.exe 启动 FastAPI
  -> Vue 的 PetSocket 重连到 ws://127.0.0.1:8000/ws
  -> 无 API key：本地规则回复；有 FOXTOKEN_KEY：foxtoken 流式回复
  -> 托盘退出：Tauri taskkill 进程树；异常退出：Python 监视父 PID 后自退
```

主动行为在桌面壳中以窗口为移动单位：空闲 12 秒后在当前显示器工作区内缓慢游走，点击、拖动、聊天或隐藏状态会暂停；浏览器预览仅保留画布内移动作为降级。
