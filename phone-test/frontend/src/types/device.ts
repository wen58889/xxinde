export type DeviceStatus = 'ONLINE' | 'SUSPECT' | 'OFFLINE' | 'RECOVERING' | 'ESTOP'

export interface Device {
  id: number
  ip: string
  hostname: string
  status: DeviceStatus
  firmware_version?: string
  last_heartbeat?: string
}
