import type { ThreadHistory, ThreadMetadata } from '@/entities/thread.ts'
import apiClient from '@/utils/api.ts'

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
    return await apiClient.post<{ response: string, threadId: string }>('/chat/response', { threadId, message })
  },

  async generateAssistantStream (threadId: string, message: string, accessToken: string) {
    console.log('Generating assistant response stream')
    return await apiClient.post('/chat/stream', { threadId, message }, {
      responseType: 'text',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })
  },
}
