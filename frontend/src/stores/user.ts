import type { User } from '@/entities/user.ts'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { userRepo } from '@/repos/user.ts'

export const useUserStore = defineStore('user', () => {
  const currentUser = ref<User | null>(null)

  // Gets user data from the API using a stored access token
  const getCurrentUser = async () => {
    const response = await userRepo.getUser()
    currentUser.value = response.data
  }

  return { currentUser, getUser: getCurrentUser }
})
