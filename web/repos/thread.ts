import type { ThreadHistory, ThreadMetadata } from '@/entities/thread.ts'
import apiClient from '@/utils/api.ts'

interface ChatResponse {
  response: string
  threadId: string
}

export const threadRepo = {
  async getAllThreadsMeta () {
    // console.log('Fetching all threads metadata')
    return await apiClient.get<{ threads: ThreadMetadata[] }>('/thread/all')
  },

  async getThreadHistory (chatId: string) {
    // console.log('Fetching thread history')
    return await apiClient.get<ThreadHistory>(`/thread/${chatId}`)
  },

  async deleteThread (chatId: string) {
    return await apiClient.delete<{ result: 'ok' }>(`/thread/${chatId}`)
  },

  async generateAssistantMessage (threadId: string, message: string) {
    // console.log('Generating assistant message')
    return await apiClient.post<ChatResponse>('/chat/response', { threadId, message })
  },

  async generateAssistantStream (threadId: string, message: string, accessToken: string, signal: AbortSignal) {
    console.log('Generating assistant response stream')
    try {
      return await fetch(`${import.meta.env.VITE_API_URL}/chat/stream`, {
        method: 'POST',
        body: JSON.stringify({ threadId, message }),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        signal,
      })
    } catch (error) {
      console.error(error)
    }
  },
}
