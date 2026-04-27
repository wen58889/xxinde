import { Rule, SubAction } from '../types/rule'

const CAM_W = 720
const CAM_H = 1280

function toPercent(px: number, py: number): [number, number] {
  return [
    Number(((px / CAM_W) * 100).toFixed(1)),
    Number(((py / CAM_H) * 100).toFixed(1)),
  ]
}

function toPixel(sx: number, sy: number): [number, number] {
  return [
    Math.round((sx / 100) * CAM_W),
    Math.round((sy / 100) * CAM_H),
  ]
}

let _ruleCounter = 1
let _subCounter = 1

function nextRuleId() { return `rule-${_ruleCounter++}` }
function nextSubId() { return `sub-${_subCounter++}` }

function makeRule(overrides: Partial<Rule> = {}): Rule {
  return {
    id: nextRuleId(),
    name: '新规则',
    expanded: false,
    actionType: '点击',
    positionMode: '坐标',
    x: 0, y: 0,
    radius: 0.005,
    count: 1,
    longPress: 0,
    timer: 0,
    probability: 1,
    slideDuration: 0,
    slideX: 0, slideY: 0,
    waitMin: 1, waitMax: 2,
    detectArea: [0, 0, 0, 0, 0, 0, 0, 0],
    ttsText: '',
    templateName: '',
    threshold: 0.85,
    keyword: '',
    subActions: [],
    ...overrides,
  }
}

function subActionLines(sub: SubAction): string[] {
  const lines: string[] = []
  const [sx, sy] = toPercent(sub.x, sub.y)
  const cnt = Math.max(1, sub.count)

  for (let i = 0; i < cnt; i++) {
    if (sub.actionType === '点击') {
      if (sub.longPress > 0) {
        lines.push(`  - action: long_press`)
        lines.push(`    screen_percent: [${sx}, ${sy}]`)
        lines.push(`    seconds: ${sub.longPress.toFixed(2)}`)
      } else {
        lines.push(`  - action: tap`)
        lines.push(`    screen_percent: [${sx}, ${sy}]`)
      }
    } else if (sub.actionType === '滑屏') {
      const [ex, ey] = toPercent(sub.slideX, sub.slideY)
      lines.push(`  - action: swipe`)
      lines.push(`    start_percent: [${sx}, ${sy}]`)
      lines.push(`    end_percent: [${ex}, ${ey}]`)
      if (sub.slideDuration > 0) {
        lines.push(`    duration_ms: ${sub.slideDuration}`)
      }
    } else if (sub.actionType === 'TTS') {
      lines.push(`  - action: tts`)
      lines.push(`    text: "${(sub.note || '').replace(/"/g, '\\"')}"`)
    } else if (sub.actionType === '识图') {
      lines.push(`  - action: tap_icon`)
      lines.push(`    template: "${(sub.templateName || '').replace(/"/g, '\\"')}"`)
      if (sub.threshold > 0 && sub.threshold !== 1) {
        lines.push(`    threshold: ${sub.threshold}`)
      }
    } else if (sub.actionType === '识字') {
      lines.push(`  - action: tap_text`)
      lines.push(`    keyword: "${(sub.keyword || '').replace(/"/g, '\\"')}"`)
    }
  }

  if (sub.waitMax > 0) {
    const sec = ((sub.waitMin + sub.waitMax) / 2).toFixed(1)
    lines.push(`  - action: wait`)
    lines.push(`    seconds: ${sec}`)
  }

  return lines
}

export function rulesToYaml(rules: Rule[]): string {
  const lines: string[] = ['steps:']

  for (const rule of rules) {
    const [px, py] = toPercent(rule.x, rule.y)
    const count = Math.max(1, rule.count)

    if (rule.timer > 0) {
      lines.push(`  - action: wait`)
      lines.push(`    seconds: ${rule.timer.toFixed(1)}`)
    }

    if (rule.actionType === '点击') {
      for (let i = 0; i < count; i++) {
        if (rule.longPress > 0) {
          lines.push(`  - action: long_press`)
          lines.push(`    screen_percent: [${px}, ${py}]`)
          lines.push(`    seconds: ${rule.longPress.toFixed(2)}`)
        } else {
          lines.push(`  - action: tap`)
          lines.push(`    screen_percent: [${px}, ${py}]`)
        }
      }
    } else if (rule.actionType === '滑屏') {
      const [ex, ey] = toPercent(rule.slideX, rule.slideY)
      for (let i = 0; i < count; i++) {
        lines.push(`  - action: swipe`)
        lines.push(`    start_percent: [${px}, ${py}]`)
        lines.push(`    end_percent: [${ex}, ${ey}]`)
        if (rule.slideDuration > 0) {
          lines.push(`    duration_ms: ${rule.slideDuration}`)
        }
      }
    } else if (rule.actionType === 'TTS') {
      lines.push(`  - action: tts`)
      lines.push(`    text: "${(rule.ttsText || '').replace(/"/g, '\\"')}"`)
    } else if (rule.actionType === '识图') {
      lines.push(`  - action: tap_icon`)
      lines.push(`    template: "${(rule.templateName || '').replace(/"/g, '\\"')}"`)
      if (rule.threshold > 0 && rule.threshold !== 1) {
        lines.push(`    threshold: ${rule.threshold}`)
      }
    } else if (rule.actionType === '识字') {
      lines.push(`  - action: tap_text`)
      lines.push(`    keyword: "${(rule.keyword || '').replace(/"/g, '\\"')}"`)
    }

    if (rule.waitMax > 0) {
      const sec = ((rule.waitMin + rule.waitMax) / 2).toFixed(1)
      lines.push(`  - action: wait`)
      lines.push(`    seconds: ${sec}`)
    }

    for (const sub of rule.subActions) {
      lines.push(...subActionLines(sub))
    }
  }

  return lines.join('\n')
}

function parseValue(val: string): any {
  val = val.trim()
  if (val.startsWith('[') && val.endsWith(']')) {
    const inner = val.slice(1, -1)
    return inner.split(',').map((s: string) => {
      const n = Number(s.trim())
      return isNaN(n) ? s.trim().replace(/^["']|["']$/g, '') : n
    })
  }
  if (val.startsWith('"') && val.endsWith('"')) return val.slice(1, -1)
  if (val.startsWith("'") && val.endsWith("'")) return val.slice(1, -1)
  const num = Number(val)
  if (!isNaN(num)) return num
  return val
}

function parseYamlSteps(yaml: string): Record<string, any>[] {
  const lines = yaml.split('\n')
  let stepsStarted = false
  const steps: Record<string, any>[] = []
  let current: Record<string, any> | null = null

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '')
    if (!line.trim() || line.trim().startsWith('#')) continue

    if (/^steps\s*:/.test(line.trim())) {
      stepsStarted = true
      continue
    }
    if (!stepsStarted) continue

    const listMatch = line.match(/^(\s*)-\s+action\s*:\s*(.+)$/)
    if (listMatch) {
      if (current) steps.push(current)
      current = { action: listMatch[2].trim() }
      continue
    }

    const kvMatch = line.match(/^(\s+)(\w+)\s*:\s*(.+)$/)
    if (kvMatch && current) {
      current[kvMatch[2]] = parseValue(kvMatch[3])
    }
  }

  if (current) steps.push(current)
  return steps
}

function parsePercentCoords(val: any): [number, number] {
  if (Array.isArray(val) && val.length >= 2) {
    return toPixel(Number(val[0]), Number(val[1]))
  }
  return [0, 0]
}

function parseWait(val: any): [number, number] {
  if (Array.isArray(val) && val.length >= 2) {
    return [Number(val[0]), Number(val[1])]
  }
  if (typeof val === 'number') {
    return [val, val]
  }
  return [1, 2]
}

export function yamlToRules(yaml: string): Rule[] {
  const steps = parseYamlSteps(yaml)
  if (steps.length === 0) return []

  _ruleCounter = 1
  _subCounter = 1

  const rules: Rule[] = []
  let i = 0

  while (i < steps.length) {
    const step = steps[i]
    const action = String(step.action || '')

    if (action === 'wait') {
      const sec = Number(step.seconds || 1)
      if (rules.length > 0) {
        const last = rules[rules.length - 1]
        last.waitMin = sec
        last.waitMax = sec
      }
      i++
      continue
    }

    if (action === 'tap' || action === 'long_press') {
      const [x, y] = parsePercentCoords(step.screen_percent)
      const name = step.description ? String(step.description) : `点击 (${x}, ${y})`
      const [wMin, wMax] = parseWait(step.wait)
      rules.push(makeRule({
        name,
        actionType: '点击',
        x, y,
        longPress: action === 'long_press' ? Number(step.seconds || 0) : 0,
        waitMin: wMin, waitMax: wMax,
      }))
      i++
      continue
    }

    if (action === 'swipe') {
      const [sx, sy] = parsePercentCoords(step.start_percent)
      const [ex, ey] = parsePercentCoords(step.end_percent)
      const name = step.description ? String(step.description) : `滑屏`
      const [wMin, wMax] = parseWait(step.wait)
      const dur = Number(step.duration_ms || 0)
      rules.push(makeRule({
        name,
        actionType: '滑屏',
        x: sx, y: sy,
        slideX: ex, slideY: ey,
        slideDuration: dur,
        waitMin: wMin, waitMax: wMax,
      }))
      i++
      continue
    }

    if (action === 'tap_icon') {
      const name = step.description ? String(step.description) : `识图 ${(step.template || '')}`
      const [wMin, wMax] = parseWait(step.wait)
      rules.push(makeRule({
        name,
        actionType: '识图',
        templateName: String(step.template || ''),
        threshold: Number(step.threshold || 0.85),
        waitMin: wMin, waitMax: wMax,
      }))
      i++
      continue
    }

    if (action === 'tap_text') {
      const name = step.description ? String(step.description) : `识字 ${(step.keyword || '')}`
      const [wMin, wMax] = parseWait(step.wait)
      rules.push(makeRule({
        name,
        actionType: '识字',
        keyword: String(step.keyword || ''),
        waitMin: wMin, waitMax: wMax,
      }))
      i++
      continue
    }

    if (action === 'tts') {
      const name = step.description ? String(step.description) : `TTS`
      const [wMin, wMax] = parseWait(step.wait)
      rules.push(makeRule({
        name,
        actionType: 'TTS',
        ttsText: String(step.text || ''),
        waitMin: wMin, waitMax: wMax,
      }))
      i++
      continue
    }

    if (action === 'detect_state') {
      const name = step.description ? String(step.description) : '状态检测'
      const [wMin, wMax] = parseWait(step.wait)
      const keywords = step.ocr_keywords
      const templates = step.templates
      if (Array.isArray(keywords) && keywords.length > 0) {
        rules.push(makeRule({
          name,
          actionType: '识字',
          keyword: keywords.map((k: any) => String(k)).join(', '),
          waitMin: wMin, waitMax: wMax,
        }))
      } else if (Array.isArray(templates) && templates.length > 0) {
        rules.push(makeRule({
          name,
          actionType: '识图',
          templateName: String(templates[0] || ''),
          waitMin: wMin, waitMax: wMax,
        }))
      } else {
        rules.push(makeRule({ name, waitMin: wMin, waitMax: wMax }))
      }
      i++
      continue
    }

    rules.push(makeRule({
      name: step.description ? String(step.description) : action,
    }))
    i++
  }

  return rules
}
