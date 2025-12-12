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
      <div class="w-100 d-flex justify-space-between align-end">
        <v-select
          v-model="mode"
          class="flex-grow-0"
          hide-details
          :items="modes"
          :menu-props="{
            transition: 'slide-y-transition',
          }"
          rounded
          variant="plain"
        />
        <v-btn class="pa-0" color="secondary" variant="tonal" @click="emitSendMessage">
          <v-icon>{{ isGenerating ? 'mdi-stop' : 'mdi-send' }}</v-icon>
        </v-btn>
      </div>
    </v-sheet>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onUnmounted, ref, unref, useTemplateRef } from 'vue'
  import { useDisplay } from 'vuetify'

  const display = useDisplay()
  const isMobile = ref(display.mobile)

  const prompt = ref('')
  const props = withDefaults(
    defineProps<{ isGenerating: boolean, modes?: string[] }>(),
    {
      modes: () => ['Always Quality', 'Prefer Quality', 'Prefer Speed'],
    },
  )
  const promptBarRef = useTemplateRef('promptBarRef')

  const mode = ref(props.modes[0])
  const emit = defineEmits<{ 'send-message': [prompt: string, mode: string] }>()

  function emitSendMessage () {
    if (!prompt.value) return
    if (!mode.value) return
    emit('send-message', unref(prompt), unref(mode)!)
    prompt.value = ''
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
