import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
})

// Auto-attach token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Auto-fetch token if none (force refresh on every app start)
export async function ensureToken() {
  const resp = await axios.post('/api/v1/token')
  localStorage.setItem('token', resp.data.access_token)
}

// Auto-refresh token on 401
client.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true
      try {
        const resp = await axios.post('/api/v1/token')
        const token = resp.data.access_token
        localStorage.setItem('token', token)
        error.config.headers.Authorization = `Bearer ${token}`
        return client(error.config)
      } catch {
        // token refresh failed, continue with original error
      }
    }
    return Promise.reject(error)
  }
)

export default client
