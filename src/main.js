import { createApp } from 'vue'

import App from './App.vue'
import pinia from './stores'
import router from './router'
import { useAuthStore } from './stores/auth'
import { setUnauthorizedHandler } from './api/http'

import './style.css'

try {
  const savedTheme = window.localStorage.getItem('omnixa-theme')
  if (savedTheme === 'dark' || savedTheme === 'light') {
    document.documentElement.dataset.theme = savedTheme
  }
} catch {
  // The default light theme is retained when storage is unavailable.
}

const app = createApp(App)

app.use(pinia)
app.use(router)

const authStore = useAuthStore(pinia)

setUnauthorizedHandler(() => {
  authStore.resetAuth()
})

app.mount('#app')

if (authStore.token && !authStore.initialized) {
  authStore.fetchCurrentUser().catch(async () => {
    // fetchCurrentUser resets stale authentication. Finish the initial navigation
    // before deciding whether the failed recovery left us on a protected page.
    await router.isReady()
    if (router.currentRoute.value.meta.requiresAuth) {
      await router.replace('/login')
    }
  })
}
