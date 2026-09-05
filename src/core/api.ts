export type ApiProtocol = 'openai-compatible' | 'anthropic-messages' | 'gemini'

export interface ApiStatus {
  configured: boolean
  protocol: ApiProtocol | string
  base_url: string
  model: string
  source: string
  message?: string
}

const configuredWsUrl = (import.meta as unknown as { env?: { VITE_WS_URL?: string } }).env?.VITE_WS_URL
export const API_URL = (configuredWsUrl || 'ws://localhost:8000/ws')
  .replace(/^ws:/, 'http:')
  .replace(/^wss:/, 'https:')
  .replace(/\/ws\/?$/, '')

export async function fetchApiStatus(): Promise<ApiStatus> {
  const response = await fetch(`${API_URL}/api/config`)
  if (!response.ok) throw new Error(`读取 API 配置失败（${response.status}）`)
  return (await response.json()) as ApiStatus
}

export async function saveApiConfig(input: {
  protocol: ApiProtocol
  base_url: string
  api_key: string
  model: string
}): Promise<ApiStatus> {
  const response = await fetch(`${API_URL}/api/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  const body = await response.json().catch(() => ({})) as { detail?: string }
  if (!response.ok) throw new Error(body.detail || `保存 API 配置失败（${response.status}）`)
  return body as unknown as ApiStatus
}

export async function clearApiConfig(): Promise<ApiStatus> {
  const response = await fetch(`${API_URL}/api/config`, { method: 'DELETE' })
  if (!response.ok) throw new Error(`清除 API 配置失败（${response.status}）`)
  return (await response.json()) as ApiStatus
}

export type ModelCapability = 'text' | 'vision' | 'audio'
export type ModelTask = 'chat' | 'vision' | 'scene'

export interface DiscoveredModel {
  id: string
  name: string
  owned_by?: string
  capabilities?: ModelCapability[]
  tasks?: ModelTask[]
}

export interface ModelProfile {
  id: string
  name: string
  protocol: ApiProtocol | string
  base_url: string
  enabled: boolean
  role: 'primary' | 'worker' | 'judge' | string
  capabilities: ModelCapability[]
  tasks: ModelTask[]
}

export interface CollaborationSettings {
  enabled: boolean
  strategy: 'fallback' | 'parallel'
  judge_model_id?: string
  model_ids: string[]
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  const body = await response.json().catch(() => ({})) as { detail?: string }
  if (!response.ok) throw new Error(body.detail || `请求失败（${response.status}）`)
  return body as T
}

export async function discoverApiModels(input: { protocol: ApiProtocol; base_url: string; api_key: string }): Promise<{
  connected: boolean
  protocol: string
  base_url: string
  models: DiscoveredModel[]
  error?: string
}> {
  return requestJson('/api/discover', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
}

export async function testApiConnection(input: { protocol: ApiProtocol; base_url: string; api_key: string; model: string }): Promise<{
  connected: boolean
  latency_ms?: number
  model: string
  error?: string
}> {
  return requestJson('/api/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
}

export async function fetchModelCatalog(): Promise<{ models: ModelProfile[] }> {
  return requestJson('/api/models')
}

export async function saveModelCatalog(models: Array<ModelProfile & { api_key?: string }>): Promise<{ models: ModelProfile[] }> {
  return requestJson('/api/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ models }) })
}

export async function fetchCollaboration(): Promise<CollaborationSettings> {
  return requestJson('/api/collaboration')
}

export async function saveCollaboration(input: CollaborationSettings): Promise<CollaborationSettings> {
  return requestJson('/api/collaboration', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
}
