import { type AxiosAdapter, AxiosHeaders } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { fileRepo } from '@/repos/file.ts'
import apiClient from '@/utils/api.ts'

const originalAdapter = apiClient.defaults.adapter

describe('file repository uploads', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter
  })

  test('sends the upload as browser-managed multipart form data', async () => {
    let receivedData: unknown
    let receivedHeaders: AxiosHeaders | undefined
    apiClient.defaults.adapter = (async config => {
      receivedData = config.data
      receivedHeaders = AxiosHeaders.from(config.headers)
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }) as AxiosAdapter

    const file = new File(['The verification code is CLYRE-M3-7QK2.'], 'text.txt', {
      type: 'text/plain',
    })

    await fileRepo.uploadFile(file)

    expect(receivedData).toBeInstanceOf(FormData)
    expect(receivedHeaders?.getContentType()).not.toBe('application/json')
    const form = receivedData as FormData
    const uploaded = form.get('upload') as File
    expect(uploaded.name).toBe(file.name)
    expect(uploaded.type).toBe(file.type)
  })
})
