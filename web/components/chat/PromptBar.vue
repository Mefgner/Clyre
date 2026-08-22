<template>
  <div class="w-100">
    <v-sheet
      class="pa-4 pt-1 mb-3 pointer-events-auto"
      color="primary-darken-2"
      :elevation="12"
      rounded="xl"
    >
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
        <v-btn
          class="pa-0 mr-2"
          :color="thinkingEnabled ? 'secondary' : 'default'"
          :title="thinkingEnabled ? 'Reasoning on: the model thinks before answering' : 'Reasoning off: instant answer'"
          variant="tonal"
          @click="thinkingEnabled = !thinkingEnabled"
        >
          <v-icon>mdi-brain</v-icon>
        </v-btn>
        <v-btn
          class="pa-0"
          color="secondary"
          :disabled="!isGenerating && !prompt"
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
  import { onMounted, onUnmounted, ref, useTemplateRef } from 'vue'
  import { useDisplay } from 'vuetify'

  const display = useDisplay()
  const isMobile = ref(display.mobile)

  const prompt = ref('')
  // Reasoning toggle, default off: Qwen3.5 thinks by default and small-model
  // reasoning loops can burn the whole context before answering (known issue #18).
  const thinkingEnabled = ref(false)
  const props = defineProps<{ isGenerating: boolean }>()
  const promptBarRef = useTemplateRef('promptBarRef')

  const emit = defineEmits<{ 'send-message': [prompt: string, enableThinking: boolean], 'stop': [] }>()

  function emitSendMessage () {
    if (!prompt.value) return
    if (props.isGenerating) return
    emit('send-message', prompt.value, thinkingEnabled.value)
    prompt.value = ''
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

</script>
