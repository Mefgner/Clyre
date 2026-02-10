import axios, { type AxiosError, type AxiosInstance } from 'axios'

import router from '@/router'

import { useAuthStore } from '@/stores/auth.ts'

console.log(import.meta.env.VITE_API_URL)

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
    const originalRequest = error.config
    // @ts-ignore
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      // @ts-ignore
      originalRequest._retry = true

      const authStore = useAuthStore()

      try {
        authStore.accessToken = null
        await authStore.refreshAccessToken()

        if (originalRequest.headers?.Authorization) {
          originalRequest.headers.Authorization = `Bearer ${authStore.accessToken}`
        }
        return apiClient(originalRequest)
      } catch {
        await authStore.logout()
        await router.push('/')
        throw error
      }
    }
    throw error
  },
)

export default apiClient
