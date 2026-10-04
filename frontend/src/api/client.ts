import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,  // vision diagnoses can take ~5s
  headers: { 'Content-Type': 'application/json' },
})

// --- Request: attach Bearer token ---
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// --- Response: handle 401 ---
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // Token expired or invalid — clear and send to login
      localStorage.removeItem('access_token')
      localStorage.removeItem('current_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)