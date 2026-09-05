#!/usr/bin/env node
// start-pet.js — 桌宠一键启动器（零依赖，纯 Node 内置模块）
// 用法：node start-pet.js   （Ctrl+C 同时关闭后端与桌宠）
//
// 作用：自动注入 PATH（pnpm / cargo / MinGW）→ 起后端 uvicorn → 等 /health 就绪
//      → 起 `tauri dev` → 退出时清理两个子进程。
// 背景：手动启动时 PATH 漏配 cargo 或 MinGW 会直接编译失败，故固化在此。
const { spawn } = require('child_process')
const http = require('http')

const PET = 'D:\\codex\\pet'
const BACKEND = PET + '\\backend'
const VENV_PY = BACKEND + '\\.venv\\Scripts\\python.exe'
const PNPM = 'D:\\node-global\\pnpm.cmd'
const HEALTH = 'http://127.0.0.1:8000/health'

const env = Object.assign({}, process.env)
const extraPath = [
  'D:\\node-global',
  'C:\\Users\\Windows\\.cargo\\bin',
  PET + '\\.mingw\\bin',
  PET + '\\.mingw\\x86_64-w64-mingw32\\bin',
]
env.PATH = extraPath.join(';') + ';' + (env.PATH || '')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function probeHealth() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(1000, () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitHealth(timeoutMs = 30000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (await probeHealth()) return true
    await sleep(500)
  }
  return false
}

async function main() {
  let backend = null
  let front = null
  let closing = false

  console.log('[1/3] 启动后端 uvicorn (ws://127.0.0.1:8000/ws) ...')
  backend = spawn(
    VENV_PY,
    ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', '8000'],
    { cwd: BACKEND, env, stdio: 'inherit' }
  )

  console.log('[2/3] 等待后端就绪 ...')
  if (!(await waitHealth())) {
    console.error('后端启动超时（30s），退出。可手动检查：' + VENV_PY)
    backend.kill()
    process.exit(1)
  }
  console.log('后端就绪：' + HEALTH)

  console.log('[3/3] 启动桌宠 (pnpm tauri dev) —— 首次需编译 Rust，请稍候 ...')
  front = spawn(PNPM, ['tauri', 'dev'], { cwd: PET, env, stdio: 'inherit' })

  const cleanup = () => {
    if (closing) return
    closing = true
    console.log('\n正在关闭后端与桌宠 ...')
    try { front && front.kill() } catch (e) { /* noop */ }
    try { backend && backend.kill() } catch (e) { /* noop */ }
    setTimeout(() => process.exit(0), 500)
  }

  process.on('SIGINT', cleanup)
  process.on('SIGTERM', cleanup)

  front.on('exit', (code) => {
    if (closing) return
    console.log('tauri dev 已退出 (code=' + code + ')，同时关闭后端。')
    cleanup()
  })
  backend.on('exit', (code) => {
    if (!closing) console.log('警告：后端意外退出 (code=' + code + ')，对话功能将不可用。')
  })
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
