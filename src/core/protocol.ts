// src/core/protocol.ts
// 前端 ↔ 后端 WebSocket 消息协议（契约见 docs/CONTRACTS.md C2）。前后端共享类型。
//
// 注意：音频走 M3 后续（ASR/TTS）。当前 M3-Part1 以 text-input（文本对话）为主通道，
// audio-chunk 的 data 暂以 number[]（JSON）传输，二进制帧优化后续再做。

export type ClientMsg =
  | { type: 'ping' }
  | { type: 'audio-chunk'; data: number[] } // Float32 采样（16000Hz），M3 后续
  | { type: 'audio-end' }
  | { type: 'text-input'; text: string; image?: string; task?: 'chat' | 'vision' | 'scene' }
  | { type: 'interrupt' }
  | { type: 'switch-character'; confUid: string }

export type ServerMsg =
  | { type: 'pong' }
  | { type: 'api-status'; configured: boolean; protocol: string; base_url: string; model: string; source: string; message?: string }
  | { type: 'ai-response'; text: string; audio?: string; volumes?: number[]; emotion: string }
  | { type: 'transcription'; text: string }
  | { type: 'tool-status'; tool: string; status: string }
  | { type: 'error'; message: string }
