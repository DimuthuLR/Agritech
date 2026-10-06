<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

async function submit() {
  error.value = null
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-bg text-text flex items-center justify-center p-4">
    <div class="w-full max-w-sm card">

      <div class="flex items-center gap-2 mb-6">
        <img src="/favicon.svg" alt="AgriTech Logo" class="w-8 h-8 rounded-sm" />
        <h1 class="text-xl font-semibold">AgriTech</h1>
      </div>

      <form @submit.prevent="submit" class="space-y-4">
        <div>
          <label class="block text-sm text-muted mb-1">Email</label>
          <input
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="input"
            placeholder="you@farm.lk"
          />
        </div>

        <div>
          <label class="block text-sm text-muted mb-1">Password</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="input"
            placeholder="••••••••"
          />
        </div>

        <div v-if="error" class="text-sm text-danger bg-danger/10 rounded-sm px-3 py-2">
          {{ error }}
        </div>
        <button type="submit" :disabled="loading" class="btn-primary w-full">
          {{ loading ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

    </div>
  </div>
</template>