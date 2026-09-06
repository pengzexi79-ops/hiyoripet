// src/core/outfit.ts
// 分部位换装引擎：对 Hiyori 纹理图集（texture_01.png，衣物专用图集）做区域重新着色，
// 然后预填充 PIXI 纹理缓存并让模型整体热重载。参考思路：Live2D 官方 texture swap +
// VPet-Simulator 的分类衣柜（按部位独立换装）。
// 为什么走"重着色 + 缓存预填充 + 模型重载"：Live2D 的 Cubism 渲染器持有自己的 GL 纹理
// 句柄，运行时改写 PIXI 纹理像素/直接 texImage2D 都不会反映到画面上（真机已验证）；
// 而模型重载走的是成熟加载管线，缓存命中后必定使用新纹理。
import * as PIXI from 'pixi.js'

export interface OutfitMask {
  // 归一化矩形 [x0, y0, x1, y1]，相对图集宽高。
  rect: [number, number, number, number]
}

export interface OutfitOption {
  id: string
  label: string
  // null = 恢复原色；off=true 表示该选项是"脱下"（把掩码区域擦成透明）。
  color: [number, number, number] | null
  off?: boolean
}

export interface OutfitCategory {
  id: string
  label: string
  masks: OutfitMask[]
  options: OutfitOption[]
  supportsOff?: boolean
  note?: string
}

// 掩码基于 Hiyori.2048/texture_01.png（衣物图集）实测，归一化到 0-1。
const ATLAS_URL = '/models/Hiyori/Hiyori.2048/texture_01.png'
const STORAGE_KEY = 'hiyori-outfits-v1'

export const OUTFIT_CATEGORIES: OutfitCategory[] = [
  {
    id: 'coat',
    label: '外套',
    supportsOff: true,
    masks: [
      // 针织开衫主体（连通域 #1，size 32967）
      { rect: [0.006, 0.008, 0.352, 0.590] },
      // 八段袖子（右侧区域连通域实测）
      { rect: [0.820, 0.660, 0.986, 0.990] },
      { rect: [0.664, 0.264, 0.873, 0.568] },
      { rect: [0.805, 0.144, 0.904, 0.426] },
      { rect: [0.642, 0.700, 0.738, 0.990] },
      { rect: [0.744, 0.580, 0.836, 0.867] },
      { rect: [0.883, 0.008, 0.990, 0.268] },
      { rect: [0.592, 0.008, 0.695, 0.272] },
      { rect: [0.707, 0.010, 0.805, 0.289] },
    ],
    options: [
      { id: 'cream', label: '奶油', color: null },
      { id: 'sakura', label: '樱花粉', color: [244, 167, 189] },
      { id: 'mint', label: '薄荷绿', color: [168, 224, 190] },
      { id: 'sky', label: '天空蓝', color: [158, 205, 240] },
      { id: 'wine', label: '酒红', color: [172, 78, 92] },
      { id: 'charcoal', label: '炭灰', color: [110, 112, 122] },
      { id: 'off', label: '脱下', color: null, off: true },
    ],
  },
  {
    id: 'top',
    label: '上衣（水手服领）',
    masks: [
      // 藏青色水手领（带白条纹，连通域实测）
      { rect: [0.250, 0.830, 0.458, 0.958] },
    ],
    options: [
      { id: 'navy', label: '藏青', color: null },
      { id: 'red', label: '红色', color: [176, 84, 92] },
      { id: 'green', label: '墨绿', color: [82, 112, 94] },
      { id: 'purple', label: '深紫', color: [122, 92, 152] },
      { id: 'brown', label: '咖啡', color: [132, 100, 78] },
    ],
  },
  {
    id: 'inner',
    label: '内衣',
    masks: [
      // 开衫领口的白色内搭衬衫（连通域实测）
      { rect: [0.148, 0.085, 0.234, 0.208] },
    ],
    options: [
      { id: 'white', label: '纯白', color: null },
      { id: 'pink', label: '浅粉', color: [248, 196, 208] },
      { id: 'blue', label: '浅蓝', color: [190, 214, 244] },
      { id: 'black', label: '黑色', color: [72, 74, 84] },
    ],
    note: '当前模型只有领口内搭网格；完整内衣替换需自定义纹理包。',
  },
  {
    id: 'bottom',
    label: '下衣',
    masks: [
      // 百褶裙（藏青+白条纹，连通域群实测）
      { rect: [0.006, 0.580, 0.340, 0.778] },
    ],
    options: [
      { id: 'navy', label: '藏青', color: null },
      { id: 'wine', label: '酒红', color: [150, 70, 84] },
      { id: 'forest', label: '墨绿', color: [78, 110, 92] },
      { id: 'beige', label: '米白', color: [214, 208, 196] },
      { id: 'gray', label: '中灰', color: [118, 122, 130] },
      { id: 'caramel', label: '焦糖', color: [176, 138, 96] },
    ],
  },
  {
    id: 'socks',
    label: '袜子',
    supportsOff: true,
    masks: [
      // 左右两只中筒袜（连通域实测，避开大腿皮肤）
      { rect: [0.403, 0.480, 0.502, 0.795] },
      { rect: [0.523, 0.480, 0.642, 0.795] },
    ],
    options: [
      { id: 'navy', label: '藏青', color: null },
      { id: 'black', label: '黑色', color: [56, 58, 66] },
      { id: 'white', label: '白色', color: [232, 232, 236] },
      { id: 'pink', label: '浅粉', color: [240, 188, 200] },
      { id: 'gray', label: '烟灰', color: [140, 144, 152] },
      { id: 'off', label: '脱下', color: null, off: true },
    ],
  },
  {
    id: 'shoes',
    label: '鞋子',
    masks: [
      // 两只棕色皮鞋（连通域群实测）
      { rect: [0.012, 0.748, 0.205, 0.888] },
    ],
    options: [
      { id: 'brown', label: '棕色', color: null },
      { id: 'black', label: '黑色', color: [58, 58, 64] },
      { id: 'red', label: '红色', color: [188, 84, 84] },
      { id: 'white', label: '白色', color: [230, 228, 224] },
    ],
  },
  {
    id: 'deco',
    label: '装饰（领结）',
    supportsOff: true,
    masks: [
      // 胸口蓝色蝴蝶结
      { rect: [0.018, 0.862, 0.096, 0.928] },
      // 两条蓝色飘带
      { rect: [0.232, 0.768, 0.264, 0.836] },
      { rect: [0.380, 0.768, 0.410, 0.842] },
    ],
    options: [
      { id: 'blue', label: '蓝色', color: null },
      { id: 'red', label: '红色', color: [206, 88, 96] },
      { id: 'pink', label: '粉色', color: [240, 170, 190] },
      { id: 'black', label: '黑色', color: [64, 64, 70] },
      { id: 'off', label: '脱下', color: null, off: true },
    ],
  },
]

type Rect = { x: number; y: number; w: number; h: number }

function toPixelRects(masks: OutfitMask[], width: number, height: number): Rect[] {
  return masks.map(({ rect }) => ({
    x: Math.floor(rect[0] * width),
    y: Math.floor(rect[1] * height),
    w: Math.max(1, Math.ceil((rect[2] - rect[0]) * width)),
    h: Math.max(1, Math.ceil((rect[3] - rect[1]) * height)),
  }))
}

function loadSelection(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') as Record<string, string>
  } catch {
    return {}
  }
}

export function currentSelection(): Record<string, string> {
  return loadSelection()
}

export function persistSelection(selection: Record<string, string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selection))
  } catch {
    // 隐私模式等场景下持久化失败不致命，仅本次会话生效。
  }
}

let originalAtlas: HTMLCanvasElement | null = null

async function ensureOriginalAtlas(): Promise<HTMLCanvasElement> {
  if (originalAtlas) return originalAtlas
  const response = await fetch(ATLAS_URL)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    originalAtlas = document.createElement('canvas')
    originalAtlas.width = image.naturalWidth
    originalAtlas.height = image.naturalHeight
    originalAtlas.getContext('2d')!.drawImage(image, 0, 0)
  } finally {
    URL.revokeObjectURL(url)
  }
  return originalAtlas
}

/** 对画布上的一组矩形做保明暗重新着色：out = 原色×0.22 + 目标色×(最大通道/255)×0.78。
 * 接近白色的像素（水手服白条纹、缝线）保持原样，避免条纹被染色消失。 */
function recolorRects(ctx: CanvasRenderingContext2D, rects: Rect[], color: [number, number, number]): void {
  for (const rect of rects) {
    const image = ctx.getImageData(rect.x, rect.y, rect.w, rect.h)
    const data = image.data
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] === 0) continue
      if (Math.min(data[i], data[i + 1], data[i + 2]) > 205) continue
      const maxc = Math.max(data[i], data[i + 1], data[i + 2])
      const f = maxc / 255
      data[i] = Math.min(255, Math.round(data[i] * 0.22 + color[0] * f * 0.78))
      data[i + 1] = Math.min(255, Math.round(data[i + 1] * 0.22 + color[1] * f * 0.78))
      data[i + 2] = Math.min(255, Math.round(data[i + 2] * 0.22 + color[2] * f * 0.78))
    }
    ctx.putImageData(image, rect.x, rect.y)
  }
}

/** 把一组矩形擦成透明（"脱下"衣物：该网格失去纹理后不再渲染）。 */
function eraseRects(ctx: CanvasRenderingContext2D, rects: Rect[]): void {
  for (const rect of rects) {
    ctx.clearRect(rect.x, rect.y, rect.w, rect.h)
  }
}

/** 按选择重着色/擦除衣物图集并预填充 PIXI 纹理缓存（键与 pixi-live2d-display 的加载键一致）。
 * 必须在 pet.load() 之前调用；模型重载后即使用新纹理。 */
export async function prepareOutfitTextures(selection: Record<string, string>): Promise<void> {
  const original = await ensureOriginalAtlas()
  const work = document.createElement('canvas')
  work.width = original.width
  work.height = original.height
  const ctx = work.getContext('2d')!
  ctx.drawImage(original, 0, 0)
  for (const category of OUTFIT_CATEGORIES) {
    const optionId = selection[category.id]
    if (!optionId) continue
    const option = category.options.find((item) => item.id === optionId)
    if (!option) continue
    if (option.off) {
      eraseRects(ctx, toPixelRects(category.masks, work.width, work.height))
    } else if (option.color) {
      recolorRects(ctx, toPixelRects(category.masks, work.width, work.height), option.color)
    }
  }
  const base = new PIXI.BaseTexture(work as unknown as { width: number })
  const texture = new PIXI.Texture(base)
  PIXI.BaseTexture.addToCache(base, ATLAS_URL)
  PIXI.Texture.addToCache(texture, ATLAS_URL)
}
