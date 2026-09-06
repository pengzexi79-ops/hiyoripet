# HiyoriPet / 日和桌宠 🌸

一个运行在 Windows 桌面上的高互动 Live2D 桌宠。日和住在你的桌面上：可以摸头、拖拽、喂食、换装、聊天，还会自己散步、爬墙、对你说的话做出反应。

<p align="center">
  <em>透明置顶窗口 · Live2D Cubism 4 · Tauri 2 + Vue 3 + PIXI · Python FastAPI 后端</em>
</p>

---

## ✨ 功能总览

### 桌宠本体
- **Live2D 渲染**：Cubism 4 模型（Hiyori），透明无边框置顶窗口，命中区域精确贴合人物轮廓——点击空白处（比如双腿之间）会穿透到桌面，不会误触宠物
- **缩放**：滚轮 0.65x ~ 工作区上限（按显示器动态钳制），缩放全程无条带乱码、无画面丢失（DPI 已强制归一，命中区域按倍率精确换算）
- **拖拽物理**：拖动/甩窗时头发、丝带、裙摆、肩部、手臂会按弹簧物理甩动回弹（参考 Shimeji-ee 的速度驱动思路）
- **动作**：走路（迈腿+摆臂+身体起伏步态）、跑步、攀爬（大幅向上移动触发）、躺下、蹲坐、鸭子坐、正坐、跳跃（双击）、摸头（连点头部3次）
- **表情**：微笑、惊讶、脸红、眨眼、生气、伤心、得意、犯困（参数化实现，不依赖表情文件）

### 🗣️ AI 对话
- 右键 1 击打开 API 面板，支持 **OpenAI-compatible / Anthropic Messages / Gemini** 三协议（官方或中转地址）
- 多模型目录 + 协作（fallback / parallel）+ 模型识别 + 连接测试
- API Key 使用 Windows DPAPI 加密存储，不回传前端
- 未配置 API 时有本地陪伴模式
- **桌面感知**：后端轮询前台窗口（只读窗口标题，不读键入内容），你切换应用时日和会随机做出场景化的反应
- 自主闲聊：空闲、窗口焦点变化、拖动等场景低频触发

### 🧺 应用收纳箱
- **右键 2 击**（或长按）打开；把桌面快捷方式（.lnk/.url）拖到日和身上，她会**张嘴吃掉**——快捷方式从桌面消失并自动分类入库
- 面板内图标卡片展示，可打开、改分类、删除，或**导出还原**到桌面
- 数据写入 `%APPDATA%/HiyoriPet/box.json`，自动备份防丢失

### 👗 衣柜换装
- **右键 3 击**打开衣柜，7 个部位：外套 / 上衣（水手服领）/ 内衣 / 下衣 / 袜子 / 鞋子 / 装饰（领结）
- 外套、袜子、装饰支持**真实穿上/脱下**（脱下开衫会露出里面的水手服本体）
- 每个部位多色可选；换装按"归一化掩码重着色衣物图集 + 纹理缓存预填充 + 模型热重载"实现，不破坏模型本体
- 选择持久化保存，重启自动恢复

### 🖱️ 右键交互（分级计时判定）
| 操作 | 效果 |
|---|---|
| 右键单击（1 秒无后续） | API 设置面板 |
| 右键连点 2 下 | 应用收纳箱 |
| 右键连点 3 下 | 日和衣柜 |
| 右键长按 650ms | 应用收纳箱 |
| 左键 | 互动 / 双击跳跃 |
| 按住左键拖动 | 移动桌宠 |
| 滚轮 | 缩放 |

---

## 🚀 快速开始

### 直接使用
从 Release 下载 `HiyoriPet_0.1.4_x64-setup.exe` 安装，或解压便携版直接运行 `HiyoriPet.exe`。

### 从源码构建

```powershell
# 依赖：Node 18+ / pnpm / Rust (x86_64-pc-windows-gnu) / MinGW-w64 / Python 3.10+
pnpm install
pnpm exec tsc --noEmit     # 类型检查
pnpm build                 # 前端构建
python -m compileall backend
pnpm tauri build --target x86_64-pc-windows-gnu --bundles nsis
```

### Live2D 资产
`public/models/`（Hiyori 等官方样例模型）与 `public/cubism-core/`（Cubism Core 运行时）
遵循 Live2D 的免费素材授权，请从 [Live2D 官方](https://www.live2d.com/) 获取并放入对应目录；
商用分发前请自行核对 Live2D 免费素材许可协议。

### AI 接入
右键单击宠物 → 填写接口地址 / 协议 / 模型 / API Key → 保存。
推荐任何 OpenAI 兼容服务（DeepSeek、通义、硅基流动、OpenRouter 等）。

---

## 🧱 架构

```
Vue 3 表现层（App.vue：交互编排 / 面板 / 气泡）
  ├─ src/core/live2d.ts   Live2D 单例：渲染 / 姿态 / 表情 / 步态 / 命中区域
  ├─ src/core/outfit.ts   换装引擎：掩码重着色 + 纹理缓存预填充
  ├─ src/core/ws|chat.ts  WebSocket 对话通道
  └─ Tauri 2（Rust）：透明窗口 / Win32 命中区域 / 单实例 / sidecar 生命周期
        ↓ ws://127.0.0.1:8000/ws
Python FastAPI（PyInstaller sidecar）
  ├─ server.py            WS 路由 / 前台窗口轮询（桌面感知）
  ├─ api_provider.py      多协议 LLM 适配（OpenAI / Anthropic / Gemini）
  ├─ box_store.py         收纳箱持久化 / 分类 / 图标 / 快捷方式
  └─ llm/ tts/ asr/       工厂化能力模块
```

## 📖 开发文档

- [`docs/CONTRACTS.md`](docs/CONTRACTS.md) — 接口契约（唯一事实源）
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 分层与目录
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — 已拍板的技术决策
- [`docs/PROGRESS.md`](docs/PROGRESS.md) — 开发进度全记录
- [`docs/AI_HANDOFF.md`](docs/AI_HANDOFF.md) — AI 协作交接手册

## 🙏 致谢与参考（仅借鉴思路，未复制代码）

- [Shimeji-ee](https://github.com/Shimeji-ee/Shimeji-ee) / Shijima-Qt — 桌宠步态循环、攀爬与拖拽互动范式
- [VPet-Simulator](https://github.com/LomeItem/VPet) — 分类衣柜与桌面交互设计
- [Live2D Cubism SDK 样例](https://www.live2d.com/) — Hiyori 模型与 Cubism Core
- [Tauri](https://tauri.app/) / [PIXI.js](https://pixijs.com/) / [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display) / [FastAPI](https://fastapi.tiangolo.com/)

## 📄 许可

项目代码供学习研究使用。Live2D 模型与 Cubism Core 的版权归 Live2D Inc. 所有，
使用前请阅读并遵守 [Live2D 免费素材许可协议](https://www.live2d.com/eula/live2d-free-material-license-agreement_ch.html)。
