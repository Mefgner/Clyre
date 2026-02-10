// Composables
import { createRouter, createWebHistory } from 'vue-router'
import Index from '@/pages/index.vue'
import { useAuthStore } from '@/stores/auth.ts'
import { useThreadStore } from '@/stores/thread.ts'
import { useUiStore } from '@/stores/ui.ts'
import { useUserStore } from '@/stores/user.ts'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'index',
      component: Index,
      children: [
        {
          path: '/:chatId',
          name: 'chat',
          component: () => import('@/pages/chat.vue'),
          props: true,
          meta: {
            requiresAuth: true,
          },
        },
      ],
    },
  ],
})

router.beforeEach(async (to, _, next) => {
  const authStore = useAuthStore()
  const uiStore = useUiStore()

  document.title = 'Clyre'

  if (to.meta.requiresAuth && !authStore.accessToken) {
    try {
      await authStore.refreshAccessToken()
    } catch (error) {
      console.error('Failed to refresh access token', error)
      uiStore.openLogin()
      return next({ name: 'index' })
    }
  }

  next()
})

// Workaround for https://github.com/vitejs/vite/issues/11804
router.onError((err, to) => {
  if (err?.message?.includes?.('Failed to fetch dynamically imported module')) {
    if (localStorage.getItem('vuetify:dynamic-reload')) {
      console.error('Dynamic import error, reloading page did not fix it', err)
    } else {
      console.log('Reloading page to fix dynamic import error')
      localStorage.setItem('vuetify:dynamic-reload', 'true')
      location.assign(to.fullPath)
    }
  } else {
    console.error(err)
  }
})

router.isReady().then(() => {
  localStorage.removeItem('vuetify:dynamic-reload')

  const authStore = useAuthStore()
  authStore.refreshAccessToken()
    .catch(() => {
      useUiStore().openLogin()
    })
})

export default router
