<script setup lang="ts">
import { ref, computed } from 'vue'
import { MoreVertical, Shield, UserX, UserCheck } from 'lucide-vue-next'
import {
  usersApi,
  ROLE_LABELS,
  type TenantRole,
  type TenantUser,
} from '../../api/users'

const props = defineProps<{
  user: TenantUser
  isSelf: boolean
}>()

const emit = defineEmits<{ updated: [TenantUser] }>()

const menuOpen = ref(false)
const editingRole = ref(false)
const busy = ref(false)

const roleOptions: TenantRole[] = [
  'viewer',
  'operator',
  'agronomist',
  'tenant_admin',
]

const displayName = computed(
  () => props.user.full_name || props.user.email.split('@')[0],
)

const initials = computed(() =>
  displayName.value
    .split(' ')
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
    .slice(0, 2),
)

async function changeRole(newRole: TenantRole) {
  if (newRole === props.user.tenant_role) {
    editingRole.value = false
    return
  }
  busy.value = true
  try {
    const updated = await usersApi.update(props.user.id, { role: newRole })
    emit('updated', updated)
    editingRole.value = false
  } finally {
    busy.value = false
  }
}

async function toggleActive() {
  busy.value = true
  try {
    const updated = await usersApi.update(props.user.id, {
      is_active: !props.user.is_active,
    })
    emit('updated', updated)
    menuOpen.value = false
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="p-4 flex items-center gap-3 hover:bg-card-hover transition-colors">

    <!-- Avatar -->
    <div
      class="w-9 h-9 rounded-full bg-accent-soft text-accent
             flex items-center justify-center text-xs font-medium shrink-0"
    >
      {{ initials }}
    </div>

    <!-- Identity -->
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2">
        <span class="font-medium text-sm truncate">{{ displayName }}</span>
        <span
          v-if="isSelf"
          class="text-[10px] uppercase tracking-wide text-muted"
        >
          You
        </span>
        <span
          v-if="!user.is_active"
          class="pill-danger text-[10px]"
        >
          Deactivated
        </span>
      </div>
      <div class="text-xs text-muted truncate">{{ user.email }}</div>
    </div>

    <!-- Role — inline editable for non-self users -->
    <div class="shrink-0 relative">
      <select
        v-if="editingRole && !isSelf"
        :value="user.tenant_role"
        class="input text-xs py-1 pr-6"
        :disabled="busy"
        @change="(e) => changeRole((e.target as HTMLSelectElement).value as TenantRole)"
        @blur="editingRole = false"
      >
        <option v-for="r in roleOptions" :key="r" :value="r">
          {{ ROLE_LABELS[r] }}
        </option>
      </select>

      <button
        v-else
        :class="[
          'pill text-xs',
          isSelf ? 'pill-muted cursor-default' : 'hover:opacity-80',
        ]"
        :disabled="isSelf"
        @click="!isSelf && (editingRole = true)"
      >
        <Shield :size="11" :stroke-width="2" />
        {{ user.tenant_role ? ROLE_LABELS[user.tenant_role] : '—' }}
      </button>
    </div>

    <!-- More menu — hidden for self -->
    <div v-if="!isSelf" class="relative shrink-0">
      <button
        class="p-1.5 rounded-sm text-muted hover:text-text hover:bg-card-hover"
        @click="menuOpen = !menuOpen"
      >
        <MoreVertical :size="16" :stroke-width="1.75" />
      </button>

      <div
        v-if="menuOpen"
        class="absolute right-0 top-full mt-1 z-10
               w-48 card p-1 shadow-lg"
      >
        <button
          class="w-full text-left px-3 py-2 rounded-sm text-sm
                 hover:bg-card-hover flex items-center gap-2"
          :disabled="busy"
          @click="toggleActive"
        >
          <component
            :is="user.is_active ? UserX : UserCheck"
            :size="14" :stroke-width="1.75"
          />
          {{ user.is_active ? 'Deactivate' : 'Reactivate' }}
        </button>
      </div>
    </div>

    <!-- Backdrop for menu close -->
    <div
      v-if="menuOpen"
      class="fixed inset-0 z-0"
      @click="menuOpen = false"
    />
  </div>
</template>