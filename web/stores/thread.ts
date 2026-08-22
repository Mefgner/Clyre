// PLAN-NOTE(fe-chat-cache): groundwork exists for a chat-history caching layer,
// currently dormant. Plan (tracked as §6.4 "Chat history cache" in PLAN.md):
//   - New dedicated repo (`repos/threadCache.ts` or extend this store) holding a
//     `ThreadHistoryCache` map (see `entities/thread.ts`) of fully loaded threads.
//   - `setCurrentThread` / `updateCurrentThread` serve from cache when present;
//     fetch + fill on miss.
//   - Invalidation points: after each completed stream (`done` event), on
//     `deleteCurrentThread`, and on `getThreadsMeta` detecting external changes.
//   - Keep memory bounded (LRU cap) once pagination (§6.1) lands.
// The orphaned `ThreadHistoryCache` interface in entities is part of this plan —
// do not delete it while the plan is open.
import type {
  ThreadHistory,
  ThreadMessage,
  ThreadMetadata,
  ThreadStreamingPayload,
} from '@/entities/thread.ts'

import { AxiosError } from 'axios'
import { defineStore } from 'pinia'

import { reactive, ref } from 'vue'
import { type ChatStreamConnection, threadRepo } from '@/repos/thread.ts'
import { logger } from '@/utils/logger.ts'
import { readNDJSONStream } from '@/utils/stream.ts'

const GENERATION_POLL_INTERVAL_MS = 1000

export const useThreadStore = defineStore('thread', () => {
  const threadsMeta = ref<ThreadMetadata[]>([])
  const isGenerating = ref(false)
  // Thread id of the run whose NDJSON stream this client is consuming, or
  // null. The resume-poller must not touch that thread (two writers on
  // currentThread duplicate/roll back visible text), and the stop button
  // must target this id — not whatever thread is currently displayed.
  const activeStreamThreadId = ref<string | null>(null)

  let streamAbort: (() => void) | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const newThread = () => ({
    id: '',
    messages: reactive([]),
    creationDate: Date.now().toString(),
    title: '',
    updateTime: Date.now().toString(),
  })

  const currentThread = ref<ThreadHistory>(newThread())

  const getThreadsMeta = async () => {
    try {
      const response = await threadRepo.getAllThreadsMeta()
      threadsMeta.value = response.data.threads
    } catch (error) {
      if (error instanceof AxiosError) {
        if (!error?.status) {
          throw error
        }
        if (error?.status !== 404) {
          throw error
        }
      }
    }
  }

  const clearThreadsMeta = () => {
    threadsMeta.value = []
  }

  // TODO(m2-chat-resume): replace polling with offset-based reconnect via
  // POST /api/chat/stream once the backend exposes a subscribe-without-send
  // endpoint; polling only survives page refreshes mid-generation.
  const stopGenerationPolling = (reason?: string) => {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
      logger.debug('generation_poll_stopped', { threadId: currentThread.value.id, reason })
    }
    isGenerating.value = false
  }

  const startGenerationPolling = () => {
    if (activeStreamThreadId.value === currentThread.value.id) {
      // A live NDJSON stream owns this thread's updates; polling alongside it
      // would replace the streamed partials wholesale every second.
      return
    }
    if (pollTimer !== null) {
      return
    }
    isGenerating.value = true
    logger.info('generation_poll_started', { threadId: currentThread.value.id })

    pollTimer = setInterval(async () => {
      const threadId = currentThread.value.id
      if (!threadId || currentThread.value.isGenerating !== true) {
        stopGenerationPolling('flag-cleared')
        return
      }

      try {
        const response = await threadRepo.getThreadHistory(threadId)
        currentThread.value = response.data
        if (response.data.isGenerating !== true) {
          stopGenerationPolling('finished')
          await getThreadsMeta()
        }
      } catch (error) {
        logger.error('generation_poll_failed', { threadId, error: String(error) })
        stopGenerationPolling('error')
      }
    }, GENERATION_POLL_INTERVAL_MS)
  }

  const setCurrentThread = async (threadMeta: ThreadMetadata) => {
    const thread = (await threadRepo.getThreadHistory(threadMeta.id)).data
    currentThread.value = thread ?? newThread()

    if (thread?.isGenerating) {
      startGenerationPolling()
    }
  }

  const updateCurrentThread = async () => {
    const thread = (await threadRepo.getThreadHistory(currentThread.value.id)).data
    currentThread.value = thread ?? newThread()
  }

  const clearCurrent = () => {
    currentThread.value = newThread()
  }

  const deleteCurrentThread = async () => {
    const result = await threadRepo.deleteThread(currentThread.value.id)
    if (result.status === 200) {
      clearCurrent()
      await getThreadsMeta()
    }
  }

  const pushUserMessage = (message: string) => {
    const newMessage: ThreadMessage = {
      role: 'user',
      content: message,
    }
    currentThread.value.messages.push(newMessage)
  }

  const pushAssistantMessage = (message: string, thinking?: string) => {
    const newMessage: ThreadMessage = {
      role: 'assistant',
      content: message,
      thinking: thinking ?? null,
    }
    currentThread.value.messages.push(newMessage)
  }

  const appendToAssistantMessage = (message: string, kind: 'content' | 'thinking') => {
    const messages = currentThread.value.messages
    let lastMsg = messages.at(-1)

    if (!lastMsg || lastMsg.role !== 'assistant') {
      pushAssistantMessage('')
      lastMsg = messages.at(-1)!
    }

    if (kind === 'content') {
      lastMsg.content = (lastMsg.content ?? '') + message
    } else {
      lastMsg.thinking = (lastMsg.thinking ?? '') + message
    }
  }

  const getAssistantMessagePipeline = async function* (prompt: string, enableThinking = false) {
    if (isGenerating.value) {
      return
    }
    isGenerating.value = true

    const requestThreadId = currentThread.value.id || null
    activeStreamThreadId.value = requestThreadId
    const startedAt = performance.now()
    let firstTokenAt: number | null = null
    let contentChunks = 0
    let thinkingChunks = 0

    const connection: ChatStreamConnection = threadRepo.openChatStream({
      threadId: requestThreadId,
      message: prompt,
      enableThinking,
      offset: 0,
    })
    streamAbort = connection.abort

    logger.info('stream_opened', {
      threadId: requestThreadId,
      offset: 0,
      messageLength: prompt.length,
      enableThinking,
    })

    let streamThreadId: string | null = requestThreadId
    let consumedEvents = 0

    const isActiveStream = () => !streamThreadId || currentThread.value.id === streamThreadId

    try {
      const response = await connection.response
      if (!response.ok || !response.body) {
        logger.error('stream_http_error', { status: response.status, threadId: requestThreadId })
        throw new Error(`Chat stream request failed with status ${response.status}`)
      }

      for await (const payload of readNDJSONStream<ThreadStreamingPayload>(response.body)) {
        consumedEvents += 1

        if (payload.threadId && streamThreadId && payload.threadId !== streamThreadId) {
          continue
        }
        if (payload.threadId) {
          streamThreadId = payload.threadId
          activeStreamThreadId.value = payload.threadId
          if (!currentThread.value.id || currentThread.value.id === payload.threadId) {
            currentThread.value.id = payload.threadId
          }
        }

        switch (payload.event) {
          case 'user_message_insert':
          case 'assistant_message_insert': {
            break
          }

          case 'new_thinking_chunk': {
            if (firstTokenAt === null) {
              firstTokenAt = performance.now()
              logger.info('first_thinking_chunk', { threadId: streamThreadId, ms: Math.round(firstTokenAt - startedAt) })
            }
            thinkingChunks += 1
            if (payload.chunk && isActiveStream()) {
              appendToAssistantMessage(payload.chunk, 'thinking')
            }
            break
          }

          case 'new_chunk': {
            if (firstTokenAt === null) {
              firstTokenAt = performance.now()
              logger.info('first_content_chunk', { threadId: streamThreadId, ms: Math.round(firstTokenAt - startedAt) })
            }
            contentChunks += 1
            if (payload.chunk && isActiveStream()) {
              appendToAssistantMessage(payload.chunk, 'content')
            }
            break
          }

          case 'done': {
            if (isActiveStream()) {
              currentThread.value.updateTime = Date.now().toString()
              try {
                await getThreadsMeta()
              } catch (error) {
                logger.warn('threads_meta_refresh_failed', { threadId: streamThreadId, error: String(error) })
              }
            }
            break
          }

          default: {
            logger.warn('unknown_stream_event', { event: payload.event })
          }
        }

        yield payload
      }

      logger.info('stream_completed', {
        threadId: streamThreadId,
        durationMs: Math.round(performance.now() - startedAt),
        firstTokenMs: firstTokenAt === null ? null : Math.round(firstTokenAt - startedAt),
        contentChunks,
        thinkingChunks,
        consumedEvents,
      })
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError'
      const log = aborted ? logger.warn : logger.error
      log(aborted ? 'stream_aborted' : 'stream_failed', {
        threadId: streamThreadId,
        consumedEvents,
        durationMs: Math.round(performance.now() - startedAt),
        contentChunks,
        thinkingChunks,
        error: String(error),
      })
      throw error
    } finally {
      streamAbort = null
      activeStreamThreadId.value = null
      isGenerating.value = false
    }
  }

  const stopGeneration = async () => {
    if (!isGenerating.value) {
      return
    }

    // Stop the run this client is actually streaming — after a mid-stream
    // thread switch currentThread.id points elsewhere.
    const threadId = activeStreamThreadId.value ?? currentThread.value.id
    if (!threadId) {
      logger.warn('stop_without_thread_id_abort_only')
      streamAbort?.()
      return
    }

    logger.info('stop_requested', { threadId })
    try {
      await threadRepo.stopGeneration(threadId)
    } catch (error) {
      logger.error('stop_failed', { threadId, error: String(error) })
      streamAbort?.()
    }
  }

  return {
    threadsMeta,
    isGenerating,
    activeStreamThreadId,
    getThreadsMeta,
    clearThreadsMeta,
    currentThread,
    setCurrentThread,
    updateCurrentThread,
    clearCurrent,
    deleteCurrentThread,
    pushUserMessage,
    pushAssistantMessage,
    getAssistantMessagePipeline,
    stopGeneration,
  }
})
