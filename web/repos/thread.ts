import type { ThreadHistory, ThreadMetadata } from '@/entities/thread.ts'
import { useAuthStore } from '@/stores/auth.ts'
import apiClient from '@/utils/api.ts'

export interface ChatStreamRequest {
  threadId: string | null
  message: string
  enableThinking: boolean
  fileIds?: string[]
}

export interface ChatStreamConnection {
  abort: () => void
  response: Promise<Response>
}

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

function openAuthenticatedStream (
  buildRequest: (token: string, signal: AbortSignal) => RequestInfo | URL,
): ChatStreamConnection {
  const controller = new AbortController()
  const authStore = useAuthStore()
  const fetchWithToken = (token: string) => fetch(buildRequest(token, controller.signal))

  const response = (async () => {
    const first = await fetchWithToken(authStore.accessToken ?? '')
    if (first.status !== 401) {
      return first
    }
    try {
      await authStore.refreshAccessToken()
    } catch {
      return first
    }
    return await fetchWithToken(authStore.accessToken ?? '')
  })()

  return {
    response,
    abort: () => controller.abort(),
  }
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
    return openAuthenticatedStream((token, signal) => new Request(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        threadId: request.threadId || null,
        message: request.message,
        enableThinking: request.enableThinking,
        fileIds: request.fileIds ?? [],
      }),
      signal,
    }))
  },

  attachChatStream (threadId: string, offset: number): ChatStreamConnection {
    const url = `${API_BASE_URL}/chat/stream/${encodeURIComponent(threadId)}?offset=${offset}`
    return openAuthenticatedStream((token, signal) => new Request(url, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
      signal,
    }))
  },

  async stopGeneration (threadId: string) {
    return await apiClient.post<{ result: 'stopping' }>('/chat/stop', { threadId })
  },
}
