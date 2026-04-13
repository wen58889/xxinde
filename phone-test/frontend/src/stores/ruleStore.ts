import { create } from 'zustand'
import { Rule, SubAction, ActionType } from '../types/rule'

let ruleCounter = 1
let subCounter = 1

function createRule(name?: string): Rule {
  const id = `rule-${ruleCounter++}`
  return {
    id,
    name: name || `新规则 ${ruleCounter - 1}`,
    expanded: true,
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
    subActions: [],
  }
}

function createSubAction(): SubAction {
  return {
    id: `sub-${subCounter++}`,
    actionType: '点击',
    x: 0, y: 0,
    radius: 0.005,
    count: 1,
    longPress: 0,
    probability: 1,
    waitMin: 1, waitMax: 2,
    note: '',
    slideX: 0, slideY: 0,
    slideDuration: 0,
  }
}

interface RuleStore {
  rules: Rule[]
  selectedRuleId: string | null

  addRule: (afterId?: string) => void
  removeRule: (id: string) => void
  duplicateRule: (id: string) => void
  updateRule: (id: string, partial: Partial<Rule>) => void
  toggleExpand: (id: string) => void
  selectRule: (id: string | null) => void

  addSubAction: (ruleId: string) => void
  removeSubAction: (ruleId: string, subId: string) => void
  updateSubAction: (ruleId: string, subId: string, partial: Partial<SubAction>) => void
  reorderSubActions: (ruleId: string, fromIndex: number, toIndex: number) => void

  setCoordinate: (x: number, y: number) => void
  clearAll: () => void
  loadRules: (rules: Rule[]) => void
}

export const useRuleStore = create<RuleStore>((set, get) => ({
  rules: [createRule()],
  selectedRuleId: null,

  addRule: (afterId) =>
    set((s) => {
      const newRule = createRule()
      if (afterId) {
        const idx = s.rules.findIndex((r) => r.id === afterId)
        const arr = [...s.rules]
        arr.splice(idx + 1, 0, newRule)
        return { rules: arr }
      }
      return { rules: [...s.rules, newRule] }
    }),

  removeRule: (id) =>
    set((s) => ({ rules: s.rules.filter((r) => r.id !== id) })),

  duplicateRule: (id) =>
    set((s) => {
      const idx = s.rules.findIndex((r) => r.id === id)
      if (idx < 0) return s
      const src = s.rules[idx]
      const dup: Rule = {
        ...JSON.parse(JSON.stringify(src)),
        id: `rule-${ruleCounter++}`,
        name: `${src.name} (副本)`,
        subActions: src.subActions.map((sa) => ({
          ...JSON.parse(JSON.stringify(sa)),
          id: `sub-${subCounter++}`,
        })),
      }
      const arr = [...s.rules]
      arr.splice(idx + 1, 0, dup)
      return { rules: arr }
    }),

  updateRule: (id, partial) =>
    set((s) => ({
      rules: s.rules.map((r) => (r.id === id ? { ...r, ...partial } : r)),
    })),

  toggleExpand: (id) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === id ? { ...r, expanded: !r.expanded } : r
      ),
    })),

  selectRule: (id) => set({ selectedRuleId: id }),

  addSubAction: (ruleId) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === ruleId
          ? { ...r, subActions: [...r.subActions, createSubAction()] }
          : r
      ),
    })),

  removeSubAction: (ruleId, subId) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === ruleId
          ? { ...r, subActions: r.subActions.filter((sa) => sa.id !== subId) }
          : r
      ),
    })),

  updateSubAction: (ruleId, subId, partial) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === ruleId
          ? {
              ...r,
              subActions: r.subActions.map((sa) =>
                sa.id === subId ? { ...sa, ...partial } : sa
              ),
            }
          : r
      ),
    })),

  reorderSubActions: (ruleId, fromIndex, toIndex) =>
    set((s) => ({
      rules: s.rules.map((r) => {
        if (r.id !== ruleId) return r
        const arr = [...r.subActions]
        const [moved] = arr.splice(fromIndex, 1)
        arr.splice(toIndex, 0, moved)
        return { ...r, subActions: arr }
      }),
    })),

  setCoordinate: (x, y) => {
    const { selectedRuleId, rules } = get()
    if (!selectedRuleId) return
    set({
      rules: rules.map((r) =>
        r.id === selectedRuleId ? { ...r, x, y } : r
      ),
    })
  },

  clearAll: () => set({ rules: [createRule()], selectedRuleId: null }),

  loadRules: (rules) => set({ rules }),
}))
