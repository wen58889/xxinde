type WSCallback = (event: string, data: Record<string, unknown>) => void

class WSClient {
  private ws: WebSocket | null = null
  private callbacks: WSCallback[] = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/api/v1/ws/status`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('WebSocket connected')
      // Keepalive ping
      this.pingInterval = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send('ping')
        }
      }, 30000)
    }

    this.ws.onmessage = (evt) => {
      if (evt.data === 'pong') return
      try {
        const msg = JSON.parse(evt.data)
        this.callbacks.forEach(cb => cb(msg.event, msg.data))
      } catch { /* ignore */ }
    }

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...')
      if (this.pingInterval) clearInterval(this.pingInterval)
      this.reconnectTimer = setTimeout(() => this.connect(), 3000)
    }
  }

  private pingInterval: ReturnType<typeof setInterval> | null = null

  subscribe(cb: WSCallback) {
    this.callbacks.push(cb)
    return () => {
      this.callbacks = this.callbacks.filter(c => c !== cb)
    }
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.pingInterval) clearInterval(this.pingInterval)
    this.ws?.close()
  }
}

export const wsClient = new WSClient()
