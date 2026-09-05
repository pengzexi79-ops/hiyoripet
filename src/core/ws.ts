// src/core/ws.ts
// 前端 ↔ 后端 WebSocket 客户端（契约见 docs/CONTRACTS.md C2）。
// 负责连接、自动重连、心跳、发送/接收，业务语义交给 chat.ts。
import type { ClientMsg, ServerMsg } from './protocol'

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

type ServerCb = (msg: ServerMsg) => void
type StatusCb = (s: WsStatus) => void

export class PetSocket {
  private ws: WebSocket | null = null
  private readonly url: string
  private statusCb?: StatusCb
  private serverCb?: ServerCb
  private heartbeatTimer: number | undefined
  private reconnectTimer: number | undefined
  private closedByUser = false

  constructor(url: string) {
    this.url = url
  }

  onStatus(cb: StatusCb): void {
    this.statusCb = cb
  }
  onServer(cb: ServerCb): void {
    this.serverCb = cb
  }

  connect(): void {
    this.closedByUser = false
    this.open()
  }

  private open(): void {
    this.statusCb?.('connecting')
    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this.statusCb?.('error')
      this.scheduleReconnect()
      return
    }
    this.ws.onopen = () => {
      this.statusCb?.('open')
      this.startHeartbeat()
    }
    this.ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as ServerMsg
        this.serverCb?.(msg)
      } catch {
        /* 忽略非法帧 */
      }
    }
    this.ws.onclose = () => {
      this.stopHeartbeat()
      this.statusCb?.('closed')
      if (!this.closedByUser) this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      this.statusCb?.('error')
    }
  }

  send(msg: ClientMsg): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  close(): void {
    this.closedByUser = true
    this.stopHeartbeat()
    this.ws?.close()
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ type: 'ping' })
    }, 15000)
  }
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = undefined
    }
  }
  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = undefined
      this.open()
    }, 3000)
  }
}
