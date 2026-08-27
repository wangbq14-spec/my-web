import { createApp } from 'vue'

import App from './App.vue'
import pinia from './stores'
import router from './router'
import { useAuthStore } from './stores/auth'
import { setUnauthorizedHandler } from './api/http'

import './style.css'

const app = createApp(App)

app.use(pinia)
app.use(router)

setUnauthorizedHandler(() => {
  useAuthStore(pinia).resetAuth()
})

app.mount('#app')
