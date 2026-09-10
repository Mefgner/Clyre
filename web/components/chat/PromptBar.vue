<template>
  <div class="w-100">
    <v-sheet
      class="pa-4 pt-1 mb-3 pointer-events-auto"
      color="primary-darken-2"
      :elevation="12"
      rounded="xl"
    >
      <div v-if="attachments.pending.length > 0 || attachments.linked.length > 0" class="d-flex flex-wrap ga-2 pt-2">
        <v-chip
          v-for="file in attachments.linked"
          :key="`linked-${file.id}`"
          closable
          color="secondary"
          :disabled="locked"
          size="small"
          variant="tonal"
          @click:close="unlinkFile(file.id)"
        >
          <v-icon start>mdi-file-document-outline</v-icon>
          {{ file.name }}
        </v-chip>
        <v-chip
          v-for="item in attachments.pending"
          :key="item.localId"
          :closable="!locked"
          :color="item.status === 'error' ? 'error' : 'secondary'"
          size="small"
          variant="tonal"
          @click:close="removePendingChip(item.localId)"
        >
          <v-icon start>{{ item.status === 'uploading' ? 'mdi-loading mdi-spin' : 'mdi-file-upload-outline' }}</v-icon>
          {{ item.fileName }}
          <span v-if="item.status === 'uploading'" class="ml-1">…</span>
        </v-chip>
      </div>
      <div v-for="item in attachments.pending.filter(p => p.status === 'error')" :key="`err-${item.localId}`" class="d-flex align-center ga-2 pt-1 text-error text-caption">
        <span class="flex-1-1">{{ item.fileName }}: {{ item.error }}</span>
        <v-btn
          color="error"
          :disabled="locked"
          size="x-small"
          variant="text"
          @click="retryUpload(item.localId)"
        >Retry</v-btn>
      </div>
      <div v-if="attachments.loadError" class="pt-1 text-error text-caption">
        {{ attachments.loadError }}
      </div>
      <div>
        <v-textarea
          ref="promptBarRef"
          v-model="prompt"
          auto-grow
          density="comfortable"
          hide-details
          max-rows="4"
          :placeholder="'Ask Clyre ' + (isMobile ? '' : '(Shift + Enter to new line, Enter to send)')"
          rows="1"
          variant="plain"
          @keydown.enter.exact.stop.prevent="emitSendMessage"
        />
      </div>
      <div class="w-100 d-flex justify-end align-end">
        <input
          ref="fileInputRef"
          accept=".txt,.md,.markdown,.rst,.csv,.json,.log,.py,text/*"
          hidden
          multiple
          type="file"
          @change="onFilesPicked"
        >
        <v-btn
          class="pa-0 mr-2"
          :disabled="locked"
          title="Attach text files"
          variant="tonal"
          @click="openPicker"
        >
          <v-icon>mdi-paperclip</v-icon>
        </v-btn>
        <v-btn
          class="pa-0 mr-2"
          :color="thinkingEnabled ? 'secondary' : 'default'"
          :title="thinkingEnabled ? 'Reasoning on: the model thinks before answering' : 'Reasoning off: instant answer'"
          variant="tonal"
          @click="thinkingEnabled = !thinkingEnabled"
        >
          <v-icon>mdi-brain</v-icon>
        </v-btn>
        <div v-if="unlinkError" class="flex-1-1 mr-2 text-error text-caption">
          {{ unlinkError }}
        </div>
        <v-btn
          class="pa-0"
          color="secondary"
          :disabled="sendDisabled"
          :title="sendTitle"
          variant="tonal"
          @click="onButtonClick"
        >
          <v-icon>{{ isGenerating ? 'mdi-stop' : 'mdi-send' }}</v-icon>
        </v-btn>
      </div>
    </v-sheet>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, reactive, ref, useTemplateRef, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import {
    describeUnlinkError,
    hasBlockingAttachments,
    httpDetail,
    httpStatus,
  } from '@/entities/file.ts'
  import { useAttachmentsStore } from '@/stores/attachments.ts'

  const display = useDisplay()
  const isMobile = ref(display.mobile)
  const props = defineProps<{ isGenerating: boolean, threadKey: string, starting: boolean }>()

  const prompt = ref('')
  const unlinkError = ref('')
  // One draft per composer key: switching threads must not carry (or wipe) the
  // text of another conversation, and a late send confirmation must not clear
  // a draft the user has since edited.
  const drafts = reactive<Record<string, string>>({})
  watch(() => props.threadKey, (next, previous) => {
    drafts[previous] = prompt.value
    prompt.value = drafts[next] ?? ''
    unlinkError.value = ''
  })
  watch(prompt, value => {
    drafts[props.threadKey] = value
  })
  // Reasoning toggle, default off: Qwen3.5 thinks by default and small-model
  // reasoning loops can burn the whole context before answering (known issue #18).
  const thinkingEnabled = ref(false)
  const promptBarRef = useTemplateRef('promptBarRef')
  const fileInputRef = useTemplateRef<HTMLInputElement>('fileInputRef')

  const attachmentsStore = useAttachmentsStore()
  const attachments = computed(() => attachmentsStore.stateFor(props.threadKey))
  const locked = computed(() => props.isGenerating || props.starting)

  const sendDisabled = computed(() => {
    if (props.isGenerating) return false
    if (props.starting) return true
    if (!prompt.value) return true
    return hasBlockingAttachments(attachments.value)
  })
  const sendTitle = computed(() => {
    if (hasBlockingAttachments(attachments.value)) return 'Finish or remove failed uploads before sending'
    return ''
  })

  const emit = defineEmits<{ 'send-message': [prompt: string, enableThinking: boolean], 'stop': [] }>()

  function openPicker () {
    if (locked.value) return
    fileInputRef.value?.click()
  }

  async function onFilesPicked (event: Event) {
    const input = event.target as HTMLInputElement
    const files = input.files ? Array.from(input.files) : []
    input.value = ''
    if (files.length === 0 || locked.value) return
    await attachmentsStore.queueFiles(props.threadKey, files)
  }

  function removePendingChip (localId: string) {
    if (locked.value) return
    attachmentsStore.removePending(props.threadKey, localId)
  }

  async function retryUpload (localId: string) {
    if (locked.value) return
    await attachmentsStore.retryPending(props.threadKey, localId)
  }

  async function unlinkFile (fileId: string) {
    if (locked.value) return
    if (props.threadKey === 'new') return
    unlinkError.value = ''
    try {
      await attachmentsStore.removeLinked(props.threadKey, props.threadKey, fileId)
    } catch (error) {
      // State was rolled back; the user still has to learn why (409 while a
      // generation is running is actionable, not silent).
      unlinkError.value = describeUnlinkError(httpStatus(error), httpDetail(error))
    }
  }

  function emitSendMessage () {
    if (!prompt.value) return
    if (props.isGenerating || props.starting) return
    if (hasBlockingAttachments(attachments.value)) return
    // The composer clears only after the server accepts the message
    // (index.vue calls clearComposer on user_message_insert).
    emit('send-message', prompt.value, thinkingEnabled.value)
  }

  /**
   * Clear the draft of `key` (default: the visible one) but only when it still
   * holds `sentText` — the confirmation can arrive after the user edited the
   * text or switched threads.
   */
  function clearComposer (sentText?: string, key?: string) {
    const target = key ?? props.threadKey
    const stored = drafts[target]
    const untouched = target === props.threadKey
      ? prompt.value === sentText
      : stored === sentText
    if (sentText !== undefined && !untouched) return
    drafts[target] = ''
    if (target === props.threadKey) {
      prompt.value = ''
    }
  }

  function onButtonClick () {
    if (props.isGenerating) {
      emit('stop')
      return
    }
    emitSendMessage()
  }

  function handleTyping (event: KeyboardEvent) {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
    if (event.key.length !== 1) return
    promptBarRef.value?.focus()
  }

  onMounted(() => document.addEventListener('keydown', handleTyping))
  onUnmounted(() => document.removeEventListener('keydown', handleTyping))

  defineExpose({ clearComposer })
</script>
