// src/core/chat.ts
// 对话编排：把后端 WS 消息翻译成宠物表现（字幕 / 占位口型 / 表情）。
// 真实口型后续由 TTS 音量包 RMS 驱动（数据流 B）；当前用占位正弦起伏。
import type { PetSocket } from './ws'
import type { ServerMsg } from './protocol'
import type { Live2d } from './live2d'

export interface ChatHandlers {
  onSubtitle?: (text: string) => void // 增量字幕（delta 累加）
  onTyping?: (typing: boolean) => void
  onError?: (msg: string) => void
  onApiStatus?: (status: Extract<ServerMsg, { type: 'api-status' }>) => void
  // 桌面感知：后端轮询到用户切换了前台应用时推送（app 为窗口标题）。
  onDesktopActivity?: (appTitle: string) => void
}

export class Chat {
  private readonly socket: PetSocket
  private readonly pet: Live2d
  private readonly handlers: ChatHandlers
  private mouthTimer: number | undefined
  private subtitleBuf = ''

  constructor(socket: PetSocket, pet: Live2d, handlers: ChatHandlers = {}) {
    this.socket = socket
    this.pet = pet
    this.handlers = handlers
    this.socket.onServer((m) => this.handle(m))
  }

  sendText(text: string, image?: string, task?: 'chat' | 'vision' | 'scene'): void {
    this.subtitleBuf = ''
    this.handlers.onTyping?.(true)
    this.socket.send({ type: 'text-input', text, ...(image ? { image } : {}), ...(task ? { task } : {}) })
  }

  private handle(m: ServerMsg): void {
    switch (m.type) {
      case 'ai-response':
        this.handlers.onTyping?.(false)
        this.subtitleBuf += m.text // 增量 delta 累加
        this.handlers.onSubtitle?.(this.subtitleBuf)
        this.startMouth()
        break
      case 'transcription':
        this.handlers.onSubtitle?.(m.text)
        break
      case 'desktop-activity':
        this.handlers.onDesktopActivity?.(m.app || '')
        break
      case 'api-status':
        this.handlers.onApiStatus?.(m)
        break
      case 'error':
        this.handlers.onTyping?.(false)
        this.handlers.onError?.(m.message)
        break
      case 'pong':
      case 'tool-status':
      default:
        break
    }
  }

  // 占位口型：说话期间让 ParamMouthOpenY 正弦起伏；真实口型待 TTS volumes 驱动。
  private startMouth(): void {
    this.stopMouth()
    const t0 = Date.now()
    this.mouthTimer = window.setInterval(() => {
      const open = (Math.sin((Date.now() - t0) / 90) + 1) / 2 // 0..1
      this.pet.setParameterValue('ParamMouthOpenY', open)
    }, 60)
    window.setTimeout(() => this.stopMouth(), 3500)
  }
  private stopMouth(): void {
    if (this.mouthTimer) {
      clearInterval(this.mouthTimer)
      this.mouthTimer = undefined
    }
    this.pet.setParameterValue('ParamMouthOpenY', 0)
  }

  destroy(): void {
    this.stopMouth()
  }
}
