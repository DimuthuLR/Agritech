<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
import { useRouter } from 'vue-router'
import { AlertCircle, LogOut } from 'lucide-vue-next'

const auth = useAuthStore()
const router = useRouter()

async function exitImpersonation() {
  await auth.endImpersonation()
  router.push({ name: 'platform' })
}
</script>

<template>
  <div
    v-if="auth.isImpersonating && auth.impersonation"
    class="sticky top-0 z-50 bg-warning/95 text-black px-4 py-2
           flex items-center gap-3 text-sm font-medium border-b border-warning"
  >
    <AlertCircle :size="16" :stroke-width="2.25" />
    <span>
      Impersonating
      <strong>{{ auth.impersonation.targetUser.email }}</strong>
    </span>
    <span class="flex-1"></span>
    <button
      class="px-3 py-1 rounded-sm bg-black/10 hover:bg-black/20
             text-xs font-medium transition-colors flex items-center gap-1.5"
      @click="exitImpersonation"
    >
      <LogOut :size="12" :stroke-width="2" />
      Exit impersonation
    </button>
  </div>
</template>