<script setup lang="ts">
  import hljs from 'highlight.js'
  import { Marked } from 'marked'
  import { markedHighlight } from 'marked-highlight'
  import { computed } from 'vue'
  import { useTheme } from 'vuetify'

  const theme = useTheme()

  if (theme.current.value.dark) {
    import('highlight.js/styles/agate.min.css')
  } else {
    import('highlight.js/styles/github.css')
  }

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
