import { create } from 'zustand'

export interface AgentStepInfo {
  step: number
  observation: string
  thought: string
  action: string
  actionDetail: Record<string, unknown>
  result: string
  timestamp: number
  phase: 'observing' | 'thinking' | 'acting' | 'done'
}

interface AgentStore {
  running: boolean
  task: string
  steps: AgentStepInfo[]
  currentStep: number
  currentPhase: AgentStepInfo['phase'] | ''
  statusMessage: string

  setRunning: (v: boolean) => void
  setTask: (t: string) => void
  reset: () => void

  onObserve: (device_id: number, step: number, observation: string) => void
  onThink: (device_id: number, step: number, thought: string, action: string) => void
  onStep: (device_id: number, data: Partial<AgentStepInfo> & { step: number }) => void
  onStatus: (device_id: number, status: string, extra?: Record<string, unknown>) => void
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  running: false,
  task: '',
  steps: [],
  currentStep: 0,
  currentPhase: '',
  statusMessage: '',

  setRunning: (v) => set({ running: v }),
  setTask: (t) => set({ task: t }),
  reset: () => set({ running: false, task: '', steps: [], currentStep: 0, currentPhase: '', statusMessage: '' }),

  onObserve: (_device_id, step, observation) => {
    const { steps } = get()
    const existing = steps.find((s) => s.step === step)
    if (existing) {
      set({
        currentStep: step,
        currentPhase: 'observing',
        steps: steps.map((s) => (s.step === step ? { ...s, observation, phase: 'observing' as const } : s)),
      })
    } else {
      set({
        currentStep: step,
        currentPhase: 'observing',
        steps: [
          ...steps,
          { step, observation, thought: '', action: '', actionDetail: {}, result: '', timestamp: Date.now() / 1000, phase: 'observing' },
        ],
      })
    }
  },

  onThink: (_device_id, step, thought, action) => {
    const { steps } = get()
    const existing = steps.find((s) => s.step === step)
    if (existing) {
      set({
        currentStep: step,
        currentPhase: 'thinking',
        steps: steps.map((s) => (s.step === step ? { ...s, thought, action, phase: 'thinking' as const } : s)),
      })
    } else {
      set({
        currentStep: step,
        currentPhase: 'thinking',
        steps: [
          ...steps,
          { step, observation: '', thought, action, actionDetail: {}, result: '', timestamp: Date.now() / 1000, phase: 'thinking' },
        ],
      })
    }
  },

  onStep: (_device_id, data) => {
    const { steps } = get()
    const existing = steps.find((s) => s.step === data.step)
    const updated: AgentStepInfo = {
      step: data.step,
      observation: data.observation || (existing?.observation ?? ''),
      thought: data.thought || (existing?.thought ?? ''),
      action: data.action || (existing?.action ?? ''),
      actionDetail: data.actionDetail || (existing?.actionDetail ?? {}),
      result: data.result || (existing?.result ?? ''),
      timestamp: data.timestamp || (existing?.timestamp ?? Date.now() / 1000),
      phase: data.action === 'done' || data.action === 'fail' ? 'done' : 'acting',
    }
    if (existing) {
      set({
        currentStep: data.step,
        currentPhase: updated.phase,
        steps: steps.map((s) => (s.step === data.step ? { ...s, ...updated } : s)),
      })
    } else {
      set({
        currentStep: data.step,
        currentPhase: updated.phase,
        steps: [...steps, updated],
      })
    }
  },

  onStatus: (_device_id, status, extra) => {
    if (status === 'running') {
      set({ running: true, task: (extra?.task as string) || get().task, statusMessage: 'Agent 运行中...' })
    } else if (status === 'done') {
      set({ running: false, currentPhase: 'done', statusMessage: `Agent 完成，共 ${extra?.steps ?? '?'} 步` })
    } else if (status === 'error') {
      set({ running: false, currentPhase: '', statusMessage: `Agent 出错，已完成 ${extra?.steps ?? '?'} 步` })
    }
  },
}))
