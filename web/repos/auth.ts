import type { AuthCredentials, AuthResponse, RegisterCredentials } from '@/entities/auth.ts'

import apiClient from '@/utils/api.ts'

export const AuthRepo = {
  async login (credentials: AuthCredentials) {
    return apiClient.post<AuthResponse>('/auth/login', credentials)
  },

  async register (credentials: RegisterCredentials) {
    return apiClient.post<AuthResponse>('/auth/register', credentials)
  },

  async logout () {
    return apiClient.post('/auth/logout')
  },

  async refreshToken () {
    return apiClient.post<AuthResponse>('/auth/refresh')
  },
}
