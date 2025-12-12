import type { User } from '@/entities/user.ts'
import apiClient from '@/utils/api.ts'

export const userRepo = {
  async getUser () {
    return apiClient.get<User>('/user/me')
  },
}
