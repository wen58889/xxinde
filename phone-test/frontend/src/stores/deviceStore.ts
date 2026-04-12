import { create } from 'zustand'
import { Device, DeviceStatus } from '../types/device'
import { devicesApi } from '../api/devices'

export interface VisionTarget {
  label: string
  x: number
  y: number
  w: number
  h: number
  kind?: string
  confidence?: number
}

interface DeviceStore {
  devices: Device[]
  selectedDeviceId: number | null
  refreshTick: number
  visionTargets: VisionTarget[]
  currentFrameSrc: string
  currentFrameBlob: Blob | null
  armLinkEnabled: boolean
  setDevices: (devices: Device[]) => void
  fetchDevices: () => Promise<void>
  updateDeviceStatus: (id: number, status: DeviceStatus) => void
  selectDevice: (id: number | null) => void
  selectedDevice: () => Device | undefined
  triggerRefresh: () => void
  setVisionTargets: (targets: VisionTarget[]) => void
  clearVisionTargets: () => void
  setCurrentFrameSrc: (src: string) => void
  setCurrentFrameBlob: (blob: Blob | null) => void
  setArmLinkEnabled: (v: boolean) => void
}

export const useDeviceStore = create<DeviceStore>((set, get) => ({
  devices: [],
  selectedDeviceId: null,
  refreshTick: 0,
  visionTargets: [],
  currentFrameSrc: '',
  currentFrameBlob: null,
  armLinkEnabled: false,
  setDevices: (devices) => set({ devices }),
  triggerRefresh: () => set((s) => ({ refreshTick: s.refreshTick + 1 })),
  setVisionTargets: (targets) => set({ visionTargets: targets }),
  clearVisionTargets: () => set({ visionTargets: [] }),
  setCurrentFrameSrc: (src) => set({ currentFrameSrc: src }),
  setCurrentFrameBlob: (blob) => set({ currentFrameBlob: blob }),
  setArmLinkEnabled: (v) => set({ armLinkEnabled: v }),
  fetchDevices: async () => {
    try {
      const list = await devicesApi.list()
      set({ devices: list })
    } catch {
      /* ignore */
    }
  },
  updateDeviceStatus: (id, status) =>
    set((s) => ({
      devices: s.devices.map((d) => (d.id === id ? { ...d, status } : d)),
    })),
  selectDevice: (id) => set({ selectedDeviceId: id, visionTargets: [], currentFrameSrc: '', currentFrameBlob: null }),
  selectedDevice: () => {
    const s = get()
    return s.devices.find((d) => d.id === s.selectedDeviceId)
  },
}))
