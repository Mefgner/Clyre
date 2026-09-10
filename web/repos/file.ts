import type { FileResponse } from '@/entities/file.ts'
import apiClient from '@/utils/api.ts'

export const fileRepo = {
  async uploadFile (file: File) {
    const form = new FormData()
    // Multipart field name must be `upload`; never set the boundary manually.
    form.append('upload', file, file.name)
    return await apiClient.post<FileResponse>('/files/upload', form, {
      // The shared client defaults to JSON; let the browser add multipart boundary.
      headers: { 'Content-Type': undefined },
    })
  },

  async listThreadFiles (threadId: string) {
    return await apiClient.get<FileResponse[]>(`/thread/${encodeURIComponent(threadId)}/files`)
  },

  async unlinkThreadFile (fileId: string, threadId: string) {
    return await apiClient.delete(
      `/files/${encodeURIComponent(fileId)}/link/thread/${encodeURIComponent(threadId)}`,
    )
  },
}
