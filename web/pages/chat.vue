<script setup lang="ts">
  import { onUnmounted, useTemplateRef, watch } from 'vue'
  import { useThreadStore } from '@/stores/thread.ts'

  const threadStore = useThreadStore()
  const props = defineProps<{ chatId: string }>()
  const chatHistoryFooter = useTemplateRef<HTMLDivElement>('chatHistoryFooter')

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
      <div v-if="chat?.content">
        <user-prompt-bubble v-if="chat.role === 'user'" :message="chat.content" />
        <chat-answer v-else-if="chat.role === 'assistant'" :message="chat.content" />
      </div>
    </div>
    <div ref="chatHistoryFooter" />
  </div>
</template>
