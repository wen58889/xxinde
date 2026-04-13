import { Rule, SubAction } from '../types/rule'

// Camera resolution: 720 (width) x 1280 (height)
const CAM_W = 720
const CAM_H = 1280

/**
 * Convert pixel coordinates to screen_percent [x%, y%]
 * Camera image is 720 wide x 1280 tall
 */
function toPercent(px: number, py: number): [number, number] {
  return [
    Number(((px / CAM_W) * 100).toFixed(1)),
    Number(((py / CAM_H) * 100).toFixed(1)),
  ]
}

/**
 * Convert a SubAction to YAML step lines.
 */
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
    }
  }

  if (sub.waitMax > 0) {
    const sec = ((sub.waitMin + sub.waitMax) / 2).toFixed(1)
    lines.push(`  - action: wait`)
    lines.push(`    seconds: ${sec}`)
  }

  return lines
}

/**
 * Convert ruleStore rules to YAML string for FlowEngine.
 */
export function rulesToYaml(rules: Rule[]): string {
  const lines: string[] = ['steps:']

  for (const rule of rules) {
    const [px, py] = toPercent(rule.x, rule.y)
    const count = Math.max(1, rule.count)

    // Timer delay before rule
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
    }

    // Wait between rule actions
    if (rule.waitMax > 0) {
      const sec = ((rule.waitMin + rule.waitMax) / 2).toFixed(1)
      lines.push(`  - action: wait`)
      lines.push(`    seconds: ${sec}`)
    }

    // Sub-actions
    for (const sub of rule.subActions) {
      lines.push(...subActionLines(sub))
    }
  }

  return lines.join('\n')
}
