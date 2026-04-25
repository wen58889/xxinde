import client from './client'
import { Device } from '../types/device'

export const devicesApi = {
  list: () => client.get<Device[]>('/devices').then(r => r.data),
  scan: () => client.post<Device[]>('/devices/scan').then(r => r.data),
  status: (id: number) => client.get<Device>(`/devices/${id}/status`).then(r => r.data),
  snapshot: (id: number) => `/api/v1/devices/${id}/snapshot?t=${Date.now()}`,
  home: (id: number) => client.post(`/devices/${id}/home`),
  reset: (id: number) => client.post(`/devices/${id}/reset`),
  estop: (id: number) => client.post(`/devices/${id}/estop`),
  execute: (id: number, action: string, params: Record<string, unknown> = {}) =>
    client.post(`/devices/${id}/execute`, { action, params }),
  stop: (id: number) => client.post(`/devices/${id}/stop`),
  calibrate: (id: number, data: { pixel_points: number[][]; mech_points: number[][]; offset_x?: number; offset_y?: number }) =>
    client.post(`/devices/${id}/calibrate`, data),
  getCalibration: (id: number) =>
    client.get<{ pixel_points: number[][]; mech_points: number[][]; offset_x: number; offset_y: number } | null>(`/devices/${id}/calibration`).then(r => r.data),
  updateOffset: (id: number, offset_x: number, offset_y: number) =>
    client.patch(`/devices/${id}/calibration/offset`, { offset_x, offset_y }).then(r => r.data),
  getPosition: (id: number) =>
    client.get<{ x: number; y: number; z: number }>(`/devices/${id}/position`).then(r => r.data),
  moveToPixel: (id: number, px: number, py: number) =>
    client.post<{
      pixel: { x: number; y: number }
      mech: { x: number; y: number }
      calibrated: boolean
      moved: boolean
      move_error: string | null
      message: string
    }>(
      `/devices/${id}/move_to_pixel`, { px, py }
    ).then(r => r.data),
}

export const templatesApi = {
  list: () => client.get('/templates').then(r => r.data),
  get: (id: number) => client.get(`/templates/${id}`).then(r => r.data),
  create: (data: { app_name: string; name: string; yaml_content: string }) =>
    client.post('/templates', data).then(r => r.data),
  update: (id: number, data: { app_name: string; name: string; yaml_content: string }) =>
    client.put(`/templates/${id}`, data).then(r => r.data),
  delete: (id: number) => client.delete(`/templates/${id}`),
}

export const tasksApi = {
  execute: (deviceId: number, action: string, params: Record<string, unknown> = {}) =>
    client.post(`/devices/${deviceId}/execute`, { action, params }),
  runYaml: (deviceId: number, yaml_content: string) =>
    client.post(`/devices/${deviceId}/run_yaml`, { yaml_content }).then(r => r.data),
  batchRun: (device_ids: number[], yaml_content: string) =>
    client.post('/tasks/batch_run', { device_ids, yaml_content }).then(r => r.data),
  natural: (instruction: string, device_id?: number) =>
    client.post('/tasks/natural', { instruction, device_id }),
  get: (id: number) => client.get(`/tasks/${id}`).then(r => r.data),
  stop: (deviceId: number) => client.post(`/devices/${deviceId}/stop`),
}

export const emergencyApi = {
  stopAll: () => client.post('/emergency_stop'),
  resetAll: () => client.post('/emergency_reset'),
}

export const visionApi = {
  inspect: (id: number, method: string, params: Record<string, unknown> = {}) =>
    client.post(`/devices/${id}/vision`, { method, params }, { timeout: 120000 }).then(r => r.data),
  firmwareRestart: (id: number) =>
    client.post(`/devices/${id}/firmware_restart`),
}

export const visionTestApi = {
  health: () => client.get<Record<string, unknown>>('/vision/health').then(r => r.data),
  matchTest: (req: {
    device_id?: number
    image_base64?: string
    template_name?: string
    app_name?: string
    threshold?: number
  }) => client.post<Record<string, unknown>>('/vision/match_test', req, { timeout: 120000 }).then(r => r.data),
  ocrTest: (req: {
    device_id?: number
    image_base64?: string
    keyword?: string
  }) => client.post<Record<string, unknown>>('/vision/ocr_test', req, { timeout: 120000 }).then(r => r.data),
}

export interface TemplateIconInfo {
  app: string
  name: string
  size: number
  path: string
}

export const templateIconsApi = {
  list: () => client.get<{ apps: Record<string, TemplateIconInfo[]> }>('/templates/icons').then(r => r.data),
  get: (app: string, name: string) => `/api/v1/templates/icons/${encodeURIComponent(app)}/${encodeURIComponent(name)}?t=${Date.now()}`,
  upload: (app: string, name: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client.post(`/templates/icons/${encodeURIComponent(app)}/${encodeURIComponent(name)}`, form).then(r => r.data)
  },
  cropFromDevice: (deviceId: number, region: { x: number; y: number; w: number; h: number }, app: string, name: string) =>
    client.post('/templates/icons/crop', { device_id: deviceId, x: region.x, y: region.y, w: region.w, h: region.h, app_name: app, icon_name: name }).then(r => r.data),
  cropFromBase64: (imageBase64: string, region: { x: number; y: number; w: number; h: number }, app: string, name: string) =>
    client.post('/templates/icons/crop_base64', { image_base64: imageBase64, x: region.x, y: region.y, w: region.w, h: region.h, app_name: app, icon_name: name }).then(r => r.data),
  delete: (app: string, name: string) =>
    client.delete(`/templates/icons/${encodeURIComponent(app)}/${encodeURIComponent(name)}`),
  createFolder: (app: string) =>
    client.post(`/templates/icons/folder/${encodeURIComponent(app)}`).then(r => r.data),
}
