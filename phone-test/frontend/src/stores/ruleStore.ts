import { create } from 'zustand'
import { Rule, SubAction, ActionType } from '../types/rule'

let ruleCounter = 1
let subCounter = 1

function createRule(name?: string): Rule {
  const id = `rule-${ruleCounter++}`
  return {
    id,
    name: name || `新规则 ${ruleCounter - 1}`,
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
    templateName: '',
    threshold: 0.85,
    keyword: '',
  }
}

function deepCloneRule(r: Rule): Rule {
  return {
    ...r,
    detectArea: [...r.detectArea] as Rule['detectArea'],
    subActions: r.subActions.map(sa => ({ ...sa })),
  }
}

interface RuleStore {
  rules: Rule[]
  selectedRuleId: string | null
  selectedSubId: string | null

  addRule: (afterId?: string) => void
  removeRule: (id: string) => void
  duplicateRule: (id: string) => void
  updateRule: (id: string, partial: Partial<Rule>) => void
  toggleExpand: (id: string) => void
  selectRule: (id: string | null) => void
  selectSub: (subId: string | null) => void

  addSubAction: (ruleId: string) => void
  removeSubAction: (ruleId: string, subId: string) => void
  updateSubAction: (ruleId: string, subId: string, partial: Partial<SubAction>) => void
  reorderSubActions: (ruleId: string, fromIndex: number, toIndex: number) => void
  reorderRules: (fromIndex: number, toIndex: number) => void

  setCoordinate: (x: number, y: number) => void
  clearAll: () => void
  loadRules: (rules: Rule[]) => void
}

export const useRuleStore = create<RuleStore>((set, get) => ({
  rules: [createRule()],
  selectedRuleId: null,
  selectedSubId: null,

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
    set((s) => ({ rules: s.rules.filter((r) => r.id !== id), selectedRuleId: s.selectedRuleId === id ? null : s.selectedRuleId })),

  duplicateRule: (id) =>
    set((s) => {
      const idx = s.rules.findIndex((r) => r.id === id)
      if (idx < 0) return s
      const src = s.rules[idx]
      const dup: Rule = {
        ...deepCloneRule(src),
        id: `rule-${ruleCounter++}`,
        name: `${src.name} (副本)`,
        subActions: src.subActions.map((sa) => ({
          ...sa,
          id: `sub-${subCounter++}`,
        })),
      }
      const arr = [...s.rules]
      arr.splice(idx + 1, 0, dup)
      return { rules: arr }
    }),

  updateRule: (id, partial) =>
    set((s) => ({
      rules: s.rules.map((r) => {
        if (r.id !== id) return r
        const merged: Rule = { ...r, ...partial }
        if ('detectArea' in partial && partial.detectArea) merged.detectArea = [...partial.detectArea] as Rule['detectArea']
        if ('subActions' in partial && partial.subActions) merged.subActions = partial.subActions.map((sa) => ({ ...sa }))
        return merged
      }),
    })),

  toggleExpand: (id) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === id ? { ...r, expanded: !r.expanded } : r
      ),
    })),

  selectRule: (id) => set({ selectedRuleId: id }),

  selectSub: (subId) => set({ selectedSubId: subId }),

  addSubAction: (ruleId) =>
    set((s) => {
      const newSub = createSubAction()
      return {
        rules: s.rules.map((r) =>
          r.id === ruleId
            ? { ...r, subActions: [...r.subActions, newSub] }
            : r
        ),
        selectedSubId: newSub.id,
      }
    }),

  removeSubAction: (ruleId, subId) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.id === ruleId
          ? { ...r, subActions: r.subActions.filter((sa) => sa.id !== subId) }
          : r
      ),
      selectedSubId: s.selectedSubId === subId ? null : s.selectedSubId,
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

  reorderRules: (fromIndex, toIndex) =>
    set((s) => {
      const arr = [...s.rules]
      const [moved] = arr.splice(fromIndex, 1)
      arr.splice(toIndex, 0, moved)
      return { rules: arr }
    }),

  setCoordinate: (x, y) => {
    const { selectedRuleId, selectedSubId, rules } = get()
    if (!selectedRuleId) return

    if (selectedSubId) {
      const rule = rules.find((r) => r.id === selectedRuleId)
      const subExists = rule?.subActions.some((sa) => sa.id === selectedSubId)
      if (subExists) {
        set({
          rules: rules.map((r) =>
            r.id === selectedRuleId
              ? {
                  ...r,
                  subActions: r.subActions.map((sa) =>
                    sa.id === selectedSubId ? { ...sa, x, y } : sa
                  ),
                }
              : r
          ),
        })
        return
      }
    }

    set({
      rules: rules.map((r) =>
        r.id === selectedRuleId ? { ...r, x, y } : r
      ),
    })
  },

  clearAll: () => {
    ruleCounter = 1
    subCounter = 1
    set({ rules: [createRule()], selectedRuleId: null, selectedSubId: null })
  },

  loadRules: (rules) => {
    ruleCounter = 1
    subCounter = 1
    const cloned = rules.map((r) => {
      const rule = JSON.parse(JSON.stringify(r)) as Rule
      ruleCounter = Math.max(ruleCounter, parseInt(rule.id.replace('rule-', ''), 10) + 1)
      rule.subActions.forEach((sa) => {
        subCounter = Math.max(subCounter, parseInt(sa.id.replace('sub-', ''), 10) + 1)
      })
      return rule
    })
    set({ rules: cloned, selectedRuleId: null, selectedSubId: null })
  },
}))
