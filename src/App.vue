<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { currentMonitor, getCurrentWindow } from '@tauri-apps/api/window'
import { invoke } from '@tauri-apps/api/core'
import { LogicalSize, PhysicalPosition, PhysicalSize } from '@tauri-apps/api/dpi'
import { Live2d, type ModelMeta, type PetPose } from './core/live2d'
import { PetSocket, type WsStatus } from './core/ws'
import { Chat } from './core/chat'
import { clearApiConfig, discoverApiModels, fetchApiStatus, fetchCollaboration, fetchModelCatalog, saveApiConfig, saveCollaboration, saveModelCatalog, testApiConnection, type ApiProtocol, type ApiStatus, type CollaborationSettings, type DiscoveredModel, type ModelCapability, type ModelProfile, type ModelTask } from './core/api'

// 模型放置于 public/models/Hiyori/（Vite 构建时拷进 dist/models/，由 Tauri 资源一并打包）。
const MODEL_URL = '/models/Hiyori/Hiyori.model3.json'
// 后端 WS 地址：默认本机 8000；可用 VITE_WS_URL 覆盖（如打包后改为实际地址）。
const WS_URL = (import.meta as unknown as { env?: { VITE_WS_URL?: string } }).env?.VITE_WS_URL || 'ws://localhost:8000/ws'

const canvas = ref<HTMLCanvasElement | null>(null)
const status = ref('初始化中…')
const hasCore = ref(true)
const meta = ref<ModelMeta | null>(null)
const lastUserInteraction = ref(0)

// M3 对话状态
const wsStatus = ref<WsStatus>('closed')
const subtitle = ref('')
const typing = ref(false)
const inputText = ref('')
const wsError = ref('')
const apiStatus = ref<ApiStatus>({ configured: false, protocol: 'openai-compatible', base_url: '', model: '', source: 'local' })
const apiPanelVisible = ref(false)
const apiPanelPos = ref({ x: 0, y: 0 })
const apiPanel = ref<HTMLElement | null>(null)
const apiSaving = ref(false)
const apiError = ref('')
type ApiPreset = { id: string; label: string; protocol: ApiProtocol; baseUrl: string }
const API_PRESETS: ApiPreset[] = [
  { id: 'custom', label: '自定义接口（其他官方 / 中转）', protocol: 'openai-compatible', baseUrl: '' },
  { id: 'openai', label: '国外 · OpenAI', protocol: 'openai-compatible', baseUrl: 'https://api.openai.com/v1' },
  { id: 'anthropic', label: '国外 · Anthropic Claude', protocol: 'anthropic-messages', baseUrl: 'https://api.anthropic.com' },
  { id: 'gemini', label: '国外 · Google Gemini', protocol: 'gemini', baseUrl: 'https://generativelanguage.googleapis.com' },
  { id: 'openrouter', label: '国外 / 聚合 · OpenRouter', protocol: 'openai-compatible', baseUrl: 'https://openrouter.ai/api/v1' },
  { id: 'deepseek', label: '国内 · DeepSeek', protocol: 'openai-compatible', baseUrl: 'https://api.deepseek.com' },
  { id: 'dashscope', label: '国内 · 通义千问 / 百炼', protocol: 'openai-compatible', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'zhipu', label: '国内 · 智谱 GLM', protocol: 'openai-compatible', baseUrl: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'siliconflow', label: '国内 / 聚合 · 硅基流动', protocol: 'openai-compatible', baseUrl: 'https://api.siliconflow.cn/v1' },
]
const apiPreset = ref('custom')
const apiForm = ref({ protocol: 'openai-compatible' as ApiProtocol, base_url: '', api_key: '', model: '' })
type UiModelProfile = ModelProfile & { api_key?: string }
const modelCatalog = ref<UiModelProfile[]>([])
const discoveredModels = ref<UiModelProfile[]>([])
const collaboration = ref<CollaborationSettings>({ enabled: false, strategy: 'fallback', model_ids: [] })
const apiDiscovering = ref(false)
const apiTesting = ref(false)
const catalogSaving = ref(false)
const providerMessage = ref('')
const pendingImage = ref('')
const imageInput = ref<HTMLInputElement | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
let discoveryAddedKeys: string[] = []
// 调试 HUD 默认隐藏：桌宠画面上不显示任何 UI（此前底部白色面板会挡住模型下半身且碍眼）。
// ── 桌宠交互：仅保留 Hiyori，缩放由滚轮控制 ──
const guideVisible = ref(true)
const reaction = ref<{ text: string; x: number; y: number } | null>(null)
const chatBubbleVisible = ref(false)
const bubble = ref<HTMLElement | null>(null)
const bubblePos = ref({ x: 0, y: 0, width: 236, side: 'right' as 'left' | 'right' | 'top' | 'bottom', arrowY: 28 })
const bubbleFading = ref(false)
const bubbleReady = ref(false)
const zoomLevel = ref(1)
const uiScale = computed(() => Math.max(0.85, Math.min(1.5, zoomLevel.value)))
const FACES = ['smile', 'surprise', 'blush', 'wink'] as const
type PetFace = typeof FACES[number]
const AUTONOMOUS_POSES: PetPose[] = ['lie', 'kneel', 'duck-sit', 'happy', 'cute', 'sleepy']

let pet: Live2d | null = null
let socket: PetSocket | null = null
let chat: Chat | null = null
let idleTimer: number | undefined
let guideTimer: number | undefined
let reactionTimer: number | undefined
let behaviorTimer: number | undefined
let autonomyTimer: number | undefined
let autonomyBusy = false
let autonomyCooldownUntil = 0
let wanderTarget: { x: number; y: number } | null = null
let desktopWanderTarget: { x: number; y: number } | null = null
let desktopPosition: { x: number; y: number } | null = null
let desktopMoveBusy = false
let desktopWalking = false
let desktopStepAt = 0
let nextWanderAt = 0
let tapCount = 0
let stopPetVisibilityListener: UnlistenFn | undefined
let stopPetHiddenListener: UnlistenFn | undefined
let press: { pointerId: number; clientX: number; clientY: number; x: number; y: number } | null = null
let stopWindowMovedListener: UnlistenFn | undefined
let bubbleDismissTimer: number | undefined
let bubbleFadeTimer: number | undefined
let zoomFrame: number | undefined
let pendingZoom: number | null = null
let zoomBusy = false
let nativeRegionRequest = 0
let hideInFlight = false
let hitRegionTimer: number | undefined

/** 命中区域同步含 WebGL 回读与 GDI 区域提交，统一去抖，避免缩放/连点时每帧执行。 */
function scheduleNativeHitRegion(delay = 180) {
  if (hitRegionTimer !== undefined) clearTimeout(hitRegionTimer)
  hitRegionTimer = window.setTimeout(() => {
    hitRegionTimer = undefined
    void syncNativeHitRegion()
  }, delay)
}

async function syncNativeHitRegion() {
  if (!pet) return
  const request = ++nativeRegionRequest
  // v-if 的面板/气泡需要等 Vue 提交 DOM、定位样式和一次布局帧后再测量。
  await nextTick()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (request !== nativeRegionRequest || !pet) return
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  const root = canvas.value?.parentElement
  const rootRect = root?.getBoundingClientRect()
  const regions = pet.getOpaqueRegions(3, true)
  // Live2D/WebGL 某些驱动会短暂返回空像素；保留上一次有效 HWND 区域，
  // 不允许空结果退化成可拦截鼠标的整块矩形。
  if (!regions.length) return
  const domRegions = [apiPanel.value, bubble.value].flatMap((element) => {
    if (!element || !rootRect) return []
    const rect = element.getBoundingClientRect()
    const x = Math.max(0, rect.left - rootRect.left - 2)
    const y = Math.max(0, rect.top - rootRect.top - 2)
    const right = Math.min(rootRect.width, rect.right - rootRect.left + 2)
    const bottom = Math.min(rootRect.height, rect.bottom - rootRect.top + 2)
    return right > x && bottom > y ? [{ x, y, width: right - x, height: bottom - y }] : []
  })
  const allRegions = [...regions, ...domRegions]
  await invoke('set_hit_region', {
    rects: allRegions.map((rect) => ({
      x: Math.floor(rect.x * dpr),
      y: Math.floor(rect.y * dpr),
      width: Math.max(1, Math.ceil(rect.width * dpr)),
      height: Math.max(1, Math.ceil(rect.height * dpr)),
    })),
  }).catch(() => {})
}

function onNativeRegionResize() {
  scheduleNativeHitRegion(240)
}

async function loadModel() {
  if (!pet) return
  try {
    status.value = '加载模型中…'
    const m = await pet.load(MODEL_URL)
    meta.value = m
    lastUserInteraction.value = Date.now()
    nextWanderAt = Date.now() + 12000
    status.value = `已加载：${Object.keys(m.motions).length} 组动作 / ${m.expressions.length} 个表情`
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    scheduleNativeHitRegion()
  } catch (e) {
    status.value = `模型加载失败：${(e as Error)?.message ?? e}（请确认 public/models/Hiyori 已放入资产）`
  }
}

onMounted(async () => {
  if (!canvas.value) return
  // pixi-live2d-display 的 Cubism 4 入口要求全局 window.Live2DCubismCore 已就绪。
  hasCore.value = !!(window as unknown as { Live2DCubismCore?: unknown }).Live2DCubismCore
  if (!hasCore.value) {
    status.value = 'Cubism Core 未加载（缺 public/cubism-core/live2dcubismcore.min.js）'
    return
  }
  pet = new Live2d()
  pet.initApp(canvas.value)
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  await loadModel()
  await normalizePetWindowSize()
  pet?.syncRendererSize()
  if (pet && meta.value) pet.resizeModel(meta.value)
  startIdle()
  startBehavior()
  guideTimer = window.setTimeout(() => (guideVisible.value = false), 8000)
  window.addEventListener('keydown', onKey)
  window.addEventListener('focus', onWindowFocus)
  window.addEventListener('blur', onWindowBlur)
  window.addEventListener('visibilitychange', onVisibilityChange)
  // 浏览器预览没有 Tauri IPC；仅在桌面壳中订阅托盘/原生快捷操作的同步事件。
  if ((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    const appWindow = getCurrentWindow()
    const initialPosition = await appWindow.outerPosition().catch(() => null)
    if (initialPosition) desktopPosition = { x: initialPosition.x, y: initialPosition.y }
    stopWindowMovedListener = await appWindow.onMoved(({ payload }) => {
      desktopPosition = { x: payload.x, y: payload.y }
    })
    stopPetVisibilityListener = await listen('pet-opened', async () => {
      await normalizePetWindowSize()
      status.value = '桌宠已打开'
      lastUserInteraction.value = Date.now()
      nextWanderAt = Date.now() + 12000
      desktopWanderTarget = null
      pet?.syncRendererSize()
      if (pet && meta.value) pet.resizeModel(meta.value)
      startIdle()
      startBehavior()
      startAutonomy()
      scheduleNativeHitRegion()
    })
    stopPetHiddenListener = await listen('pet-hidden', async () => {
      await closeBubble()
      closeApiPanel()
      stopAutonomy()
      stopBehavior()
    })
  }
  // M3：建立后端对话通道
  window.addEventListener('resize', positionBubble)
  window.addEventListener('resize', positionApiPanel)
  window.addEventListener('resize', onNativeRegionResize)
  window.addEventListener('pet-api-action', onApiAction as EventListener)
  ;(window as Window & { petApi?: { dispatch: (action: PetApiAction) => void } }).petApi = {
    dispatch: (action) => window.dispatchEvent(new CustomEvent('pet-api-action', { detail: action })),
  }
  connectChat()
  startAutonomy()
})

// Esc 关闭气泡；其余交互由鼠标完成
function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
  if (e.key === 'Escape') {
    void closeBubble()
    closeApiPanel()
  }
}

function onWindowFocus() {
  maybeAutonomousTalk('你回到桌面了')
}

function onWindowBlur() {
  maybeAutonomousTalk('你暂时离开了桌宠')
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') maybeAutonomousTalk('桌面重新亮起来了')
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('focus', onWindowFocus)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('visibilitychange', onVisibilityChange)
  stopPetVisibilityListener?.()
  stopPetVisibilityListener = undefined
  stopPetHiddenListener?.()
  stopPetHiddenListener = undefined
  stopWindowMovedListener?.()
  stopWindowMovedListener = undefined
  window.removeEventListener('resize', positionBubble)
  window.removeEventListener('resize', positionApiPanel)
  window.removeEventListener('resize', onNativeRegionResize)
  if (autonomyTimer) clearTimeout(autonomyTimer)
  autonomyTimer = undefined
  cancelBubbleDismiss()
  if (zoomFrame !== undefined) cancelAnimationFrame(zoomFrame)
  zoomFrame = undefined
  pendingZoom = null
  window.removeEventListener('pet-api-action', onApiAction as EventListener)
  delete (window as Window & { petApi?: unknown }).petApi
  if (guideTimer) clearTimeout(guideTimer)
  if (reactionTimer) clearTimeout(reactionTimer)
  stopBehavior()
  stopIdle()
  chat?.destroy()
  socket?.close()
  pet?.destroy()
  pet = null
  socket = null
  chat = null
})

function connectChat() {
  if (!pet) return
  socket = new PetSocket(WS_URL)
  socket.onStatus((s) => {
    wsStatus.value = s
    if (s === 'open') wsError.value = ''
  })
  chat = new Chat(socket, pet, {
    onSubtitle: (t) => {
      subtitle.value = t
      openBubble()
      requestAnimationFrame(positionBubble)
    },
    onTyping: (b) => {
      typing.value = b
      if (b) cancelBubbleDismiss()
      else armBubbleDismiss()
    },
    onError: (m) => {
      wsError.value = m
      subtitle.value = ''
      openBubble()
    },
    onApiStatus: applyApiStatus,
  })
  socket.connect()
  void fetchApiStatus().then(applyApiStatus).catch(() => {})
}

const LOCAL_CHATTER = [
  '我在这里晃一晃，陪你工作一会儿～',
  '记得抬头看看远处，眼睛也要休息哦。',
  '今天的桌面看起来很认真呢。',
  '要不要摸摸我的头？我会努力回应的！',
]

function stopAutonomy() {
  if (autonomyTimer) clearTimeout(autonomyTimer)
  autonomyTimer = undefined
  autonomyBusy = false
}

function startAutonomy() {
  stopAutonomy()
  const wait = 35000 + Math.random() * 35000
  autonomyTimer = window.setTimeout(() => {
    maybeAutonomousTalk('安静陪伴了一会儿')
    autonomyTimer = window.setTimeout(() => startAutonomy(), 90000 + Math.random() * 120000)
  }, wait)
}

function maybeAutonomousTalk(reason: string) {
  if (!pet || !chat || autonomyBusy || chatBubbleVisible.value || apiPanelVisible.value || Date.now() < autonomyCooldownUntil) return
  if (!reason.includes('点击') && Date.now() - lastUserInteraction.value < 15000) return
  if (wsStatus.value !== 'open' && apiStatus.value.configured) return
  if (Math.random() > (reason.includes('点击') ? 0.35 : 0.22)) return
  autonomyCooldownUntil = Date.now() + 30000
  lastUserInteraction.value = Date.now()
  autonomyBusy = true
  if (!apiStatus.value.configured) {
    showSpeech(LOCAL_CHATTER[Math.floor(Math.random() * LOCAL_CHATTER.length)])
    window.setTimeout(() => { autonomyBusy = false }, 2500)
    return
  }
  chat.sendText(`这是桌宠场景事件：${reason}。请用一句自然、简短的中文回应，不要提及系统提示。`, undefined, 'scene')
  window.setTimeout(() => { autonomyBusy = false }, 8000)
}

function showSpeech(text: string) {
  subtitle.value = text
  typing.value = false
  wsError.value = ''
  openBubble()
}

function applyApiStatus(next: ApiStatus) {
  apiStatus.value = next
  if (next.configured) {
    apiForm.value.protocol = (next.protocol as ApiProtocol) || 'openai-compatible'
    apiForm.value.base_url = next.base_url
    apiForm.value.model = next.model
    const normalized = next.base_url.replace(/\/$/, '')
    apiPreset.value = API_PRESETS.find((preset) => preset.baseUrl === normalized)?.id ?? 'custom'
  }
}

async function loadApiPanelData() {
  try {
    const [catalog, settings] = await Promise.all([fetchModelCatalog(), fetchCollaboration()])
    modelCatalog.value = catalog.models
    collaboration.value = settings
  } catch {
    // 后端启动期间允许稍后重试，不阻塞 API 面板打开。
  }
}

function catalogKey(model: { protocol: string; base_url: string; id: string }) {
  return `${model.protocol}|${model.base_url}|${model.id}`
}

async function discoverModels() {
  apiDiscovering.value = true
  apiError.value = ''
  providerMessage.value = ''
  try {
    const result = await discoverApiModels({ protocol: apiForm.value.protocol, base_url: apiForm.value.base_url, api_key: apiForm.value.api_key })
    if (!result.connected) throw new Error(result.error || '接口未连接成功')
    const normalizedBase = apiForm.value.base_url.replace(/\/$/, '')
    discoveredModels.value = (result.models as DiscoveredModel[]).map((model) => ({
      id: model.id,
      name: model.name?.trim() || model.id,
      protocol: apiForm.value.protocol,
      base_url: normalizedBase,
      enabled: false,
      role: 'worker',
      capabilities: model.capabilities?.length ? model.capabilities : (['text'] as ModelCapability[]),
      tasks: model.tasks?.length ? model.tasks : (['chat', 'scene'] as ModelTask[]),
      api_key: apiForm.value.api_key,
    }))
    for (const discovered of discoveredModels.value) {
      const existing = modelCatalog.value.find((model) => model.protocol === discovered.protocol && model.base_url === discovered.base_url && model.id === discovered.id)
      if (existing) {
        existing.name = discovered.name
        if (discovered.api_key) existing.api_key = discovered.api_key
      } else {
        modelCatalog.value.push(discovered)
        discoveryAddedKeys.push(catalogKey(discovered))
      }
    }
    if (!apiForm.value.model && result.models[0]) apiForm.value.model = result.models[0].id
    providerMessage.value = `连接成功，识别到 ${result.models.length} 个可用模型；可一键启动或取消本次识别。`
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    apiDiscovering.value = false
  }
}

function setDiscoveredEnabled(model: UiModelProfile) {
  const existing = modelCatalog.value.find((item) => item.protocol === model.protocol && item.base_url === model.base_url && item.id === model.id)
  if (existing) existing.enabled = model.enabled
}

async function enableAllDiscovered() {
  if (!discoveredModels.value.length) return
  catalogSaving.value = true
  apiError.value = ''
  try {
    for (const model of discoveredModels.value) {
      model.enabled = true
      setDiscoveredEnabled(model)
    }
    const saved = await saveModelCatalog(modelCatalog.value)
    const selected = saved.models.filter((model) => model.enabled).map((model) => model.id)
    const next = await saveCollaboration({ ...collaboration.value, enabled: true, model_ids: selected })
    modelCatalog.value = saved.models
    collaboration.value = next
    discoveredModels.value = []
    discoveryAddedKeys = []
    providerMessage.value = `已一键启动 ${selected.length} 个模型，多模型协作已开启。`
    void fetchApiStatus().then(applyApiStatus).catch(() => {})
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    catalogSaving.value = false
  }
}

function cancelDiscovery() {
  const added = new Set(discoveryAddedKeys)
  modelCatalog.value = modelCatalog.value.filter((model) => !added.has(catalogKey(model)) || model.enabled)
  discoveredModels.value = []
  discoveryAddedKeys = []
  providerMessage.value = '已取消本次识别结果，未保存的识别模型已移除。'
}

async function importModelsFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  apiError.value = ''
  try {
    const parsed = JSON.parse(await file.text()) as { models?: unknown[] } | unknown[]
    const rows = Array.isArray(parsed) ? parsed : Array.isArray((parsed as { models?: unknown[] }).models) ? (parsed as { models: unknown[] }).models : []
    if (!rows.length) throw new Error('JSON 中缺少 models 数组')
    let added = 0
    for (const row of rows) {
      const item = row as Partial<UiModelProfile>
      const id = String(item.id || '').trim()
      const baseUrl = String(item.base_url || '').replace(/\/$/, '')
      if (!id || !baseUrl.startsWith('http')) continue
      const profile: UiModelProfile = {
        id,
        name: String(item.name || id),
        protocol: (item.protocol || 'openai-compatible') as ApiProtocol,
        base_url: baseUrl,
        enabled: Boolean(item.enabled),
        role: item.role || 'worker',
        capabilities: item.capabilities?.length ? item.capabilities : ['text'],
        tasks: item.tasks?.length ? item.tasks : ['chat', 'scene'],
        api_key: typeof item.api_key === 'string' ? item.api_key : undefined,
      }
      const existing = modelCatalog.value.find((model) => catalogKey(model) === catalogKey(profile))
      if (existing) Object.assign(existing, profile)
      else {
        modelCatalog.value.push(profile)
        added += 1
      }
    }
    providerMessage.value = `导入完成：新增 ${added} 个模型；勾选后保存即可启用。`
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  }
}

function pickImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 4 * 1024 * 1024) {
    wsError.value = '图片过大，请选择 4MB 以内的图片。'
    return
  }
  const reader = new FileReader()
  reader.onload = () => { pendingImage.value = String(reader.result || '') }
  reader.onerror = () => { wsError.value = '图片读取失败，请重试。' }
  reader.readAsDataURL(file)
}

async function testConnection() {
  apiTesting.value = true
  apiError.value = ''
  providerMessage.value = ''
  try {
    const result = await testApiConnection({ protocol: apiForm.value.protocol, base_url: apiForm.value.base_url, api_key: apiForm.value.api_key, model: apiForm.value.model })
    if (!result.connected) throw new Error(result.error || '接口测试失败')
    providerMessage.value = `连接测试成功 · ${result.model} · ${result.latency_ms ?? 0} ms`
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    apiTesting.value = false
  }
}

async function saveModelSettings() {
  catalogSaving.value = true
  apiError.value = ''
  try {
    const saved = await saveModelCatalog(modelCatalog.value)
    const selected = saved.models.filter((model) => model.enabled).map((model) => model.id)
    const next = await saveCollaboration({ ...collaboration.value, model_ids: selected })
    modelCatalog.value = saved.models
    collaboration.value = next
    providerMessage.value = next.enabled ? `已启用 ${selected.length} 个模型协作。` : '多模型协作已关闭。'
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    catalogSaving.value = false
  }
}
function positionApiPanel() {
  if (!apiPanelVisible.value) return
  const b = pet?.getBounds() ?? { x: window.innerWidth / 2, y: window.innerHeight / 2, width: 0, height: 0 }
  const width = apiPanel.value?.offsetWidth || Math.min(286 * uiScale.value, window.innerWidth - 16)
  const height = apiPanel.value?.offsetHeight || Math.min(430 * uiScale.value, window.innerHeight - 16)
  const gap = 10
  const right = window.innerWidth - (b.x + b.width)
  const rawX = right >= width + gap ? b.x + b.width + gap : b.x - width - gap
  apiPanelPos.value = {
    x: Math.max(8, Math.min(rawX, window.innerWidth - width - 8)),
    y: Math.max(8, Math.min(b.y + b.height * 0.08, window.innerHeight - height - 8)),
  }
}

async function openApiPanel() {
  apiError.value = ''
  await closeBubble()
  stopIdle()
  stopBehavior()
  stopAutonomy()
  apiPanelVisible.value = true
  void syncNativeHitRegion()
  lastUserInteraction.value = Date.now()
  void loadApiPanelData()
  positionApiPanel()
  requestAnimationFrame(positionApiPanel)
}

function closeApiPanel() {
  const wasVisible = apiPanelVisible.value
  apiPanelVisible.value = false
  apiError.value = ''
  void syncNativeHitRegion()
  if (wasVisible && pet) {
    startIdle()
    startBehavior()
    startAutonomy()
  }
}

function selectApiPreset() {
  const preset = API_PRESETS.find((item) => item.id === apiPreset.value)
  if (!preset) return
  apiForm.value.protocol = preset.protocol
  apiForm.value.base_url = preset.baseUrl
  apiForm.value.model = ''
}

async function saveApi() {
  apiSaving.value = true
  apiError.value = ''
  try {
    applyApiStatus(await saveApiConfig(apiForm.value))
    closeApiPanel()
    wsError.value = ''
    subtitle.value = 'API 已保存，下次对话会使用新配置。'
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    apiSaving.value = false
  }
}

async function clearApi() {
  apiSaving.value = true
  apiError.value = ''
  try {
    applyApiStatus(await clearApiConfig())
    apiForm.value.api_key = ''
    closeApiPanel()
    subtitle.value = '已清除 API，当前使用本地陪伴模式。'
  } catch (e) {
    apiError.value = (e as Error)?.message ?? String(e)
  } finally {
    apiSaving.value = false
  }
}

function sendText() {
  const text = inputText.value.trim()
  const image = pendingImage.value
  if ((!text && !image) || !chat) return
  subtitle.value = ''
  wsError.value = ''
  openBubble()
  chat.sendText(text || '请看这张图片并简短回应。', image || undefined, image ? 'vision' : 'chat')
  inputText.value = ''
  pendingImage.value = ''
  lastUserInteraction.value = Date.now()
}

// ── M2：空闲自播待机动作（数据流 C）──
function startIdle() {
  stopIdle()
  idleTimer = window.setInterval(() => {
    if (!pet || apiPanelVisible.value || press) return
    const idle = Date.now() - lastUserInteraction.value > 8000
    if (idle) {
      pet.playMotionRandom('Idle').catch(() => {})
      if (Math.random() < 0.45) pet.applyFace(FACES[Math.floor(Math.random() * FACES.length)])
      if (Math.random() < 0.32) pet.applyPose(AUTONOMOUS_POSES[Math.floor(Math.random() * AUTONOMOUS_POSES.length)], 5200)
      if (Math.random() < 0.3) {
        const b = pet.getBounds()
        showReaction(b.x + b.width / 2, b.y + b.height * 0.18)
      }
    }
  }, 8000)
}
function stopIdle() {
  if (idleTimer) {
    clearInterval(idleTimer)
    idleTimer = undefined
  }
}

async function stepDesktopWander() {
  if (!pet || desktopMoveBusy) return
  desktopMoveBusy = true
  try {
    const appWindow = getCurrentWindow()
    if (!desktopPosition) {
      const position = await appWindow.outerPosition()
      desktopPosition = { x: position.x, y: position.y }
    }
    if (!desktopWanderTarget) {
      if (Date.now() < nextWanderAt) return
      const [monitor, size] = await Promise.all([currentMonitor(), appWindow.outerSize()])
      if (!monitor) return
      const minX = monitor.workArea.position.x
      const minY = monitor.workArea.position.y
      const maxX = Math.max(minX, minX + monitor.workArea.size.width - size.width)
      const maxY = Math.max(minY, minY + monitor.workArea.size.height - size.height)
      desktopPosition = {
        x: Math.max(minX, Math.min(maxX, desktopPosition.x)),
        y: Math.max(minY, Math.min(maxY, desktopPosition.y)),
      }
      desktopWanderTarget = {
        x: Math.round(minX + Math.random() * Math.max(1, maxX - minX)),
        y: Math.round(minY + Math.random() * Math.max(1, maxY - minY)),
      }
      pet.applyPose('walk', 2400)
      pet.playMotionRandom('Idle').catch(() => {})
      if (Math.random() < 0.65) pet.applyFace(FACES[Math.floor(Math.random() * FACES.length)])
    }
    const dx = desktopWanderTarget.x - desktopPosition.x
    const dy = desktopWanderTarget.y - desktopPosition.y
    const distance = Math.hypot(dx, dy)
    if (distance < 5) {
      desktopWanderTarget = null
      desktopWalking = false
      desktopStepAt = 0
      pet.applyPose('idle', 1200)
      nextWanderAt = Date.now() + 3000 + Math.random() * 6000
      return
    }
    if (!desktopWalking) {
      desktopWalking = true
      pet.applyPose('walk', 2400)
    }
    const now = performance.now()
    const elapsed = desktopStepAt > 0 ? Math.min(120, now - desktopStepAt) : 33
    desktopStepAt = now
    const step = Math.min(distance, Math.max(1, elapsed * 0.12))
    const monitor = await currentMonitor()
    const size = await appWindow.outerSize()
    if (!monitor) return
    const minX = monitor.workArea.position.x
    const minY = monitor.workArea.position.y
    const maxX = Math.max(minX, minX + monitor.workArea.size.width - size.width)
    const maxY = Math.max(minY, minY + monitor.workArea.size.height - size.height)
    desktopPosition = {
      x: Math.max(minX, Math.min(maxX, Math.round(desktopPosition.x + dx / distance * step))),
      y: Math.max(minY, Math.min(maxY, Math.round(desktopPosition.y + dy / distance * step))),
    }
    await appWindow.setPosition(new PhysicalPosition(desktopPosition.x, desktopPosition.y))
  } finally {
    desktopMoveBusy = false
  }
}

function startBehavior() {
  stopBehavior()
  behaviorTimer = window.setInterval(() => {
    if (!pet || chatBubbleVisible.value || apiPanelVisible.value || press) return
    if (Date.now() - lastUserInteraction.value < 12000) return
    if ((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
      void stepDesktopWander()
      return
    }
    const b = pet.getBounds()
    const halfW = Math.max(48, b.width / 2)
    const halfH = Math.max(80, b.height / 2)
    if (!wanderTarget) {
      if (Date.now() < nextWanderAt) return
      wanderTarget = {
        x: halfW + 12 + Math.random() * Math.max(1, window.innerWidth - halfW * 2 - 24),
        y: halfH + 12 + Math.random() * Math.max(1, window.innerHeight - halfH * 2 - 24),
      }
      pet.playMotionRandom('Idle').catch(() => {})
    }
    const p = pet.getPosition()
    const dx = wanderTarget.x - p.x
    const dy = wanderTarget.y - p.y
    const distance = Math.hypot(dx, dy)
    if (distance < 8) {
      wanderTarget = null
      desktopWalking = false
      pet.applyPose('idle', 1200)
      nextWanderAt = Date.now() + 3000 + Math.random() * 6000
    } else {
      const now = performance.now()
      const elapsed = desktopStepAt > 0 ? Math.min(120, now - desktopStepAt) : 33
      desktopStepAt = now
      const step = Math.max(1, elapsed * 0.12)
      pet.setPosition(p.x + dx / distance * step, p.y + dy / distance * step)
    }
  }, 33)
}
function stopBehavior() {
  if (behaviorTimer) clearInterval(behaviorTimer)
  behaviorTimer = undefined
  wanderTarget = null
  desktopWanderTarget = null
  desktopWalking = false
  desktopStepAt = 0
}

// ── M2：点击互动（数据流 A）──
function randomFace() {
  if (!pet) return
  pet.applyFace(FACES[Math.floor(Math.random() * FACES.length)])
  status.value = '换了个表情～'
  lastUserInteraction.value = Date.now()
}

function showReaction(x: number, y: number) {
  const marks = ['💗', '✨', '♪', '！', '🌸', '😊', '～']
  reaction.value = { text: marks[Math.floor(Math.random() * marks.length)], x, y }
  if (reactionTimer) clearTimeout(reactionTimer)
  reactionTimer = window.setTimeout(() => (reaction.value = null), 900)
}

type PetApiAction =
  | { type: 'motion'; group: string }
  | { type: 'face'; name: PetFace }
  | { type: 'say'; text: string }

function onApiAction(event: Event) {
  const action = (event as CustomEvent<PetApiAction>).detail
  if (!pet || !action) return
  lastUserInteraction.value = Date.now()
  if (action.type === 'motion') pet.playMotionRandom(action.group).catch(() => {})
  if (action.type === 'face') pet.applyFace(action.name)
  if (action.type === 'say') {
    subtitle.value = action.text
    openBubble()
  }
}

function inDesktopShell() {
  return !!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
}

type BubbleWindowLayout = {
  side: 'left' | 'right'
  baseWidth: number
  baseHeight: number
  baseX: number
  baseY: number
  extraWidth: number
}
let bubbleWindowLayout: BubbleWindowLayout | null = null
let bubbleWindowDesired = false
let bubbleWindowBusy = false
let bubbleWindowTransition: Promise<void> = Promise.resolve()

function waitForPaint() {
  return new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
}

async function normalizePetWindowSize() {
  if (!inDesktopShell()) return
  const appWindow = getCurrentWindow()
  const expectedWidth = Math.round(360 * zoomLevel.value)
  const expectedHeight = Math.round(600 * zoomLevel.value)
  const size = await appWindow.outerSize().catch(() => null)
  if (!size || (size.width <= expectedWidth + 4 && size.height <= expectedHeight + 4)) return
  await appWindow.setSize(new LogicalSize(expectedWidth, expectedHeight)).catch(() => {})
  const [position, monitor, nextSize] = await Promise.all([
    appWindow.outerPosition().catch(() => null),
    currentMonitor().catch(() => null),
    appWindow.outerSize().catch(() => null),
  ])
  if (!position || !monitor || !nextSize) return
  const minX = monitor.workArea.position.x
  const minY = monitor.workArea.position.y
  const maxX = Math.max(minX, minX + monitor.workArea.size.width - nextSize.width)
  const maxY = Math.max(minY, minY + monitor.workArea.size.height - nextSize.height)
  await appWindow.setPosition(new PhysicalPosition(
    Math.max(minX, Math.min(maxX, position.x)),
    Math.max(minY, Math.min(maxY, position.y)),
  )).catch(() => {})
}

function pinPetToBaseWindow(layout: BubbleWindowLayout) {
  if (!pet) return
  // The native window grows only to make room for the bubble. Keep Hiyori in
  // the original 360×600 visual area instead of re-centering her under it.
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  const baseWidth = layout.baseWidth / dpr
  const baseHeight = layout.baseHeight / dpr
  const extraWidth = layout.extraWidth / dpr
  pet.setPosition(
    layout.side === 'left' ? extraWidth + baseWidth / 2 : baseWidth / 2,
    baseHeight / 2,
  )
}

async function expandBubbleWindowNow() {
  if (!inDesktopShell() || !pet || !meta.value || bubbleWindowLayout) return
  const appWindow = getCurrentWindow()
  const [position, size, monitor] = await Promise.all([
    appWindow.outerPosition().catch(() => null),
    appWindow.outerSize().catch(() => null),
    currentMonitor().catch(() => null),
  ])
  if (!position || !size) return
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  const extraWidth = Math.ceil((236 * uiScale.value + 28) * dpr)
  const canExpandRight = !monitor || position.x + size.width + extraWidth <= monitor.workArea.position.x + monitor.workArea.size.width
  const canExpandLeft = !monitor || position.x - extraWidth >= monitor.workArea.position.x
  const layout: BubbleWindowLayout = {
    side: canExpandRight || !canExpandLeft ? 'right' : 'left',
    baseWidth: size.width,
    baseHeight: size.height,
    baseX: position.x,
    baseY: position.y,
    extraWidth,
  }
  // Mark the transition before awaiting native calls so a rapid close/open cannot start
  // another expansion from the already-expanded size.
  bubbleWindowLayout = layout
  if (layout.side === 'left') await appWindow.setPosition(new PhysicalPosition(position.x - extraWidth, position.y)).catch(() => {})
  await appWindow.setSize(new PhysicalSize(size.width + extraWidth, size.height)).catch(() => {})
  await waitForPaint()
  pet.syncRendererSize()
  if (meta.value) pet.resizeModel(meta.value)
  pinPetToBaseWindow(layout)
  await waitForPaint()
}

async function restoreBubbleWindowNow(layout: BubbleWindowLayout) {
  if (!inDesktopShell()) return
  const appWindow = getCurrentWindow()
  await appWindow.setSize(new PhysicalSize(layout.baseWidth, layout.baseHeight)).catch(() => {})
  await appWindow.setPosition(new PhysicalPosition(layout.baseX, layout.baseY)).catch(() => {})
  await waitForPaint()
  pet?.syncRendererSize()
  if (pet && meta.value) pet.resizeModel(meta.value)
}

async function reconcileBubbleWindow() {
  if (bubbleWindowBusy) return bubbleWindowTransition
  bubbleWindowBusy = true
  bubbleWindowTransition = (async () => {
    try {
      while (true) {
        if (bubbleWindowDesired) {
          if (!bubbleWindowLayout) await expandBubbleWindowNow()
          if (!bubbleWindowDesired) continue
          break
        }
        const layout = bubbleWindowLayout
        if (layout) {
          await restoreBubbleWindowNow(layout)
          if (!bubbleWindowDesired && bubbleWindowLayout === layout) bubbleWindowLayout = null
          continue
        }
        await normalizePetWindowSize()
        break
      }
    } finally {
      bubbleWindowBusy = false
      scheduleNativeHitRegion()
      if ((bubbleWindowDesired && !bubbleWindowLayout) || (!bubbleWindowDesired && bubbleWindowLayout)) void reconcileBubbleWindow()
    }
  })()
  return bubbleWindowTransition
}

function requestBubbleWindowState(visible: boolean) {
  bubbleWindowDesired = visible
  return reconcileBubbleWindow()
}

async function prepareBubble() {
  await nextTick()
  await requestBubbleWindowState(true)
  if (!chatBubbleVisible.value) return
  positionBubble()
  await waitForPaint()
  if (!chatBubbleVisible.value) return
  positionBubble()
  bubbleReady.value = true
  scheduleNativeHitRegion()
}

function positionBubble() {
  if (!pet || !chatBubbleVisible.value) return
  const b = pet.getBounds()
  const maxWidth = Math.min(236 * uiScale.value, Math.max(120, window.innerWidth - 16))
  const measured = bubble.value?.getBoundingClientRect()
  const height = measured?.height || Math.min(220 * uiScale.value, window.innerHeight - 16)
  const gap = 12
  const edge = 8
  const minSideWidth = Math.min(112 * uiScale.value, maxWidth)
  const rightSpace = Math.max(0, window.innerWidth - b.x - b.width - gap - edge)
  const leftSpace = Math.max(0, b.x - gap - edge)
  let side: 'left' | 'right' | 'top' | 'bottom' = bubbleWindowLayout?.side ?? (rightSpace >= leftSpace ? 'right' : 'left')
  let width = bubbleWindowLayout
    ? maxWidth
    : Math.min(maxWidth, Math.max(minSideWidth, side === 'right' ? rightSpace : leftSpace))
  if (!bubbleWindowLayout && (side === 'right' ? rightSpace : leftSpace) < minSideWidth) {
    side = side === 'right' ? 'left' : 'right'
    width = Math.min(maxWidth, Math.max(72, side === 'right' ? rightSpace : leftSpace))
  }
  const topSpace = Math.max(0, b.y - gap - edge)
  const bottomSpace = Math.max(0, window.innerHeight - b.y - b.height - gap - edge)
  if (!bubbleWindowLayout && topSpace >= height && topSpace > (side === 'right' ? rightSpace : leftSpace) && topSpace >= bottomSpace) {
    side = 'top'
    width = maxWidth
  } else if (!bubbleWindowLayout && bottomSpace >= height && bottomSpace > (side === 'right' ? rightSpace : leftSpace)) {
    side = 'bottom'
    width = maxWidth
  }
  const headY = b.y + b.height * 0.18
  const rawX = side === 'right'
    ? b.x + b.width + gap
    : side === 'left'
      ? b.x - width - gap
      : b.x + b.width / 2 - width / 2
  const rawY = side === 'top'
    ? b.y - height - gap
    : side === 'bottom'
      ? b.y + b.height + gap
      : headY - height * 0.42
  const x = Math.max(edge, Math.min(rawX, window.innerWidth - width - edge))
  const y = Math.max(edge, Math.min(rawY, window.innerHeight - height - edge))
  bubblePos.value = {
    x,
    y,
    width,
    side,
    arrowY: Math.max(18, Math.min(height - 18, headY - y)),
  }
}
function openBubble() {
  if (apiPanelVisible.value) return
  cancelBubbleDismiss()
  bubbleFading.value = false
  if (chatBubbleVisible.value) {
    positionBubble()
    armBubbleDismiss()
    return
  }
  bubbleReady.value = false
  chatBubbleVisible.value = true
  void prepareBubble()
  armBubbleDismiss()
}
async function closeBubble() {
  cancelBubbleDismiss()
  bubbleFading.value = false
  bubbleReady.value = false
  if (!chatBubbleVisible.value && !bubbleWindowLayout) return
  chatBubbleVisible.value = false
  await requestBubbleWindowState(false)
}

function cancelBubbleDismiss() {
  if (bubbleDismissTimer) clearTimeout(bubbleDismissTimer)
  if (bubbleFadeTimer) clearTimeout(bubbleFadeTimer)
  bubbleDismissTimer = undefined
  bubbleFadeTimer = undefined
}
function armBubbleDismiss() {
  cancelBubbleDismiss()
  if (!chatBubbleVisible.value || typing.value) return
  bubbleDismissTimer = window.setTimeout(() => {
    bubbleFading.value = true
    bubbleFadeTimer = window.setTimeout(() => closeBubble(), 500)
  }, 3000)
}

async function closePet() {
  if (hideInFlight) return
  hideInFlight = true
  try {
    await closeBubble()
    closeApiPanel()
    stopAutonomy()
    stopBehavior()
    desktopWanderTarget = null
    stopIdle()
    await getCurrentWindow().hide().catch(() => {})
  } finally {
    hideInFlight = false
  }
}

async function applyZoom(nextZoom: number) {
  if (!pet) return
  zoomLevel.value = Math.max(0.65, Math.min(2.2, nextZoom))
  const targetWidth = Math.round(360 * zoomLevel.value)
  const targetHeight = Math.round(600 * zoomLevel.value)
  if ((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    const appWindow = getCurrentWindow()
    const [beforePosition, beforeSize] = await Promise.all([
      appWindow.outerPosition().catch(() => null),
      appWindow.outerSize().catch(() => null),
    ])
    await appWindow.setSize(new LogicalSize(targetWidth, targetHeight)).catch(() => {})
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    pet.syncRendererSize()
    pet.setZoom(zoomLevel.value)
    if (meta.value) pet.resizeModel(meta.value)
    scheduleNativeHitRegion(260)
    if (beforePosition && beforeSize) {
      const afterSize = await appWindow.outerSize().catch(() => null)
      if (afterSize) {
        const nextPosition = {
          x: Math.round(beforePosition.x + (beforeSize.width - afterSize.width) / 2),
          y: Math.round(beforePosition.y + beforeSize.height - afterSize.height),
        }
        const monitor = await currentMonitor().catch(() => null)
        if (monitor) {
          const minX = monitor.workArea.position.x
          const minY = monitor.workArea.position.y
          const maxX = Math.max(minX, minX + monitor.workArea.size.width - afterSize.width)
          const maxY = Math.max(minY, minY + monitor.workArea.size.height - afterSize.height)
          nextPosition.x = Math.max(minX, Math.min(maxX, nextPosition.x))
          nextPosition.y = Math.max(minY, Math.min(maxY, nextPosition.y))
        }
        await appWindow.setPosition(new PhysicalPosition(nextPosition.x, nextPosition.y)).catch(() => {})
        desktopPosition = nextPosition
      }
    }
  } else {
    pet.setZoom(zoomLevel.value)
  }
  positionBubble()
  positionApiPanel()
  if (pendingZoom !== null) scheduleZoomFlush()
}
function scheduleZoomFlush() {
  if (zoomFrame !== undefined) return
  zoomFrame = requestAnimationFrame(() => {
    zoomFrame = undefined
    if (zoomBusy || pendingZoom === null) return
    const next = pendingZoom
    pendingZoom = null
    zoomBusy = true
    void applyZoom(next).finally(() => {
      zoomBusy = false
      if (pendingZoom !== null) scheduleZoomFlush()
    })
  })
}
function queueZoom(nextZoom: number) {
  pendingZoom = Math.max(0.65, Math.min(2.2, nextZoom))
  zoomLevel.value = pendingZoom
  scheduleZoomFlush()
}

let lastInteractAt = 0
function interactAt(x: number, y: number) {
  if (!pet) return
  const now = Date.now()
  if (now - lastInteractAt < 120) return
  lastInteractAt = now
  const hits = pet.hitTest(x, y)
  if (!hits.length && !pet.containsPoint(x, y)) return
  pet.focus(x, y)
  showReaction(x, y)
  lastUserInteraction.value = Date.now()
  status.value = hits.includes('Head') ? '摸摸头～' : hits.includes('Body') ? '被摸到了～' : '戳到啦～'
  tapCount += 1
  pet.playMotionRandom(tapCount % 3 === 0 || Math.random() < 0.35 ? 'Idle' : 'TapBody').catch(() => {})
  const poses: PetPose[] = hits.includes('Head')
    ? ['cute', 'happy', 'surprised']
    : ['happy', 'cute', 'angry', 'surprised']
  pet.applyPose(poses[Math.floor(Math.random() * poses.length)], 2800)
  if (meta.value?.expressions.length && Math.random() < 0.35) pet.playExpressionRandom().catch(() => {})
  else randomFace()
  maybeAutonomousTalk('你点击了我')
}

function onContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (!pet) return
  // 透明桌宠窗口本身只承载日和；不再用 Live2D 包围盒拦截右键，避免 DPI/缩放后点到身体边缘无响应。
  guideVisible.value = false
  desktopWanderTarget = null
  if (apiPanelVisible.value) closeApiPanel()
  else openApiPanel()
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0 || !pet) return
  const hits = pet.hitTest(e.offsetX, e.offsetY)
  if (!hits.length && !pet.containsPoint(e.offsetX, e.offsetY)) return
  closeBubble()
  desktopWanderTarget = null
  guideVisible.value = false
  canvas.value?.setPointerCapture(e.pointerId)
  press = { pointerId: e.pointerId, clientX: e.clientX, clientY: e.clientY, x: e.offsetX, y: e.offsetY }
  pet.focus(e.offsetX, e.offsetY)
}

// 移动超过阈值才拖窗；短按到 pointerup 才互动，避免 startDragging 吞掉单击。
function onPointerMove(e: PointerEvent) {
  if (!pet) return
  pet.focus(e.offsetX, e.offsetY)
  if (!press || press.pointerId !== e.pointerId) return
  if (Math.hypot(e.clientX - press.clientX, e.clientY - press.clientY) < 7) return
  press = null
  desktopWanderTarget = null
  lastUserInteraction.value = Date.now()
  maybeAutonomousTalk('你把我拖到了新的位置')
  void getCurrentWindow().startDragging().catch(() => {})
}
function onPointerUp(e: PointerEvent) {
  if (canvas.value?.hasPointerCapture(e.pointerId)) canvas.value.releasePointerCapture(e.pointerId)
  if (!press || press.pointerId !== e.pointerId) return
  const p = press
  press = null
  if (Math.hypot(e.clientX - p.clientX, e.clientY - p.clientY) < 7) interactAt(p.x, p.y)
}
function onPointerCancel(e: PointerEvent) {
  if (canvas.value?.hasPointerCapture(e.pointerId)) canvas.value.releasePointerCapture(e.pointerId)
  press = null
}

function onWheel(e: WheelEvent) {
  queueZoom(zoomLevel.value * (e.deltaY > 0 ? 0.9 : 1.1))
  maybeAutonomousTalk('你调整了我的大小')
  lastUserInteraction.value = Date.now()
}

</script>

<template>
  <div class="wrapper" :style="{ '--ui-scale': String(uiScale) }">
    <canvas
      ref="canvas"
      class="stage"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
      @wheel.prevent.stop="onWheel"
      @contextmenu.prevent.stop="onContextMenu"
    ></canvas>

    <div
      v-if="apiPanelVisible"
      ref="apiPanel"
      class="api-panel"
      :style="{ left: apiPanelPos.x + 'px', top: apiPanelPos.y + 'px' }"
      @pointerdown.stop
      @click.stop
       @contextmenu.prevent="closeApiPanel"
    >
      <div class="panel-head">
        <div><strong>连接 AI 对话</strong><div class="panel-subtitle">右键宠物可再次打开 / 关闭</div></div>
        <button type="button" class="icon-button" aria-label="关闭 API 设置" @click="closeApiPanel">×</button>
      </div>
      <div class="panel-status" :class="{ connected: apiStatus.configured }">{{ apiStatus.configured ? `已接入 · ${apiStatus.model}` : '当前未接入 API，将使用本地陪伴模式' }}</div>
      <label>服务 / 模型来源
        <select v-model="apiPreset" @change="selectApiPreset">
          <option v-for="preset in API_PRESETS" :key="preset.id" :value="preset.id">{{ preset.label }}</option>
        </select>
      </label>
      <label>协议
        <select v-model="apiForm.protocol">
          <option value="openai-compatible">OpenAI / 中转（兼容接口）</option>
          <option value="anthropic-messages">Anthropic Messages</option>
          <option value="gemini">Google Gemini</option>
        </select>
      </label>
      <label>接口地址
        <input v-model="apiForm.base_url" type="url" placeholder="https://api.openai.com/v1" />
      </label>
      <label>模型名称
        <input v-model="apiForm.model" type="text" placeholder="填写该服务控制台中的模型 ID" />
      </label>
      <label>API Key
        <input v-model="apiForm.api_key" type="password" placeholder="已保存可留空" autocomplete="off" />
      </label>
      <div class="api-actions">
        <button type="button" class="primary-action" :disabled="apiSaving" @click="saveApi">保存连接</button>
        <button type="button" class="secondary-action" :disabled="apiSaving || !apiStatus.configured" @click="clearApi">清除 API</button>
      </div>
      <div class="api-actions">
        <button type="button" class="secondary-action" :disabled="apiDiscovering" @click="discoverModels">{{ apiDiscovering ? '识别中…' : '识别模型' }}</button>
        <button type="button" class="secondary-action" :disabled="apiTesting || !apiForm.model" @click="testConnection">{{ apiTesting ? '测试中…' : '测试连接' }}</button>
      </div>
      <div class="api-actions">
        <button type="button" class="secondary-action" @click="importInput?.click()">导入模型 JSON</button>
        <input ref="importInput" type="file" accept=".json,application/json" hidden @change="importModelsFile" />
      </div>
      <div v-if="providerMessage" class="provider-message">{{ providerMessage }}</div>
      <div v-if="discoveredModels.length" class="discovery-result">
        <div class="catalog-title">本次识别结果 · {{ discoveredModels.length }} 个模型</div>
        <label v-for="model in discoveredModels" :key="`found-${model.protocol}-${model.base_url}-${model.id}`" class="discovery-row">
          <input v-model="model.enabled" type="checkbox" :aria-label="`启用识别到的 ${model.name}`" @change="setDiscoveredEnabled(model)" />
          <span class="discovery-info"><strong>{{ model.name }}</strong><small>模型 ID：{{ model.id }}</small><small>能力：{{ model.capabilities.join(' / ') }} · 任务：{{ model.tasks.join(' / ') }}</small></span>
        </label>
        <div class="api-actions">
          <button type="button" class="primary-action" :disabled="catalogSaving" @click="enableAllDiscovered">{{ catalogSaving ? '启动中…' : '一键启动全部' }}</button>
          <button type="button" class="secondary-action" @click="cancelDiscovery">取消本次识别</button>
        </div>
      </div>
      <div v-if="modelCatalog.length" class="model-catalog">
        <div class="catalog-title">模型目录 · 勾选启用 / 停用</div>
        <div v-for="model in modelCatalog" :key="model.protocol + model.base_url + model.id" class="model-row">
          <input v-model="model.enabled" type="checkbox" :aria-label="`启用 ${model.name || model.id}`" />
          <div class="model-info"><strong>{{ model.name || model.id }}</strong><small>模型 ID：{{ model.id }}</small><small>{{ model.protocol }} · {{ model.base_url }}</small></div>
          <select v-model="model.role" :aria-label="`${model.id} 协作角色`">
            <option value="primary">主模型</option>
            <option value="worker">协作</option>
            <option value="judge">裁决</option>
          </select>
        </div>
        <label class="collab-toggle"><input v-model="collaboration.enabled" type="checkbox" /> 启用多模型协作</label>
        <label v-if="collaboration.enabled">协作策略
          <select v-model="collaboration.strategy" class="strategy-select">
            <option value="fallback">故障转移（更稳）</option>
            <option value="parallel">并行汇总（更丰富）</option>
          </select>
        </label>
        <label v-if="collaboration.enabled">裁决模型（可选）
          <select v-model="collaboration.judge_model_id">
            <option :value="undefined">不指定</option>
            <option v-for="model in modelCatalog" :key="`judge-${model.id}`" :value="model.id">{{ model.name || model.id }}</option>
          </select>
        </label>
        <button type="button" class="primary-action catalog-save" :disabled="catalogSaving" @click="saveModelSettings">{{ catalogSaving ? '保存中…' : '保存模型与协作' }}</button>
      </div>
      <div v-if="apiError" class="bubble-error">⚠ {{ apiError }}</div>
      <small>内置常用国内外服务；“自定义接口”可填写其他官方或中转地址。识别不会发起生成请求，测试连接可能产生一次计费请求。</small>
    </div>

    <div
      v-if="reaction"
      class="reaction"
      :style="{ left: reaction.x + 'px', top: reaction.y + 'px' }"
    >{{ reaction.text }}</div>
    <div
      v-if="chatBubbleVisible"
      ref="bubble"
      class="chat-bubble"
      :class="[bubblePos.side, { fading: bubbleFading, ready: bubbleReady }]"
      :style="{ left: bubblePos.x + 'px', top: bubblePos.y + 'px', width: bubblePos.width + 'px', '--bubble-arrow-y': bubblePos.arrowY + 'px' }"
      @pointerdown.stop
      @click.stop
    >
      <div class="bubble-head"><strong>日和</strong><button type="button" @click="closeBubble">×</button></div>
      <div v-if="subtitle" class="bubble-text">{{ subtitle }}<span v-if="typing" class="caret">▌</span></div>
      <div v-if="pendingImage" class="pending-image"><img :src="pendingImage" alt="待发送图片" /><button type="button" @click="pendingImage = ''">×</button></div>
      <div class="bubble-input-row">
        <button type="button" class="attach-image" title="发送图片（多模态）" @click="imageInput?.click()">🖼</button>
        <input ref="imageInput" type="file" accept="image/*" hidden @change="pickImage" />
        <input v-model="inputText" type="text" placeholder="和日和聊聊…" @keydown.enter="sendText" />
        <button type="button" @click="sendText">发送</button>
      </div>
      <button class="dismiss-pet" type="button" @click="closePet">隐藏桌宠</button>
      <div v-if="wsError" class="bubble-error">⚠ {{ wsError }}</div>
    </div>
    <div v-if="guideVisible" class="guide">左键互动 · 按住拖动 · 滚轮缩放 · 右键 API 设置</div>

  </div>
</template>

<style>
html,
body,
#app {
  margin: 0;
  height: 100%;
}
body {
  background: transparent;
  overflow: hidden;
  font-family: system-ui, sans-serif;
}
.wrapper {
  width: 100vw;
  height: 100vh;
  position: relative;
  background: transparent !important;
  --ui-scale: 1;
}
.stage {
  width: 100%;
  height: 100%;
  display: block;
  background: transparent !important;
  touch-action: none;
}
.chat-bubble {
  position: absolute;
  z-index: 60;
  min-width: 0;
  max-width: calc(100vw - 16px);
  box-sizing: border-box;
  padding: calc(9px * var(--ui-scale));
  border: 1px solid rgba(91, 117, 145, 0.18);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  color: #2f435a;
  box-shadow: 0 8px 24px rgba(31, 55, 78, 0.2);
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.chat-bubble:not(.ready),
.chat-bubble.fading {
  opacity: 0;
  transform: translateY(4px);
  pointer-events: none;
}
.api-panel { max-height: calc(100vh - 16px); overflow-y: auto; position: absolute; z-index: 80; width: min(calc(286px * var(--ui-scale)), calc(100vw - 16px)); max-height: calc(100vh - 16px); overflow: auto; box-sizing: border-box; padding: calc(14px * var(--ui-scale)); border: 1px solid rgba(91, 117, 145, 0.2); border-radius: calc(16px * var(--ui-scale)); background: rgba(255, 255, 255, 0.98); color: #2f435a; box-shadow: 0 10px 30px rgba(31, 55, 78, 0.24); }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: calc(10px * var(--ui-scale)); }
.panel-subtitle { margin-top: 2px; color: #8a98a6; font-size: calc(10px * var(--ui-scale)); }
.panel-status { margin: 0 0 calc(8px * var(--ui-scale)); padding: calc(7px * var(--ui-scale)) calc(8px * var(--ui-scale)); border-radius: calc(9px * var(--ui-scale)); background: #fff8e8; color: #9a6d24; font-size: calc(11px * var(--ui-scale)); line-height: 1.35; }
.panel-status.connected { background: #f0faf4; color: #3f8058; }
.icon-button { border: 0; background: transparent; color: #8493a3; font-size: 20px; cursor: pointer; }
.api-panel label { display: block; margin: calc(8px * var(--ui-scale)) 0; color: #637489; font-size: calc(11px * var(--ui-scale)); }
.api-panel input, .api-panel select { width: 100%; box-sizing: border-box; margin-top: 4px; padding: calc(7px * var(--ui-scale)) calc(8px * var(--ui-scale)); border: 1px solid #d7e0e8; border-radius: calc(8px * var(--ui-scale)); outline: none; color: #2f435a; background: white; }
.api-panel input[type="checkbox"] { width: auto; min-width: 13px; padding: 0; margin: 3px 0 0; border: 1px solid #d7e0e8; border-radius: 3px; }
.model-catalog, .discovery-result { max-height: min(calc(46vh), calc(320px * var(--ui-scale))); overflow-y: auto; }
.api-actions { display: flex; flex-wrap: wrap; gap: calc(8px * var(--ui-scale)); margin-top: calc(10px * var(--ui-scale)); }
.api-actions button { flex: 1 1 110px; min-width: 0; border: 0; border-radius: calc(9px * var(--ui-scale)); padding: calc(7px * var(--ui-scale)) calc(8px * var(--ui-scale)); cursor: pointer; }
.primary-action { background: #6f9bc5; color: white; }
.secondary-action { background: #eef2f6; color: #637489; }
.api-actions button:disabled { cursor: wait; opacity: 0.55; }
.api-hint { margin-top: 4px; color: #9a6d24; font-size: calc(10px * var(--ui-scale)); line-height: 1.35; }
.provider-message { margin-top: 7px; padding: 6px 8px; border-radius: 8px; background: #f0faf4; color: #3f8058; font-size: calc(10px * var(--ui-scale)); line-height: 1.35; }
.discovery-result { margin-top: 10px; padding: 8px; border: 1px solid #d8eee0; border-radius: 9px; background: #f7fcf8; }
.discovery-row { display: flex; align-items: flex-start; gap: 6px; padding: 4px 0; color: #40566d; font-size: calc(10px * var(--ui-scale)); cursor: pointer; }
.discovery-row > input { flex: 0 0 auto; margin-top: 3px; }
.discovery-info { min-width: 0; flex: 1; }
.discovery-info strong, .discovery-info small { display: block; overflow-wrap: anywhere; line-height: 1.25; }
.discovery-info strong { color: #2f435a; }
.discovery-info small { margin-top: 2px; color: #7b8a98; font-size: calc(9px * var(--ui-scale)); }
.model-catalog { margin-top: 10px; padding-top: 8px; border-top: 1px solid #edf1f4; }
.catalog-title { margin-bottom: 6px; color: #637489; font-size: calc(11px * var(--ui-scale)); }
.model-row { display: flex; align-items: flex-start; gap: 6px; margin: 7px 0; font-size: calc(10px * var(--ui-scale)); }
.model-row > input { flex: 0 0 auto; margin-top: 3px; }
.model-info { min-width: 0; flex: 1; color: #40566d; }
.model-info strong, .model-info small { display: block; overflow-wrap: anywhere; white-space: normal; line-height: 1.25; }
.model-info small { margin-top: 2px; }
.model-info strong { color: #2f435a; }
.model-info small { color: #7b8a98; font-size: calc(9px * var(--ui-scale)); }
.model-info small { margin-top: 2px; }
.model-row select, .strategy-select { flex: 0 0 auto; width: auto; max-width: 76px; margin: 0; padding: 4px; font-size: calc(10px * var(--ui-scale)); }
.collab-toggle { display: flex !important; align-items: center; gap: 5px; margin: 8px 0 4px !important; }
.catalog-save { width: 100%; margin-top: 7px; }.api-panel small { display: block; margin-top: calc(9px * var(--ui-scale)); color: #8a98a6; font-size: calc(10px * var(--ui-scale)); line-height: 1.4; overflow-wrap: anywhere; }
.chat-bubble::after {
  content: '';
  position: absolute;
  top: var(--bubble-arrow-y, 28px);
  width: 12px;
  height: 12px;
  background: inherit;
  border-left: inherit;
  border-bottom: inherit;
  transform: rotate(45deg);
}
.chat-bubble.right::after { left: -7px; }
.chat-bubble.left::after { right: -7px; transform: rotate(225deg); }
.chat-bubble.top::after { left: calc(50% - 6px); top: auto; bottom: -7px; transform: rotate(315deg); }
.chat-bubble.bottom::after { left: calc(50% - 6px); top: -7px; transform: rotate(135deg); }
.bubble-head, .bubble-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.bubble-head { justify-content: space-between; margin-bottom: 6px; }
.bubble-head button {
  border: 0; background: transparent; color: #8493a3; font-size: 18px; cursor: pointer;
}
.bubble-text {
  min-height: calc(28px * var(--ui-scale));
  max-height: calc(92px * var(--ui-scale));
  overflow: auto;
  margin-bottom: 7px;
  font-size: 13px;
  line-height: 1.45;
}
.bubble-input-row input {
  min-width: 0; flex: 1; padding: calc(6px * var(--ui-scale)) calc(8px * var(--ui-scale)); border: 1px solid #d7e0e8; border-radius: 9px; outline: none;
}
.bubble-input-row button, .dismiss-pet {
  border: 0; border-radius: 9px; padding: 6px 8px; background: #6f9bc5; color: white; cursor: pointer;
}
.dismiss-pet {
  margin-top: 7px; background: transparent; color: #8898a8; font-size: 11px; padding: 2px 0;
}
.bubble-error { margin-top: 5px; color: #e74c3c; font-size: 11px; }
.attach-image { border: 0; background: transparent; font-size: 15px; cursor: pointer; padding: 0 2px; }
.pending-image { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.pending-image img { width: 44px; height: 44px; object-fit: cover; border-radius: 8px; border: 1px solid #d7e0e8; }
.pending-image button { border: 0; background: transparent; color: #8493a3; font-size: 15px; cursor: pointer; }
.subtitle {
  position: absolute;
  left: 50%;
  top: 12%;
  transform: translateX(-50%);
  max-width: 80%;
  background: rgba(255, 255, 255, 0.85);
  color: #234;
  padding: 6px 12px;
  border-radius: 12px;
  font-size: 14px;
  text-align: center;
  pointer-events: none;
}
.caret {
  opacity: 0.5;
}
.reaction {
  position: absolute;
  z-index: 40;
  transform: translate(-50%, -70%);
  font-size: 26px;
  pointer-events: none;
  animation: pop-away 0.9s ease-out forwards;
}
@keyframes pop-away {
  0% { opacity: 0; transform: translate(-50%, -40%) scale(0.6); }
  25% { opacity: 1; transform: translate(-50%, -80%) scale(1.15); }
  100% { opacity: 0; transform: translate(-50%, -150%) scale(0.9); }
}
.guide {
  position: absolute;
  z-index: 50;
  left: 50%;
  bottom: 48px;
  transform: translateX(-50%);
  width: max-content;
  max-width: calc(100vw - 56px);
  padding: 5px 9px;
  border-radius: 12px;
  background: rgba(35, 45, 58, 0.78);
  color: white;
  font-size: 11px;
  text-align: center;
  pointer-events: none;
}
</style>
