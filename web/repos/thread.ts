import type { ThreadHistory, ThreadMetadata } from '@/entities/thread.ts'
import { useAuthStore } from '@/stores/auth.ts'
import apiClient from '@/utils/api.ts'

export interface ChatStreamRequest {
  threadId: string | null
  message: string
  enableThinking: boolean
  offset: number
}

export interface ChatStreamConnection {
  abort: () => void
  response: Promise<Response>
}

export const threadRepo = {
  async getAllThreadsMeta () {
    return await apiClient.get<{ threads: ThreadMetadata[] }>('/thread/all')
  },

  async getThreadHistory (chatId: string) {
    return await apiClient.get<ThreadHistory>(`/thread/${chatId}`)
  },

  async deleteThread (chatId: string) {
    return await apiClient.delete<{ result: 'ok' }>(`/thread/${chatId}`)
  },

  openChatStream (request: ChatStreamRequest): ChatStreamConnection {
    const controller = new AbortController()
    const authStore = useAuthStore()
    const url = `${import.meta.env.VITE_API_URL ?? '/api'}/chat/stream?offset=${request.offset}`

    const doFetch = (token: string) => fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        threadId: request.threadId || null,
        message: request.message,
        enableThinking: request.enableThinking,
      }),
      signal: controller.signal,
    })

    // Raw fetch bypasses the axios 401→refresh interceptor; emulate it here
    // with one refresh-and-retry so an expired token doesn't fail the send.
    const response = (async () => {
      const first = await doFetch(authStore.accessToken ?? '')
      if (first.status !== 401) {
        return first
      }
      try {
        await authStore.refreshAccessToken()
      } catch {
        return first // refresh failed: surface the original 401
      }
      return await doFetch(authStore.accessToken ?? '')
    })()

    return {
      response,
      abort: () => controller.abort(),
    }
  },

  async stopGeneration (threadId: string) {
    return await apiClient.post<{ result: 'stopping' }>('/chat/stop', { threadId })
  },
}
