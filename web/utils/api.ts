import axios, { type AxiosError, type AxiosInstance } from 'axios'

import router from '@/router'
import { useAuthStore } from '@/stores/auth.ts'
import { useUiStore } from '@/stores/ui.ts'

type RetryableRequestConfig = NonNullable<AxiosError['config']> & {
  _retry?: boolean
}

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

apiClient.interceptors.request.use(
  config => {
    const authStore = useAuthStore()
    if (authStore.accessToken) {
      config.headers.Authorization = `Bearer ${authStore.accessToken}`
    }
    return config
  },
  error => Promise.reject(error),
)

apiClient.interceptors.response.use(
  response => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined
    const isRefreshRequest = originalRequest?.url?.endsWith('/auth/refresh')
    if (
      error.response?.status === 401
      && originalRequest
      && !isRefreshRequest
      && !originalRequest._retry
    ) {
      originalRequest._retry = true

      const authStore = useAuthStore()
      try {
        authStore.accessToken = null
        await authStore.refreshAccessToken()
        // apiClient() runs request interceptors again, which attaches the new token.
        return apiClient(originalRequest)
      } catch {
        authStore.accessToken = null
        useUiStore().openLogin()
        await router.push('/')
      }
    }
    throw error
  },
)

export default apiClient
