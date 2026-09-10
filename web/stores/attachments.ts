import type {

  PendingAttachment,
  ThreadAttachmentState,
} from '@/entities/file.ts'
import { defineStore } from 'pinia'
import { reactive } from 'vue'
import {
  attachmentKey,
  describeUploadError,
  httpDetail,
  httpStatus,
  NEW_THREAD_DRAFT_KEY,
} from '@/entities/file.ts'
import { fileRepo } from '@/repos/file.ts'
import { logger } from '@/utils/logger.ts'

function freshState (): ThreadAttachmentState {
  return {
    linked: [],
    pending: [],
    unlinking: [],
    loading: false,
    loadError: null,
    revision: 0,
    listRevision: 0,
  }
}

let localIdCounter = 0
function nextLocalId (): string {
  localIdCounter += 1
  return `pending-${Date.now()}-${localIdCounter}`
}

export const useAttachmentsStore = defineStore('attachments', () => {
  // Per-thread state including the 'new' draft. Draft survives in-memory
  // navigation; no reload persistence is required for M3.
  const byKey = reactive<Record<string, ThreadAttachmentState>>({})

  const stateFor = (key: string): ThreadAttachmentState => {
    let state = byKey[key]
    if (!state) {
      state = freshState()
      byKey[key] = state
    }
    return state
  }

  const bumpRevision = (key: string): number => {
    const state = stateFor(key)
    state.revision += 1
    return state.revision
  }

  /** Queue files for a composer key and upload them strictly sequentially. */
  const queueFiles = async (key: string, files: File[]) => {
    const state = stateFor(key)
    const revision = state.revision
    for (const file of files) {
      const item: PendingAttachment = {
        localId: nextLocalId(),
        fileName: file.name,
        status: 'uploading',
        uploaded: null,
        error: null,
        source: file,
      }
      // Re-read through the map: a thread switch must not move chips or
      // errors into another conversation.
      const live = byKey[key]
      if (!live || live.revision !== revision) {
        return
      }
      live.pending.push(item)
      try {
        const response = await fileRepo.uploadFile(file)
        const current = byKey[key]
        if (!current || current.revision !== revision) {
          return
        }
        const target = current.pending.find(entry => entry.localId === item.localId)
        if (!target) {
          continue
        }
        target.status = 'ready'
        target.uploaded = response.data
      } catch (error) {
        const current = byKey[key]
        if (!current || current.revision !== revision) {
          return
        }
        const target = current.pending.find(entry => entry.localId === item.localId)
        if (!target) {
          continue
        }
        target.status = 'error'
        const status = httpStatus(error)
        target.error = describeUploadError(status, httpDetail(error))
        logger.warn('attachment_upload_failed', { key, fileName: file.name, status })
      }
    }
  }

  const retryPending = async (key: string, localId: string) => {
    const state = stateFor(key)
    const item = state.pending.find(entry => entry.localId === localId)
    if (!item || !item.source) {
      return
    }
    item.status = 'uploading'
    item.error = null
    try {
      const response = await fileRepo.uploadFile(item.source)
      if (byKey[key]?.revision !== state.revision) {
        return
      }
      item.status = 'ready'
      item.uploaded = response.data
    } catch (error) {
      if (byKey[key]?.revision !== state.revision) {
        return
      }
      item.status = 'error'
      item.error = describeUploadError(httpStatus(error), httpDetail(error))
    }
  }

  /** Removing a pending chip only deselects it; the uploaded blob is kept. */
  const removePending = (key: string, localId: string) => {
    const state = stateFor(key)
    state.pending = state.pending.filter(entry => entry.localId !== localId)
  }

  /** Removing a linked chip unlinks server-side; the blob itself is kept. */
  const removeLinked = async (key: string, threadId: string, fileId: string) => {
    const state = stateFor(key)
    const revision = state.revision
    const removed = state.linked.find(file => file.id === fileId)
    const removedIndex = state.linked.findIndex(file => file.id === fileId)
    state.linked = state.linked.filter(file => file.id !== fileId)
    // The chip is gone locally, but the server still counts the file until the
    // DELETE lands: keep it in `unlinking` so Send stays blocked meanwhile.
    state.unlinking = [...state.unlinking, fileId]
    const settleUnlink = () => {
      const current = byKey[key]
      if (current && current.revision === revision) {
        current.unlinking = current.unlinking.filter(id => id !== fileId)
      }
    }
    const removeLinkedChip = () => {
      const current = byKey[key]
      if (current && current.revision === revision) {
        current.linked = current.linked.filter(file => file.id !== fileId)
      }
    }
    try {
      await fileRepo.unlinkThreadFile(fileId, threadId)
      settleUnlink()
      removeLinkedChip()
    } catch (error) {
      settleUnlink()
      const current = byKey[key]
      // Restore only this failed file. A list reload may have changed the
      // other chips while the DELETE was in flight, so restoring a previous
      // snapshot would overwrite newer server state.
      if (
        current
        && current.revision === revision
        && removed
        && !current.linked.some(file => file.id === fileId)
      ) {
        const insertAt = Math.min(Math.max(removedIndex, 0), current.linked.length)
        current.linked = [
          ...current.linked.slice(0, insertAt),
          removed,
          ...current.linked.slice(insertAt),
        ]
      }
      logger.error('attachment_unlink_failed', { threadId, fileId, error: String(error) })
      throw error
    }
  }

  const loadLinked = async (threadId: string) => {
    const key = attachmentKey(threadId)
    const state = stateFor(key)
    const revision = state.revision
    // Only list results are invalidated here: bumping `revision` would also
    // drop in-flight uploads for this key (they never finish -> chip stuck).
    state.listRevision += 1
    const listRevision = state.listRevision
    state.loading = true
    state.loadError = null
    const liveState = (): ThreadAttachmentState | null => {
      const current = byKey[key]
      if (!current || current.revision !== revision || current.listRevision !== listRevision) {
        return null
      }
      return current
    }
    try {
      const response = await fileRepo.listThreadFiles(threadId)
      const current = liveState()
      if (!current) {
        return
      }

      /* eslint-disable-next-line unicorn/no-array-sort -- ES2022 has no toSorted; copy sorted, payload untouched. */
      current.linked = [...response.data].sort((a, b) =>
        a.name === b.name ? (a.id < b.id ? -1 : 1) : (a.name < b.name ? -1 : 1),
      )
    } catch (error) {
      const current = liveState()
      if (!current) {
        return
      }
      current.loadError = httpDetail(error) || 'Could not load attachments.'
    } finally {
      const current = liveState()
      if (current) {
        current.loading = false
      }
    }
  }

  /** After a draft creates a thread, carry its chips to the new thread key. */
  const adoptDraft = (newThreadId: string) => {
    const draft = byKey[NEW_THREAD_DRAFT_KEY]
    if (!draft) {
      return
    }
    const key = attachmentKey(newThreadId)
    const target = stateFor(key)
    target.pending = draft.pending
    target.linked = draft.linked
    draft.pending = []
    draft.linked = []
    bumpRevision(NEW_THREAD_DRAFT_KEY)
  }

  const clearPending = (key: string) => {
    stateFor(key).pending = []
  }

  const resetKey = (key: string) => {
    // Bumping the revision drops every in-flight upload/list result for the
    // key without touching other conversations.
    bumpRevision(key)
    byKey[key] = freshState()
  }

  return {
    byKey,
    stateFor,
    queueFiles,
    retryPending,
    removePending,
    removeLinked,
    loadLinked,
    adoptDraft,
    clearPending,
    resetKey,
    bumpRevision,
  }
})

export { type FileResponse } from '@/entities/file.ts'
