import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PromptBar from '@/components/chat/PromptBar.vue'
import { fileRepo } from '@/repos/file.ts'
import { useAttachmentsStore } from '@/stores/attachments.ts'

const vuetify = createVuetify({ components, directives })

function mountBar (props: Record<string, unknown> = {}) {
  setActivePinia(createPinia())
  return mount(PromptBar, {
    props: { isGenerating: false, threadKey: 'new', starting: false, ...props },
    global: { plugins: [vuetify] },
  })
}

function sendButton (wrapper: ReturnType<typeof mount>) {
  const buttons = wrapper.findAllComponents({ name: 'VBtn' })
  return buttons.at(-1)!
}

describe('PromptBar attachments (M3)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  test('renders linked and pending chips with file names', async () => {
    const wrapper = mountBar()
    const store = useAttachmentsStore()
    const state = store.stateFor('new')
    state.linked = [
      {
        id: 'f1', name: 'linked.txt', contentType: 'text/plain', headValue: null,
        creationDate: null, projectId: null, indexStatus: 'not_indexed', indexError: null,
      },
    ]
    state.pending = [
      { localId: 'p1', fileName: 'pending.txt', status: 'ready', uploaded: null, error: null, source: null },
    ]
    await wrapper.vm.$nextTick()
    const text = wrapper.text()
    expect(text).toContain('linked.txt')
    expect(text).toContain('pending.txt')
  })

  test('send stays disabled while an upload runs or failed', async () => {
    const wrapper = mountBar()
    const store = useAttachmentsStore()
    const textarea = wrapper.find('textarea')
    await textarea.setValue('hello')

    // Uploading blocks send even with text present.
    store.stateFor('new').pending = [
      { localId: 'p1', fileName: 'a.txt', status: 'uploading', uploaded: null, error: null, source: null },
    ]
    await wrapper.vm.$nextTick()
    expect(sendButton(wrapper).attributes('disabled')).toBeDefined()

    // A failed upload also blocks send and surfaces the error with retry.
    store.stateFor('new').pending = [
      { localId: 'p1', fileName: 'a.txt', status: 'error', uploaded: null, error: 'Too big', source: null },
    ]
    await wrapper.vm.$nextTick()
    expect(sendButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Too big')
    expect(wrapper.text()).toContain('Retry')
  })

  test('send emits the prompt once uploads resolve', async () => {
    const wrapper = mountBar()
    const store = useAttachmentsStore()
    store.stateFor('new').pending = [
      { localId: 'p1', fileName: 'a.txt', status: 'ready', uploaded: null, error: null, source: null },
    ]
    await wrapper.find('textarea').setValue('hello')
    await wrapper.vm.$nextTick()
    expect(sendButton(wrapper).attributes('disabled')).toBeUndefined()
    await sendButton(wrapper).trigger('click')
    expect(wrapper.emitted('send-message')).toBeTruthy()
    expect(wrapper.emitted('send-message')![0]).toEqual(['hello', false])
  })

  test('attachment controls lock while generating', async () => {
    const wrapper = mountBar({ isGenerating: true })
    const buttons = wrapper.findAllComponents({ name: 'VBtn' })
    // Attach is the first button; it must be disabled during generation.
    expect(buttons[0]!.attributes('disabled')).toBeDefined()
  })

  test('keeps drafts per thread and ignores a late clear for edited text', async () => {
    const wrapper = mountBar()
    const textarea = wrapper.find('textarea')
    await textarea.setValue('draft for new')

    await wrapper.setProps({ threadKey: 'thread-1' })
    expect(wrapper.find('textarea').element.value).toBe('')
    await wrapper.find('textarea').setValue('draft for thread')

    await wrapper.setProps({ threadKey: 'new' })
    expect(wrapper.find('textarea').element.value).toBe('draft for new')

    await wrapper.find('textarea').setValue('edited after send')
    wrapper.vm.clearComposer('draft for new', 'new')
    expect(wrapper.find('textarea').element.value).toBe('edited after send')

    wrapper.vm.clearComposer('edited after send', 'new')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('textarea').element.value).toBe('')
  })

  test('shows an unlink failure instead of suppressing it', async () => {
    const wrapper = mountBar({ threadKey: 'thread-1' })
    const store = useAttachmentsStore()
    store.stateFor('thread-1').linked = [
      {
        id: 'f1', name: 'linked.txt', contentType: 'text/plain', headValue: null,
        creationDate: null, projectId: null, indexStatus: 'not_indexed', indexError: null,
      },
    ]
    vi.spyOn(fileRepo, 'unlinkThreadFile').mockRejectedValue({
      response: { status: 409, data: { detail: 'Generation already active' } },
    })

    await wrapper.vm.$nextTick()
    await wrapper.findComponent({ name: 'VChip' }).vm.$emit('click:close')
    await new Promise(resolve => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('still in use')
  })
})
