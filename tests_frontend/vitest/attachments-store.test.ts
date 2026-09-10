import type { FileResponse } from '@/entities/file.ts'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { hasBlockingAttachments } from '@/entities/file.ts'
import { fileRepo } from '@/repos/file.ts'
import { useAttachmentsStore } from '@/stores/attachments.ts'

function fileResponse (id: string): FileResponse {
  return {
    id,
    name: `${id}.txt`,
    contentType: 'text/plain',
    headValue: null,
    creationDate: null,
    projectId: null,
    indexStatus: 'not_indexed',
    indexError: null,
  }
}

describe('attachments store concurrency', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  test('loading linked files does not strand an in-flight upload', async () => {
    let resolveUpload: ((value: unknown) => void) | undefined
    const uploadResponse = new Promise<unknown>(resolve => {
      resolveUpload = resolve
    })
    vi.spyOn(fileRepo, 'uploadFile').mockImplementation(async () => await uploadResponse as never)
    vi.spyOn(fileRepo, 'listThreadFiles').mockResolvedValue({ data: [] } as never)

    const store = useAttachmentsStore()
    const state = store.stateFor('thread-1')
    const upload = store.queueFiles('thread-1', [new File(['data'], 'a.txt')])
    await Promise.resolve()
    expect(state.pending[0]?.status).toBe('uploading')

    await store.loadLinked('thread-1')
    resolveUpload?.({ data: fileResponse('file-1') })
    await upload

    expect(state.pending[0]?.status).toBe('ready')
    expect(state.pending[0]?.uploaded?.id).toBe('file-1')
  })

  test('an in-flight unlink blocks send and settles after success', async () => {
    let resolveUnlink: ((value: unknown) => void) | undefined
    const unlinkResponse = new Promise<unknown>(resolve => {
      resolveUnlink = resolve
    })
    vi.spyOn(fileRepo, 'unlinkThreadFile').mockImplementation(async () => await unlinkResponse as never)

    const store = useAttachmentsStore()
    const state = store.stateFor('thread-1')
    state.linked = [fileResponse('file-1')]
    const unlink = store.removeLinked('thread-1', 'thread-1', 'file-1')

    expect(state.linked).toEqual([])
    expect(state.unlinking).toEqual(['file-1'])
    expect(hasBlockingAttachments(state)).toBe(true)

    resolveUnlink?.(undefined)
    await unlink
    expect(state.unlinking).toEqual([])
    expect(hasBlockingAttachments(state)).toBe(false)
  })

  test('failed unlink restores the file after a list reload', async () => {
    let rejectUnlink: ((reason: unknown) => void) | undefined
    const unlinkResponse = new Promise<unknown>((_, reject) => {
      rejectUnlink = reject
    })
    vi.spyOn(fileRepo, 'unlinkThreadFile').mockImplementation(async () => await unlinkResponse as never)
    vi.spyOn(fileRepo, 'listThreadFiles').mockResolvedValue({
      data: [fileResponse('file-1')],
    } as never)

    const store = useAttachmentsStore()
    const state = store.stateFor('thread-1')
    state.linked = [fileResponse('file-1')]
    const unlink = store.removeLinked('thread-1', 'thread-1', 'file-1')
    const reload = store.loadLinked('thread-1')
    await reload
    expect(state.linked.map(file => file.id)).toEqual(['file-1'])

    const unlinkError = new Error('detach failed')
    rejectUnlink?.(unlinkError)
    await expect(unlink).rejects.toBe(unlinkError)
    expect(state.linked.map(file => file.id)).toEqual(['file-1'])
    expect(state.unlinking).toEqual([])
  })
})
