import { Rule, SubAction } from '../types/rule'

/**
 * Convert a SubAction to YAML step lines.
 */
function subActionLines(sub: SubAction): string[] {
  const lines: string[] = []
  const sx = ((sub.x / 1280) * 100).toFixed(1)
  const sy = ((sub.y / 720) * 100).toFixed(1)
  const cnt = Math.max(1, sub.loopCount)

  for (let i = 0; i < cnt; i++) {
    if (sub.actionType === '点击') {
      if (sub.longPress > 0) {
        lines.push(`  - action: long_press`)
        lines.push(`    screen_percent: [${sx}, ${sy}]`)
        lines.push(`    seconds: ${(sub.longPress / 1000).toFixed(2)}`)
      } else {
        lines.push(`  - action: tap`)
        lines.push(`    screen_percent: [${sx}, ${sy}]`)
      }
    } else if (sub.actionType === '滑屏') {
      lines.push(`  - action: swipe_up`)
      lines.push(`    screen_percent: [${sx}, ${sy}]`)
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
    const px = ((rule.x / 1280) * 100).toFixed(1)
    const py = ((rule.y / 720) * 100).toFixed(1)
    const count = Math.max(1, rule.count)

    if (rule.actionType === '点击') {
      for (let i = 0; i < count; i++) {
        if (rule.longPress > 0) {
          lines.push(`  - action: long_press`)
          lines.push(`    screen_percent: [${px}, ${py}]`)
          lines.push(`    seconds: ${(rule.longPress / 1000).toFixed(2)}`)
        } else {
          lines.push(`  - action: tap`)
          lines.push(`    screen_percent: [${px}, ${py}]`)
        }
      }
    } else if (rule.actionType === '滑屏') {
      const dx = rule.slideX - rule.x
      const dy = rule.slideY - rule.y
      let dir = 'swipe_up'
      if (Math.abs(dx) >= Math.abs(dy)) {
        dir = dx >= 0 ? 'swipe_right' : 'swipe_left'
      } else {
        dir = dy >= 0 ? 'swipe_down' : 'swipe_up'
      }
      lines.push(`  - action: ${dir}`)
      lines.push(`    screen_percent: [${px}, ${py}]`)
      if (rule.slideDuration > 0) {
        lines.push(`    duration_ms: ${rule.slideDuration}`)
      }
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
