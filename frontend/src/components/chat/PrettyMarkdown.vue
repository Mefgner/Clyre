<script setup lang="ts">
  import hljs from 'highlight.js'
  import { Marked } from 'marked'
  import { markedHighlight } from 'marked-highlight'
  import { computed, onBeforeUnmount, watch } from 'vue'
  import { useTheme } from 'vuetify'

  const theme = useTheme()

  let currentStyleLink: HTMLLinkElement | null = null

  function applyHighlightTheme () {
    if (currentStyleLink) {
      currentStyleLink.remove()
    }

    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = theme.current.value.dark
      ? import.meta.env.VITE_HLJS_DARK_STYLE_URL
      : import.meta.env.VITE_HLJS_LIGHT_STYLE_URL

    document.head.append(link)
    currentStyleLink = link
  }

  watch(() => theme.current.value.dark, applyHighlightTheme, { immediate: true })

  onBeforeUnmount(() => {
    currentStyleLink?.remove()
  })

  const props = defineProps<{ value: string }>()

  const markedParser = new Marked(markedHighlight({
    langPrefix: 'hljs language-',
    highlight: (code, lang) => {
      const language = hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    },
  }))

  const rendered = computed(() => {
    if (!props.value) return ''
    return markedParser.parse(props.value)
  })
</script>

<template>
  <div :key="$route.fullPath" class="w-100 pretty-rendered" v-html="rendered" />
</template>
