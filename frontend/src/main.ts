/// <reference types="vite-plugin-pwa/client" />

import { registerSW } from 'virtual:pwa-register'

registerSW({ immediate: true })

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// If we boot with a stored session, refresh the feature map in the
// background. Fire-and-forget: the UI renders immediately with the
// cached map from localStorage and updates when the fetch resolves.
const auth = useAuthStore(pinia)
if (auth.isAuthenticated) {
  auth.loadFeatures()
}

app.use(router)
app.mount('#app')