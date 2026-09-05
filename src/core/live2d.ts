// src/core/live2d.ts
// Live2d 单例：PIXI Application + Live2DModel（pixi-live2d-display@0.4.0, PIXI v6）
// 契约见 docs/CONTRACTS.md C1。API 以 pixi-live2d-display@0.4.0 实际类型为准（tsc --strict 已验证）。
import * as PIXI from 'pixi.js'
// Hiyori 等官方样例是 Cubism 4，走 /cubism4 入口。
// ⚠️ 运行时必须已存在全局 window.Live2DCubismCore（由 index.html 预加载 public/cubism-core/live2dcubismcore.min.js 提供）。
import { Live2DModel } from 'pixi-live2d-display/cubism4'

// pixi-live2d-display 通过 window.PIXI.Ticker 自动驱动模型更新，必须暴露。
;(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI

export interface ModelExpression {
  name: string
  file: string
}


export interface ModelMeta {
  width: number
  height: number
  // 动作组：键为组名（如 Idle / TapBody），值为该组动作定义数组。
  motions: Record<string, unknown[]>
  expressions: ModelExpression[]
}

export type PetPose =
  | 'idle' | 'walk' | 'lie' | 'kneel' | 'duck-sit'
  | 'happy' | 'angry' | 'cute' | 'surprised' | 'sleepy'

export class Live2d {
  private app: PIXI.Application | null = null
  private view: HTMLCanvasElement | null = null
  // 精确类型（pixi-live2d-display@0.4.0 已导出 Live2DModel）。
  private model: Live2DModel | null = null
  // 加载/resize 时的 contain 基准缩放，zoom 相对它计算。
  private baseScale = 0
  private zoomLevel = 1
  // 伪表情在 Cubism 每帧提交前回写，避免动作/眨眼覆盖；销毁模型时必须解绑。
  private paramOverrides: Record<string, number> = {}
  private poseTargets: Record<string, number> = {}
  private poseCurrent: Record<string, number> = {}
  private poseBase: Record<string, number> = {}
  private faceTimer: number | undefined
  private poseTimer: number | undefined
  private activePose: PetPose = 'idle'
  private poseStartedAt = 0
  // 不透明区域提取是 WebGL 回读，代价高；短 TTL 缓存避免每次点击/缩放都回读。
  private regionCache: Array<{ x: number; y: number; width: number; height: number }> | null = null
  private regionCacheAt = 0
  private paramHook: { off: (event: string, listener: () => void) => void } | null = null
  private paramListener: (() => void) | null = null

  initApp(canvas: HTMLCanvasElement): void {
    // PIXI v6/v7 通用构造器写法（v8 才改 await app.init()）。backgroundAlpha:0 保证透明。
    this.app = new PIXI.Application({
      view: canvas,
      backgroundAlpha: 0,
      resizeTo: window,
      resolution: window.devicePixelRatio || 1,
      antialias: true,
      autoStart: true,
    })
    this.view = canvas
    this.app.ticker.maxFPS = 120
    this.app.ticker.minFPS = 30
    this.syncRendererSize()
  }

  /** ResizePlugin 首帧可能仍是 PIXI 默认尺寸；加载前强制同步真实 WebView CSS 尺寸。 */
  syncRendererSize(): void {
    if (!this.app || !this.view) return
    const width = Math.max(1, Math.round(this.view.clientWidth || window.innerWidth))
    const height = Math.max(1, Math.round(this.view.clientHeight || window.innerHeight))
    if (this.app.screen.width !== width || this.app.screen.height !== height) {
      this.app.renderer.resize(width, height)
    }
  }

  async load(path: string): Promise<ModelMeta> {
    if (!this.app) throw new Error('Live2d.initApp() 必须先调用')
    // 先加载新模型，失败时保留当前模型，避免换装/换角色失败后出现空白窗口。
    const next = await Live2DModel.from(path)
    if (this.model) this.disposeModel()
    // path 为最终可访问 URL（Cubism 4 的 .model3.json）。
    // 本地模型需经 Tauri convertFileSrc 转 asset:// 后传入（在调用方处理，本方法只认 URL）。
    this.model = next
    this.app.stage.addChild(this.model)
    const meta = this.scanMeta()
    this.syncRendererSize()
    this.resizeModel(meta)
    return meta
  }

  private scanMeta(): ModelMeta {
    const m = this.model
    const motions: Record<string, unknown[]> = {}
    const rawMotions = (m as unknown as { motions?: Record<string, unknown[]> })?.motions
    if (rawMotions && typeof rawMotions === 'object') {
      for (const k of Object.keys(rawMotions)) motions[k] = rawMotions[k]
    }
    const expressions: ModelExpression[] = []
    const rawExpr = (m as unknown as { expressions?: ModelExpression[] })?.expressions
    if (Array.isArray(rawExpr)) {
      for (const e of rawExpr) expressions.push({ name: e?.name ?? '', file: e?.file ?? '' })
    }
    // Container.width/height can still be zero before PIXI completes its first bounds pass.
    // The internal model canvas is ready when Live2DModel.from resolves and is stable across DPI values.
    const internalSize = m?.internalModel as unknown as { width?: number; height?: number }
    const width = Number(internalSize?.width)
    const height = Number(internalSize?.height)
    return {
      width: Number.isFinite(width) && width > 0 ? width : (m?.width ?? 0),
      height: Number.isFinite(height) && height > 0 ? height : (m?.height ?? 0),
      motions,
      expressions,
    }
  }

  resizeModel(size: ModelMeta): void {
    if (!this.model || !this.app) return
    const sw = this.app.screen.width
    const sh = this.app.screen.height
    // contain 缩放（Math.min 保证宽高都不溢出 → 全身可见），留 4% 边距。
    if (this.baseScale <= 0) {
      this.baseScale = Math.min(sw / (size.width || 1), sh / (size.height || 1)) * 0.96
    }
    this.model.scale.set(this.baseScale * this.zoomLevel)
    this.model.anchor.set(0.5, 0.5)
    this.model.x = sw / 2
    this.model.y = sh / 2
  }

  // ── M2 互动 ───────────────────────────────────────────────
  /** 命中检测：返回点 (x,y) 命中的 hit area 名称数组（model3.json 的 HitAreas.Name）。空数组=未命中。 */
  hitTest(x: number, y: number): string[] {
    return this.model?.hitTest(x, y) ?? []
  }

  /**
   * 精确命中：点必须落在模型不透明轮廓内（world space，即 canvas CSS 像素）。
   * 不再使用模型包围盒兜底，避免透明的大矩形拦截桌面鼠标或触发互动。
   */
  containsPoint(x: number, y: number): boolean {
    if (!this.model) return false
    return this.getOpaqueRegions().some((rect) =>
      x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height,
    )
  }

  /**
   * 将模型渲染成低复杂度 alpha 区域，供 Windows 原生 HWND 命中区域使用。
   * 返回 canvas CSS 像素坐标；透明的模型包围盒不会拦截桌面鼠标。
   */
  getOpaqueRegions(padding = 3, force = false): Array<{ x: number; y: number; width: number; height: number }> {
    if (!this.model || !this.app) return []
    if (!force && this.regionCache && performance.now() - this.regionCacheAt < 400) return this.regionCache
    const rects = this.computeOpaqueRegions(padding)
    if (rects.length) {
      this.regionCache = rects
      this.regionCacheAt = performance.now()
    }
    return rects.length ? rects : (this.regionCache ?? [])
  }

  private computeOpaqueRegions(padding = 3): Array<{ x: number; y: number; width: number; height: number }> {
    if (!this.model || !this.app) return []
    // WebGL 的 extract 插件在部分 WebView2 驱动上会返回空像素；不能因此清除 HWND 区域，
    // 否则透明窗口会退化为整块长方形并拦截桌面。Hiyori 固定角色用紧凑分段轮廓兜底。
    let fallback: (() => Array<{ x: number; y: number; width: number; height: number }>) | undefined
    try {
      const bounds = this.model.getBounds()
      fallback = () => {
        const bands = [
          [0.08, 0.18, 0.36, 0.64], [0.16, 0.34, 0.31, 0.69],
          [0.28, 0.50, 0.29, 0.71], [0.45, 0.68, 0.35, 0.65],
          [0.64, 0.77, 0.32, 0.68], [0.74, 0.93, 0.39, 0.49],
          [0.74, 0.93, 0.51, 0.61], [0.90, 0.97, 0.34, 0.66],
        ]
        return bands.map(([y0, y1, x0, x1]) => ({
          x: Math.max(0, bounds.x + bounds.width * x0 - padding),
          y: Math.max(0, bounds.y + bounds.height * y0 - padding),
          width: Math.min(this.app!.screen.width, bounds.width * (x1 - x0) + padding * 2),
          height: Math.min(this.app!.screen.height, bounds.height * (y1 - y0) + padding * 2),
        }))
      }
      const resolution = Math.max(1, Number(this.app.renderer.resolution) || 1)
      const pixelWidth = Math.max(1, Math.round(bounds.width * resolution))
      const extract = (this.app.renderer as unknown as {
        plugins?: { extract?: { pixels: (target: unknown) => Uint8Array } }
      }).plugins?.extract
      const pixels = extract?.pixels(this.model)
      if (!pixels?.length) return fallback()
      const pixelHeight = Math.max(1, Math.floor(pixels.length / 4 / pixelWidth))
      const regions: Array<{ x: number; y: number; width: number; height: number }> = []
      for (let py = 0; py < pixelHeight; py += 6) {
        const yEnd = Math.min(pixelHeight, py + 6)
        let runStart = -1
        for (let px = 0; px <= pixelWidth; px += 4) {
          const xEnd = Math.min(pixelWidth, px + 4)
          let opaque = false
          for (let yy = py; yy < yEnd && !opaque; yy += 1) {
            for (let xx = px; xx < xEnd; xx += 1) {
              if ((pixels[(yy * pixelWidth + xx) * 4 + 3] ?? 0) > 18) {
                opaque = true
                break
              }
            }
          }
          const isLast = px + 4 >= pixelWidth
          if (opaque && runStart < 0) runStart = px
          if ((!opaque || isLast) && runStart >= 0) {
            const end = opaque && isLast ? pixelWidth : px
            const top = Math.max(0, bounds.y + py / resolution - padding)
            const x = Math.max(0, bounds.x + runStart / resolution - padding)
            const right = Math.min(this.app.screen.width, bounds.x + end / resolution + padding)
            const bottom = Math.min(this.app.screen.height, bounds.y + yEnd / resolution + padding)
            if (right > x && bottom > top) regions.push({ x, y: top, width: right - x, height: bottom - top })
            runStart = -1
          }
        }
      }
      return regions.length ? regions.slice(0, 240) : fallback()
    } catch {
      // A transient Live2D layout mutation should preserve the previous native
      // region in App.vue rather than turning the transparent window rectangular.
      return fallback?.() ?? []
    }
  }
  /** 当前模型的 world-space 包围盒，供聊天气泡和自动行为布局使用。 */
  getBounds(): { x: number; y: number; width: number; height: number } {
    const b = this.model?.getBounds()
    return b ? { x: b.x, y: b.y, width: b.width, height: b.height } : { x: 0, y: 0, width: 0, height: 0 }
  }

  // ── M4 互动扩展：注视 / 缩放 / 伪表情 ───────────────────────

  /** 视线跟随：眼睛与头部看向 (x,y)（world space）。底层 Live2DModel.focus 内部自行做坐标转换。 */
  focus(x: number, y: number): void {
    this.model?.focus(x, y)
  }

  /** 当前模型中心点（world space）。 */
  getPosition(): { x: number; y: number } {
    return { x: this.model?.x ?? 0, y: this.model?.y ?? 0 }
  }

  /** 设置模型中心点；自动行为使用，坐标始终限制在 canvas 内。 */
  setPosition(x: number, y: number): void {
    if (!this.model || !this.app) return
    const b = this.model.getBounds()
    const halfW = b.width / 2
    const halfH = b.height / 2
    this.model.x = Math.max(halfW, Math.min(this.app.screen.width - halfW, x))
    this.model.y = Math.max(halfH, Math.min(this.app.screen.height - halfH, y))
  }

  /** 当前缩放倍率（1 = 加载时 contain 基准）。 */
  get zoom(): number {
    return this.zoomLevel
  }

  /** 设置缩放倍率，范围钳制 [0.35, 3]，缩放围绕模型锚点（中心）。 */
  setZoom(z: number): void {
    if (!this.model) return
    this.zoomLevel = Math.max(0.35, Math.min(3, z))
    this.model.scale.set((this.baseScale || 1) * this.zoomLevel)
  }

  /** 参数化表情：不依赖 .exp3.json，Hiyori/Rice 等单表情模型也可用。 */
  applyFace(name: 'smile' | 'surprise' | 'blush' | 'wink' | 'reset', durationMs = 2500): void {
    if (!this.model) return
    this.ensureParamHook()
    if (this.faceTimer) clearTimeout(this.faceTimer)
    if (name === 'reset') {
      this.paramOverrides = {}
      return
    }
    const set = (id: string, ratio: number) => {
      const { min, max } = this.getParameterRange(id)
      const value = min + (max - min) * ratio
      if (Number.isFinite(value)) this.paramOverrides[id] = value
    }
    switch (name) {
      case 'smile':
        set('ParamMouthForm', 1)
        set('ParamEyeLOpen', 0.9)
        set('ParamEyeROpen', 0.9)
        set('ParamEyeLSmile', 1)
        set('ParamEyeRSmile', 1)
        break
      case 'surprise':
        set('ParamMouthOpenY', 0.8)
        set('ParamEyeLOpen', 1)
        set('ParamEyeROpen', 1)
        set('ParamBrowLY', 0.8)
        set('ParamBrowRY', 0.8)
        break
      case 'blush':
        set('ParamCheek', 1)
        set('ParamMouthForm', 0.8)
        break
      case 'wink':
        set('ParamEyeLOpen', 1)
        set('ParamEyeROpen', 0)
        set('ParamMouthForm', 0.9)
        break
    }
    this.faceTimer = window.setTimeout(() => {
      this.paramOverrides = {}
      this.faceTimer = undefined
    }, durationMs)
  }

  /** 参数化姿态：仅使用模型实际存在的参数，平滑进入并在时限后回到原始姿态。 */
  applyPose(pose: PetPose, durationMs = 3600): void {
    if (!this.model) return
    this.ensureParamHook()
    if (this.poseTimer) clearTimeout(this.poseTimer)
    this.activePose = pose
    this.poseStartedAt = performance.now()
    this.poseTargets = {}
    const core = (this.model.internalModel as unknown as { coreModel?: {
      getParameterIndex: (id: string) => number
      getParameterValueById?: (id: string) => number
    } }).coreModel
    const set = (id: string, ratio: number) => {
      if (!core) return
      try {
        if (core.getParameterIndex(id) < 0) return
        const { min, max } = this.getParameterRange(id)
        const value = min + (max - min) * Math.max(0, Math.min(1, ratio))
        if (!(id in this.poseBase)) {
          const current = core.getParameterValueById?.(id)
          this.poseBase[id] = Number.isFinite(current) ? current as number : value
          this.poseCurrent[id] = this.poseBase[id]
        }
        this.poseTargets[id] = value
      } catch { /* 模型不支持的参数静默跳过 */ }
    }
    const neutral = () => {
      set('ParamBodyAngleX', 0.5); set('ParamBodyAngleY', 0.5); set('ParamBodyAngleZ', 0.5)
      set('ParamLeg', 0.5); set('ParamArmLA', 0.5); set('ParamArmRA', 0.5)
      set('ParamHandL', 0.5); set('ParamHandR', 0.5)
    }
    neutral()
    switch (pose) {
      case 'walk': set('ParamBodyAngleX', 0.58); set('ParamBodyAngleY', 0.54); set('ParamBodyAngleZ', 0.56); set('ParamLeg', 0.38); set('ParamArmLA', 0.68); set('ParamArmRA', 0.32); break
      case 'lie': set('ParamBodyAngleY', 0.2); set('ParamBodyAngleZ', 0.42); set('ParamLeg', 0.2); set('ParamArmLA', 0.42); set('ParamArmRA', 0.58); break
      case 'kneel': set('ParamBodyAngleY', 0.43); set('ParamBodyAngleZ', 0.52); set('ParamLeg', 0.28); set('ParamArmLA', 0.62); set('ParamArmRA', 0.38); break
      case 'duck-sit': set('ParamBodyAngleY', 0.34); set('ParamBodyAngleZ', 0.5); set('ParamLeg', 0.14); set('ParamArmLA', 0.55); set('ParamArmRA', 0.45); break
      case 'happy': set('ParamMouthForm', 0.92); set('ParamEyeLOpen', 0.86); set('ParamEyeROpen', 0.86); set('ParamEyeLSmile', 1); set('ParamEyeRSmile', 1); break
      case 'angry': set('ParamMouthForm', 0.18); set('ParamBrowLY', 0.18); set('ParamBrowRY', 0.18); set('ParamBodyAngleZ', 0.54); break
      case 'cute': set('ParamMouthForm', 0.78); set('ParamCheek', 0.8); set('ParamBodyAngleZ', 0.47); set('ParamEyeLSmile', 0.9); set('ParamEyeRSmile', 0.9); break
      case 'surprised': set('ParamMouthOpenY', 0.78); set('ParamEyeLOpen', 1); set('ParamEyeROpen', 1); set('ParamBrowLY', 0.86); set('ParamBrowRY', 0.86); break
      case 'sleepy': set('ParamEyeLOpen', 0.28); set('ParamEyeROpen', 0.28); set('ParamBodyAngleY', 0.46); break
    }
    this.poseTimer = window.setTimeout(() => {
      this.poseTargets = {}
      this.activePose = 'idle'
      this.poseStartedAt = performance.now()
      this.poseTimer = undefined
    }, Math.max(800, durationMs))
  }

  /** 在 beforeModelUpdate 回写，确保覆盖动作、原生表情、眨眼和注视的本帧结果。 */
  private ensureParamHook(): void {
    if (this.paramHook || !this.model) return
    const internal = this.model.internalModel as unknown as {
      on: (event: string, listener: () => void) => void
      off: (event: string, listener: () => void) => void
      coreModel: { setParameterValueById: (id: string, value: number) => void }
    }
    const listener = () => {
      const elapsed = Math.max(0, (performance.now() - this.poseStartedAt) / 1000)
      const wave = Math.sin(elapsed * 8)
      const sway = Math.sin(elapsed * 4)
      const ids = new Set([...Object.keys(this.poseBase), ...Object.keys(this.poseTargets)])
      for (const id of ids) {
        const target = this.poseTargets[id] ?? this.poseBase[id]
        const current = this.poseCurrent[id] ?? target
        const range = this.getParameterRange(id)
        const span = range.max - range.min
        let animatedTarget = target
        if (this.activePose === 'walk') {
          if (id === 'ParamLeg') animatedTarget += span * 0.12 * wave
          if (id === 'ParamArmLA' || id === 'ParamArmRA') animatedTarget += span * 0.08 * (id === 'ParamArmLA' ? wave : -wave)
          if (id === 'ParamBodyAngleZ') animatedTarget += span * 0.04 * sway
        } else if (this.activePose === 'happy' || this.activePose === 'cute') {
          if (id === 'ParamBodyAngleZ') animatedTarget += span * 0.025 * sway
          if (id === 'ParamBustY' || id === 'ParamRibbon') animatedTarget += span * 0.06 * wave
        } else if (this.activePose === 'sleepy') {
          if (id === 'ParamBodyAngleY') animatedTarget += span * 0.025 * sway
        }
        animatedTarget = Math.max(range.min, Math.min(range.max, animatedTarget))
        const next = current + (animatedTarget - current) * 0.18
        this.poseCurrent[id] = next
        internal.coreModel.setParameterValueById(id, next)
      }
      for (const [id, value] of Object.entries(this.paramOverrides)) {
        if (Number.isFinite(value)) internal.coreModel.setParameterValueById(id, value)
      }
    }
    internal.on('beforeModelUpdate', listener)
    this.paramHook = internal
    this.paramListener = listener
  }

  /** 列出所有动作组名（如 ['Idle','TapBody']）。 */
  getMotionGroups(): string[] {
    const raw = (this.model as unknown as { motions?: Record<string, unknown[]> })?.motions
    return raw ? Object.keys(raw) : []
  }

  /** 随机播一个动作组里的某个动作；组不存在则静默。 */
  async playMotionRandom(group: string): Promise<void> {
    const raw = (this.model as unknown as { motions?: Record<string, unknown[]> })?.motions
    const arr = raw?.[group]
    if (Array.isArray(arr) && arr.length) {
      const i = Math.floor(Math.random() * arr.length)
      await this.playMotion(group, i)
    }
  }

  /** 随机播一个表情；无表情则静默。 */
  async playExpressionRandom(): Promise<void> {
    const exprs = (this.model as unknown as { expressions?: ModelExpression[] })?.expressions
    if (Array.isArray(exprs) && exprs.length) {
      const i = Math.floor(Math.random() * exprs.length)
      await this.playExpressions(i)
    }
  }

  async playMotion(group: string, index: number): Promise<void> {
    if (this.model) await this.model.motion(group, index)
  }

  async playExpressions(index: number): Promise<void> {
    if (this.model) this.model.expression(index)
  }

  getParameterRange(id: string): { min: number; max: number } {
    // Cubism Core 的 min/max API 接受参数索引，不接受字符串 ID。
    const cm = (this.model?.internalModel as unknown as { coreModel?: {
      getParameterIndex: (id: string) => number
      getParameterCount: () => number
      getParameterMinimumValue: (index: number) => number
      getParameterMaximumValue: (index: number) => number
    } })?.coreModel
    try {
      if (cm) {
        const index = cm.getParameterIndex(id)
        if (index >= 0 && index < cm.getParameterCount()) {
          const min = cm.getParameterMinimumValue(index)
          const max = cm.getParameterMaximumValue(index)
          if (Number.isFinite(min) && Number.isFinite(max) && max > min) return { min, max }
        }
      }
    } catch {
      /* 使用安全默认范围 */
    }
    return { min: 0, max: 1 }
  }

  setParameterValue(id: string, value: number | boolean): void {
    const coreModel = (this.model?.internalModel as unknown as {
      coreModel?: { setParameterValueById: (id: string, value: number) => void }
    })?.coreModel
    if (!coreModel) return
    coreModel.setParameterValueById(id, typeof value === 'boolean' ? Number(value) : value)
  }

  private disposeModel(): void {
    if (this.faceTimer) clearTimeout(this.faceTimer)
    if (this.poseTimer) clearTimeout(this.poseTimer)
    if (this.paramHook && this.paramListener) this.paramHook.off('beforeModelUpdate', this.paramListener)
    this.faceTimer = undefined
    this.poseTimer = undefined
    this.paramHook = null
    this.paramListener = null
    this.paramOverrides = {}
    this.poseTargets = {}
    this.poseCurrent = {}
    this.poseBase = {}
    this.activePose = 'idle'
    this.poseStartedAt = 0
    if (this.model) {
      this.app?.stage.removeChild(this.model)
      this.model.destroy()
      this.model = null
    }
    this.baseScale = 0
    this.zoomLevel = 1
  }

  destroy(): void {
    this.disposeModel()
    if (this.app) {
      this.app.destroy(true)
      this.app = null
    }
    this.view = null
  }
}
