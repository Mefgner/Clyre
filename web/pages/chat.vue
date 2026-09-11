<script setup lang="ts">
  import { computed, onUnmounted, useTemplateRef, watch } from 'vue'
  import { useAttachmentsStore } from '@/stores/attachments.ts'
  import { useThreadStore } from '@/stores/thread.ts'

  const threadStore = useThreadStore()
  const attachmentsStore = useAttachmentsStore()
  const props = defineProps<{ chatId: string }>()
  const chatHistoryFooter = useTemplateRef<HTMLDivElement>('chatHistoryFooter')

  // Global isGenerating alone marks the last message of an unrelated thread
  // as streaming; tie the state to THIS thread (live stream or server flag).
  const thisThreadGenerating = computed(() =>
    threadStore.isGenerating
    && (threadStore.activeStreamThreadId === threadStore.currentThread.id
      || threadStore.currentThread.isGenerating === true))

  const contextBoundaryOrder = computed(() => {
    const window = threadStore.contextWindow
    return window && window.omittedMessages > 0 ? window.firstIncludedOrder : null
  })

  watch([() => threadStore.threadsMeta, () => props.chatId], async () => {
    if (props.chatId === 'new') return
    const threadMeta = threadStore.threadsMeta.find(thread => thread.id === props.chatId)
    if (!threadMeta) return
    if (threadStore.currentThread.id === threadMeta.id) return
    await threadStore.setCurrentThread(threadMeta)
    // Reopening a thread shows its linked attachments; failures surface
    // inline in the composer, never as a blocking error.
    await attachmentsStore.loadLinked(threadMeta.id).catch(() => {})
  }, { immediate: true })

  watch(() => threadStore.currentThread.messages, () => {
    if (!chatHistoryFooter.value) return
    chatHistoryFooter.value.scrollIntoView({ behavior: 'smooth' })
  })

  onUnmounted(() => {
    if (props.chatId === 'new') return
    threadStore.clearCurrent()
  })
</script>

<template>
  <div class="d-flex flex-column justify-start w-100">
    <div v-for="(chat, index) in threadStore.currentThread.messages" :key="`chat-message-${chat.order ?? index}`">
      <div
        v-if="contextBoundaryOrder !== null && chat.order === contextBoundaryOrder"
        class="context-window-boundary d-flex align-center ga-3 my-4"
      >
        <v-divider />
        <div class="text-medium-emphasis text-caption text-center flex-shrink-0">
          <div>Модель видит сообщения начиная отсюда</div>
          <div class="text-disabled">Для новой темы лучше открыть новый чат</div>
        </div>
        <v-divider />
      </div>
      <user-prompt-bubble v-if="chat.role === 'user'" :message="chat.content ?? ''" />
      <chat-answer
        v-else-if="chat.role === 'assistant'"
        :message="chat.content ?? ''"
        :streaming="thisThreadGenerating && index === threadStore.currentThread.messages.length - 1"
        :thinking="chat.thinking"
      />
    </div>
    <div ref="chatHistoryFooter" />
  </div>
</template>

<style scoped>
.context-window-boundary {
  opacity: 0.72;
}
</style>
