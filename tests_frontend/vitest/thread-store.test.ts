import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { threadRepo } from '@/repos/thread.ts'
import { ChatGenerationError, useThreadStore } from '@/stores/thread.ts'

describe('thread store stream starts', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  test('does not reconnect a rejected start on an existing thread', async () => {
    const open = vi.spyOn(threadRepo, 'openChatStream').mockReturnValue({
      abort: vi.fn(),
      response: Promise.resolve(Response.json(
        { detail: 'Model budget check is temporarily unavailable' },
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      )),
    })
    const attach = vi.spyOn(threadRepo, 'attachChatStream')
    vi.spyOn(threadRepo, 'getThreadHistory').mockResolvedValue({
      data: {
        id: 'thread-1', messages: [], creationDate: '', title: 'Thread', updateTime: '',
      },
    } as never)

    const store = useThreadStore()
    store.currentThread.id = 'thread-1'
    const consume = async () => {
      for await (const _payload of store.getAssistantMessagePipeline('new question')) {
        // The rejected POST has no stream payload.
      }
    }

    await expect(consume()).rejects.toBeInstanceOf(ChatGenerationError)
    expect(open).toHaveBeenCalledOnce()
    expect(attach).not.toHaveBeenCalled()
  })
})
