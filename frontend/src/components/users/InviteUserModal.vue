<script setup lang="ts">
import { ref, watch } from 'vue'
import { X, UserPlus } from 'lucide-vue-next'
import {
  usersApi,
  ROLE_HINTS,
  ROLE_LABELS,
  type TenantRole,
  type TenantUser,
} from '../../api/users'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  close: []
  created: [TenantUser]
}>()

const email = ref('')
const fullName = ref('')
const password = ref('')
const role = ref<TenantRole>('operator')
const submitting = ref(false)
const error = ref<string | null>(null)

const roleOptions: TenantRole[] = [
  'viewer',
  'operator',
  'agronomist',
  'tenant_admin',
]

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      email.value = ''
      fullName.value = ''
      password.value = ''
      role.value = 'operator'
      error.value = null
    }
  },
)

async function submit() {
  if (!email.value.trim() || !password.value.trim()) {
    error.value = 'Email and password are required'
    return
  }
  if (password.value.length < 8) {
    error.value = 'Password must be at least 8 characters'
    return
  }

  submitting.value = true
  error.value = null
  try {
    const created = await usersApi.create({
      email: email.value.trim(),
      password: password.value,
      full_name: fullName.value.trim() || null,
      role: role.value,
    })
    emit('created', created)
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to create user'
  } finally {
    submitting.value = false
  }
}

function close() {
  if (submitting.value) return
  emit('close')
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4
           bg-black/50 backdrop-blur-sm"
    @click.self="close"
  >
    <div class="card w-full max-w-md max-h-[90vh] overflow-y-auto">

      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-2">
          <UserPlus :size="18" :stroke-width="1.75" class="text-accent" />
          <h2 class="text-lg font-semibold">Invite user</h2>
        </div>
        <button class="text-muted hover:text-text" @click="close">
          <X :size="18" :stroke-width="1.75" />
        </button>
      </div>

      <form @submit.prevent="submit" class="space-y-4">

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            Email
          </label>
          <input
            v-model="email"
            type="email"
            class="input"
            placeholder="name@example.com"
            required
          />
        </div>

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            Full name (optional)
          </label>
          <input
            v-model="fullName"
            class="input"
            placeholder="Carol Perera"
          />
        </div>

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            Initial password
          </label>
          <input
            v-model="password"
            type="password"
            class="input"
            placeholder="At least 8 characters"
            required
          />
          <p class="text-xs text-muted mt-1">
            Share this with the user out-of-band. They can change it later.
          </p>
        </div>

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            Role
          </label>
          <select v-model="role" class="input">
            <option v-for="r in roleOptions" :key="r" :value="r">
              {{ ROLE_LABELS[r] }}
            </option>
          </select>
          <p class="text-xs text-muted mt-1">
            {{ ROLE_HINTS[role] }}
          </p>
        </div>

        <div
          v-if="error"
          class="text-sm text-danger bg-danger/10 rounded-sm px-3 py-2"
        >
          {{ error }}
        </div>

        <div class="flex gap-2 pt-2">
          <button type="button" class="btn-ghost flex-1" @click="close">
            Cancel
          </button>
          <button type="submit" class="btn-primary flex-1" :disabled="submitting">
            {{ submitting ? 'Creating…' : 'Invite' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>