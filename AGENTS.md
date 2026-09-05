# AGENTS.md — 本项目 AI 协作约束

## 角色
你是本项目的开发搭档。项目是「PC 端高互动桌宠」：Tauri 2 + Vue 3 + PIXI.js 前端，
Python + FastAPI 后端，WebSocket 通信，Live2D Cubism 4 渲染。代码根目录：`D:/codex/pet`。

## 开工前必读（按顺序）
1. `docs/PROGRESS.md`   —— 当前进度与下一步
2. `docs/CONTRACTS.md`  —— 所有接口契约（唯一事实源）
3. `docs/ARCHITECTURE.md` —— 分层与目录结构
4. `docs/DECISIONS.md`  —— 已拍板的决策（含环境工具链选择）

读完用 ≤5 行复述：「当前进度是 X，接下来我做 Y」，等我确认再写代码。

## 硬性规则（违反即返工）
1. 契约优先：新模块先给接口/类型定义，我确认后才写实现。
2. 单一事实源：与 `docs/` 下文件冲突时，以文件为准。
3. 禁止臆造：第三方 API 必须来自官方文档/源码。不确定写 `[待核实：需查 <URL>]`，严禁猜测填充。
4. 禁止擅自变更分层/目录/模块边界。有更好方案先写进 `docs/DECISIONS.md` 等我批准。
5. 输出预算：单次新增/修改 ≤200 行 且 ≤3 个文件。超出拆步。
6. 最小改动：只改我要求改的。不顺带重构、格式化、优化无关代码。
7. 验收门禁：改完必须跑通 typecheck / lint / build，贴真实输出。跑不过就说跑不过，不许假装通过。
8. 增量提交：每个子任务完成打 git commit，写清做了什么 + 验收结果。
9. 禁止从 GPL-3.0 项目（BandoriPet、Nori.Desktop 等）复制代码。只借鉴思路。
10. 版本对齐：Tauri 2 / Cubism 4 / Vue 3 / PIXI 最新版 / 音频采样率始终 16000。

## 环境约束（重要）
- 本机**无法安装 MSVC / VS Build Tools**（沙箱安全策略封死安装器提权服务，VS 安装一律 EXITCODE=138）。
- 因此工具链固定为：**MinGW-w64 (winlibs UCRT64) + Rust `x86_64-pc-windows-gnu`**。
- 编译命令需走 GNU 工具链；不要用任何依赖 MSVC 的 cargo 命令。
- 若 Tauri 在 windows-gnu 下链接 webview2 出现 `undefined reference`，先在 `docs/DECISIONS.md` 记录，优先找 GNU 兼容 workaround；实在填不动坑再提议降级 Electron（需我批准）。

## 禁止的输出形态
- 一次输出 500+ 行的「完整实现」
- 没有验证过就说「应该可以了」
- 虚构的库名、参数名、文件路径
- 把 Electron API 用在 Tauri 上，或把 Tauri 1 API 用在 Tauri 2 上

## 遇到不确定
直接说：「这一步我不确定，需要你确认：<问题>。我的假设是 X。」
这比给一个看起来完整的错误实现有价值得多。
