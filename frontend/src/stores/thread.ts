import type {
  ThreadHistory,
  ThreadMessage,
  ThreadMetadata,
  ThreadStreamingPayload,
} from '@/entities/thread.ts'

import { AxiosError } from 'axios'
import { defineStore } from 'pinia'

import { reactive, ref } from 'vue'
import { threadRepo } from '@/repos/thread.ts'
import { readNDJSONStream } from '@/utils/stream.ts'

export const useThreadStore = defineStore('thread', () => {
  const threadsMeta = ref<ThreadMetadata[]>([])
  const isGenerating = ref(false)

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

  const setCurrentThread = async (threadMeta: ThreadMetadata) => {
    const thread = (await threadRepo.getThreadHistory(threadMeta.id)).data

    if (isGenerating.value) {
      const messages = currentThread.value.messages
      currentThread.value = { ...currentThread.value, ...thread, messages }
    } else {
      currentThread.value = thread ?? newThread()
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

  const pushAssistantMessage = (message: string) => {
    const newMessage: ThreadMessage = {
      role: 'assistant',
      content: message,
    }
    currentThread.value.messages.push(newMessage)
  }

  const appendToAssistantMessage = (message: string) => {
    const messages = currentThread.value.messages
    const lastMsg = messages.at(-1)

    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.content += message
    } else {
      pushAssistantMessage(message)
    }
  }

  // fallback function, don't use it
  const generateAssistantMessage = async (prompt: string, _: string) => {
    const response = await threadRepo.generateAssistantMessage(currentThread.value.id, prompt)
    currentThread.value = { ...currentThread.value, id: response.data.threadId, updateTime: Date.now().toString() }
    pushAssistantMessage(response.data.response)
  }

  const getAssistantMessagePipeline = async function* (prompt: string, _: string, accessToken: string, signal: AbortSignal) {
    const response = await threadRepo.generateAssistantStream(currentThread.value.id, prompt, accessToken, signal)

    isGenerating.value = true
    try {
      for await (const payload of readNDJSONStream<ThreadStreamingPayload>(response)) {
        switch (payload.event) {
          case 'user_message_insert':
          case 'assistant_message_insert': {
            if (payload.threadId) {
              currentThread.value.id = payload.threadId
            }
            break
          }

          case 'new_chunk': {
            if (payload.chunk) {
              appendToAssistantMessage(payload.chunk)
            }
            break
          }

          case 'done': {
            currentThread.value.updateTime = Date.now().toString()
            await getThreadsMeta()
            break
          }

          default: {
            console.warn(`Unknown event: ${payload.event}`)
          }
        }

        yield payload
      }
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== 'AbortError') {
        console.error(error)
      }
    } finally {
      isGenerating.value = false
    }
  }

  return {
    threadsMeta,
    isGenerating,
    getThreadsMeta,
    clearThreadsMeta,
    currentThread,
    setCurrentThread,
    updateCurrentThread,
    clearCurrent,
    deleteCurrentThread,
    pushUserMessage,
    pushAssistantMessage,
    generateAssistantMessage,
    getAssistantMessagePipeline,
  }
})
