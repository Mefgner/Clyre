import type { AxiosAdapter, AxiosRequestConfig } from 'axios'
import { mount, type VueWrapper } from '@vue/test-utils'
import { AxiosError } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import ModalContainer from '@/components/ModalContainer.vue'
import { AuthRepo } from '@/repos/auth.ts'
import router from '@/router'
import { useAuthStore } from '@/stores/auth.ts'
import { useUiStore } from '@/stores/ui.ts'
import apiClient from '@/utils/api.ts'

const originalAdapter = apiClient.defaults.adapter

function response (config: AxiosRequestConfig, data: unknown, status = 200) {
  return {
    data,
    status,
    statusText: status === 200 ? 'OK' : 'Unauthorized',
    headers: {},
    config,
  } as never
}

function unauthorized (config: AxiosRequestConfig): Promise<never> {
  return Promise.reject(new AxiosError(
    'Unauthorized',
    'ERR_BAD_REQUEST',
    config as never,
    undefined,
    response(config, { detail: 'Unauthorized' }, 401),
  ))
}

function setAdapter (handler: (config: AxiosRequestConfig) => Promise<unknown>) {
  apiClient.defaults.adapter = (async config => await handler(config)) as AxiosAdapter
}

describe('authentication flow', () => {
  let mounted: VueWrapper | undefined
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    vi.restoreAllMocks()
  })

  afterEach(() => {
    mounted?.unmount()
    mounted = undefined
    apiClient.defaults.adapter = originalAdapter
  })

  test('does not retry a failed refresh request and clears the token', async () => {
    const calls: string[] = []
    setAdapter(async config => {
      calls.push(config.url ?? '')
      return await unauthorized(config)
    })

    const authStore = useAuthStore()
    authStore.accessToken = 'stale-token'

    await expect(authStore.refreshAccessToken()).rejects.toBeInstanceOf(AxiosError)
    expect(calls).toEqual(['/auth/refresh'])
    expect(authStore.accessToken).toBeNull()

    await expect(authStore.refreshAccessToken()).rejects.toBeInstanceOf(AxiosError)
    expect(calls).toHaveLength(2)
  })

  test('opens the login modal for the initial unauthenticated state', () => {
    mounted = mount(ModalContainer, {
      global: {
        plugins: [pinia],
        stubs: {
          'are-you-sure-modal': true,
          'login-modal': true,
          'register-modal': true,
        },
      },
    })

    expect(useUiStore().isLoginOpen).toBe(true)
    expect(useUiStore().isRegisterOpen).toBe(false)
  })

  test('retries a protected request after one successful refresh', async () => {
    const calls: Array<{
      url: string
      authorization: string
    }> = []
    setAdapter(async config => {
      const authorization = String(config.headers?.Authorization ?? '')
      calls.push({ url: config.url ?? '', authorization })

      if (config.url === '/protected' && authorization === 'Bearer stale-token') {
        return await unauthorized(config)
      }
      if (config.url === '/auth/refresh') {
        return response(config, { token: 'fresh-token' })
      }
      return response(config, { ok: true })
    })

    const authStore = useAuthStore()
    authStore.accessToken = 'stale-token'

    const result = await apiClient.get('/protected')

    expect(result.data).toEqual({ ok: true })
    expect(calls.map(call => call.url)).toEqual([
      '/protected',
      '/auth/refresh',
      '/protected',
    ])
    expect(calls.filter(call => call.url === '/auth/refresh')).toHaveLength(1)
    expect(calls.at(-1)?.authorization).toBe('Bearer fresh-token')
  })

  test('failed refresh opens login and does not call backend logout', async () => {
    const calls: string[] = []
    setAdapter(async config => {
      calls.push(config.url ?? '')
      return await unauthorized(config)
    })

    const logout = vi.spyOn(AuthRepo, 'logout')
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined as never)
    const authStore = useAuthStore()
    authStore.accessToken = 'stale-token'

    await expect(apiClient.get('/protected')).rejects.toBeInstanceOf(AxiosError)

    expect(calls).toEqual(['/protected', '/auth/refresh'])
    expect(logout).not.toHaveBeenCalled()
    expect(authStore.accessToken).toBeNull()
    expect(useUiStore().isLoginOpen).toBe(true)
    expect(push).toHaveBeenCalledWith('/')
  })
})
