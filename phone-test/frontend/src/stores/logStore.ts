import { create } from 'zustand'

export interface LogEntry {
  id: number
  time: string
  message: string
  level: 'info' | 'error' | 'success' | 'warn'
}

let logId = 0

interface LogStore {
  logs: LogEntry[]
  addLog: (message: string, level?: LogEntry['level']) => void
  clear: () => void
}

export const useLogStore = create<LogStore>((set) => ({
  logs: [],
  addLog: (message, level = 'info') => {
    const now = new Date()
    const time = now.toTimeString().slice(0, 8)
    set((s) => ({
      logs: [...s.logs.slice(-200), { id: logId++, time, message, level }],
    }))
  },
  clear: () => set({ logs: [] }),
}))
