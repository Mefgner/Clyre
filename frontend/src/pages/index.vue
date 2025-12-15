<template>
  <v-navigation-drawer
    v-model="drawer"
    :permanent="!isMobile"
    :rail="isRail && !isMobile"
    rail-width="65"
    width="260"
  >
    <template #prepend>
      <div class="d-flex align-center pa-2 mt-2" :class="(isRail && !isMobile) ? 'justify-center' : 'justify-space-between'">
        <span v-show="!isRail || isMobile" class="font-weight-light ml-1 text-h5">Clyre</span>
        <v-btn
          color="grey-darken-1"
          icon
          size="small"
          variant="text"
          @click="() => {isMobile ? (drawer = !drawer) : (isRail = !isRail)}"
        >
          <v-icon>{{ isMobile ? 'mdi-close' : (isRail ? 'mdi-dock-right' : 'mdi-dock-left') }}</v-icon>
        </v-btn>
      </div>

      <div class="px-2 mb-2 d-flex mt-2" :class="isRail ? 'justify-center' : ''">
        <v-btn
          :block="!isRail"
          class="text-none overflow-x-hidden"
          color="secondary"
          height="40"
          :icon="isRail"
          variant="tonal"
          @click="goNewThreadPage"
        >
          <v-icon :class="{ 'mr-2': !isRail }">mdi-plus</v-icon>

          <span v-if="!isRail" class="font-weight-regular text-body-1">New Chat</span>
        </v-btn>
      </div>
    </template>

    <div v-show="!isRail">
      <v-list id="chatList" density="compact" nav>
        <v-list-item
          v-for="(chat, index) in Array.from(threadStore.threadsMeta).reverse()"
          :key="chat.title + chat.id + String(index)"
          link
          rounded="xl"
          :to="{ name: 'chat', params: { chatId: chat.id } }"
          :value="chat.id"
          @click="console.log('link clicked')"
        >
          <template #title>
            <span class="mx-2">
              {{ chat.title }}
            </span>
          </template>
        </v-list-item>
      </v-list>
    </div>

    <template #append>
      <div class="d-flex align-center mb-1 pa-2" :class="!isRail ? 'justify-space-between' : 'justify-center'">
        <v-btn
          :class="!isRail ? 'd-flex align-center' : ''"
          disabled
          height="40"
          :icon="isRail"
          rounded="xl"
          variant="tonal"
        >
          <template #default>
            <v-icon>mdi-account</v-icon>
          </template>
          <template #append>
            <span v-show="!isRail" style="margin-top: -1px;">
              {{ userStore.currentUser?.name }}
            </span>
          </template>
        </v-btn>
        <v-btn
          v-show="!isRail"
          color="secondary"
          height="40"
          variant="tonal"
          @click="logout"
        >
          <v-icon>mdi-logout</v-icon>
        </v-btn>
      </div>
    </template>

  </v-navigation-drawer>

  <v-app-bar class="bg-transparent blur" density="default">
    <v-row align="center" :class="'position-relative' + (isMobile ? 'px-5' : 'pa-2')" justify="space-between">
      <div class="position-absolute top-0 left-0 bottom-0 d-flex align-center" :class="isMobile ? 'px-4' : 'px-2'">
        <v-btn v-if="isMobile" class="position-absolute" icon @click="drawer = !drawer"><v-icon>mdi-menu</v-icon></v-btn>
      </div>

      <span class="ma-auto font-weight-light text-h6">{{ smartThreadTitle }}</span>
      <div class="position-absolute top-0 right-0 bottom-0 d-flex align-center" :class="isMobile ? 'px-4' : 'px-2'">
        <v-btn
          color="primary"
          :disabled="!threadStore.currentThread.id"
          icon
          size="small"
          variant="tonal"
          @click="callDeleteThread"
          @keyup.delete.stop.prevent="callDeleteThread"
        ><v-icon>mdi-delete</v-icon></v-btn>
      </div>
    </v-row>
  </v-app-bar>

  <div
    class="top-chat-shadow position-fixed bottom-0 left-0 right-0 w-100"
  />

  <div
    class="bottom-chat-shadow position-fixed top-0 left-0 right-0 w-100"
  />

  <v-container class="fill-height align-start justify-center pa-0">
    <v-row class="ma-1" justify="center" no-gutters>
      <v-col class="pa-4" lg="6">
        <router-view :key="String($route?.params?.chatId)" v-slot="{ Component }">
          <Component :is="Component" />
        </router-view>
        <div style="height: 128px; flex-shrink: 0;" />
      </v-col>
    </v-row>
  </v-container>

  <v-footer
    app
    class="justify-center pa-0 pointer-events-none"
    shadow="shadow"
  >
    <v-container class="pa-0" fluid style="position: relative;">
      <v-row class="ma-0" justify="center">
        <v-col
          class="position-absolute bottom-0 w-100 px-4 pb-4"
          cols="12"
          lg="6"
          md="11"
          style="z-index: 50;"
        >
          <v-fade-transition>
            <prompt-bar :is-generating="threadStore.isGenerating" @send-message="generateAnswer" />
          </v-fade-transition>
        </v-col>
      </v-row>
    </v-container>
  </v-footer>
</template>

<script lang="ts" setup>
  import type PromptBar from '@/components/chat/PromptBar.vue'
  import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { useAuthStore } from '@/stores/auth.ts'
  import { useThreadStore } from '@/stores/thread.ts'
  import { useUiStore } from '@/stores/ui.ts'
  import { useUserStore } from '@/stores/user.ts'

  const mobile = useDisplay()
  const isMobile = ref(mobile.mobile)
  const drawer = ref(!isMobile.value)
  const isRail = ref(false)

  const authStore = useAuthStore()
  const userStore = useUserStore()
  const threadStore = useThreadStore()
  const uiStore = useUiStore()

  const smartThreadTitle = computed(() => {
    const thread = threadStore.currentThread
    if (!thread.title) return 'New Chat'
    if (isMobile.value) {
      return thread.title.slice(0, 23) + (thread.title.length > 23 ? '...' : '')
    }
    return thread.title
  })

  const router = useRouter()

  const abortController = ref(new AbortController())

  const intervalId = ref(0)

  onMounted(() => {
    watch(() => authStore.isLoggedIn, async () => {
      if (!authStore.isLoggedIn) return
      await userStore.getUser()
      await threadStore.getThreadsMeta()
    }, { immediate: true })

    intervalId.value = setInterval(() => {
      if (!authStore.isLoggedIn) {
        return
      }
      threadStore.getThreadsMeta()
    }, 60_000)
  })

  onUnmounted(() => {
    clearInterval(intervalId.value)
  })

  function goNewThreadPage () {
    threadStore.clearCurrent()
    router.push({ name: 'chat', params: { chatId: 'new' } })
  }

  function logout () {
    threadStore.clearCurrent()
    threadStore.clearThreadsMeta()
    authStore.logout().then(() => router.push({ name: 'index' }))
  }

  function callDeleteThread () {
    if (!threadStore.currentThread.id) {
      return
    }
    uiStore.openDeleteConfirm()
  }

  async function generateAnswer (prompt: string, mode: string) {
    if (threadStore.isGenerating) {
      abortController.value.abort()
      return
    }

    threadStore.pushUserMessage(prompt)
    const accessToken = authStore.accessToken
    if (!accessToken) return

    try {
      abortController.value = new AbortController()

      for await (const payload of threadStore.getAssistantMessagePipeline(prompt, mode, accessToken, abortController.value.signal)) {
        if ((payload.event === 'user_message_insert' || payload.event === 'assistant_message_insert')) {
          threadStore.getThreadsMeta().then(async () => {
            threadStore.setCurrentThread(threadStore.currentThread!)

            const nextId = threadStore.currentThread?.id
            if (nextId) {
              await router.push({ name: 'chat', params: { chatId: nextId } })
            } else {
              console.error('No next chat id')
            }
          })
        }
      }
    } catch (error) {
      console.error('Failed to generate answer', error)
    }
  }
</script>
