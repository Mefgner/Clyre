<script setup lang="ts">
  import { computed, onUnmounted, useTemplateRef, watch } from 'vue'
  import { useThreadStore } from '@/stores/thread.ts'

  const threadStore = useThreadStore()
  const props = defineProps<{ chatId: string }>()
  const chatHistoryFooter = useTemplateRef<HTMLDivElement>('chatHistoryFooter')

  // Global isGenerating alone marks the last message of an unrelated thread
  // as streaming; tie the state to THIS thread (live stream or server flag).
  const thisThreadGenerating = computed(() =>
    threadStore.isGenerating
    && (threadStore.activeStreamThreadId === threadStore.currentThread.id
      || threadStore.currentThread.isGenerating === true))

  watch([() => threadStore.threadsMeta, () => props.chatId], async () => {
    const threadMeta = threadStore.threadsMeta.find(thread => thread.id === props.chatId)
    if (!threadMeta) return
    if (threadStore.currentThread.id === threadMeta.id) return
    threadStore.setCurrentThread(threadMeta)
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
    <div v-for="(chat, index) in threadStore.currentThread.messages" :key="`chat-message-${index}`">
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
