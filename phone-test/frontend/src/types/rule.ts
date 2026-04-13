export type ActionType = '点击' | '滑屏' | 'TTS' | '识图' | '识字'
export type PositionMode = '中心' | '相对' | '坐标'

export interface SubAction {
  id: string
  actionType: ActionType
  x: number
  y: number
  radius: number
  count: number
  longPress: number
  probability: number
  waitMin: number
  waitMax: number
  note: string
  // 滑屏专用
  slideX: number
  slideY: number
  slideDuration: number
  // 识图专用
  templateName: string
  threshold: number
  // 识字专用
  keyword: string
}

export interface Rule {
  id: string
  name: string
  expanded: boolean
  actionType: ActionType
  positionMode: PositionMode
  x: number
  y: number
  radius: number
  count: number
  longPress: number
  timer: number
  probability: number
  slideDuration: number
  slideX: number
  slideY: number
  waitMin: number
  waitMax: number
  detectArea: [number, number, number, number, number, number, number, number]
  ttsText: string
  // 识图专用
  templateName: string
  threshold: number
  // 识字专用
  keyword: string
  subActions: SubAction[]
}

export interface Template {
  id: number
  app_name: string
  name: string
  yaml_content: string
  version: number
  created_at: string
}
