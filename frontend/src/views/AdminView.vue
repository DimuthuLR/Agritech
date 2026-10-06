<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Users, Plus, ShieldAlert } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import { usersApi, type TenantUser } from '../api/users'
import InviteUserModal from '../components/users/InviteUserModal.vue'
import UserRow from '../components/users/UserRow.vue'

const auth = useAuthStore()

const users = ref<TenantUser[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const showInvite = ref(false)

const isTenantAdmin = computed(
  () => auth.user?.tenant_role === 'tenant_admin',
)

async function load() {
  loading.value = true
  error.value = null
  try {
    users.value = await usersApi.list()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load users'
  } finally {
    loading.value = false
  }
}

function onCreated(u: TenantUser) {
  users.value.push(u)
  users.value.sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
}

function onUpdated(u: TenantUser) {
  const idx = users.value.findIndex((x) => x.id === u.id)
  if (idx >= 0) users.value[idx] = u
}

onMounted(load)
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">

    <!-- Header -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-semibold">Users</h1>
        <p class="text-muted text-sm mt-1">
          <template v-if="users.length">
            {{ users.length }} user{{ users.length === 1 ? '' : 's' }}
            in your organization
          </template>
          <template v-else>Manage who can access your farm</template>
        </p>
      </div>

      <button
        v-if="isTenantAdmin"
        class="btn-primary"
        @click="showInvite = true"
      >
        <Plus :size="16" :stroke-width="2" />
        Invite user
      </button>
    </div>

    <!-- Not an admin -->
    <div
      v-if="!isTenantAdmin"
      class="card flex items-start gap-3 border-warning/30 bg-warning/5"
    >
      <ShieldAlert :size="20" :stroke-width="1.75" class="text-warning shrink-0 mt-0.5" />
      <div class="text-sm">
        <p class="font-medium text-warning">Admin access required</p>
        <p class="text-muted mt-1">
          Only tenant administrators can manage users. Ask your
          administrator if you need something changed.
        </p>
      </div>
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="card text-sm text-muted">
      Loading users…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="card border-danger/40 text-danger text-sm">
      {{ error }}
    </div>

    <!-- Empty -->
    <div
      v-else-if="users.length === 0"
      class="card flex flex-col items-center gap-4 py-12 text-center"
    >
      <Users :size="32" :stroke-width="1.5" class="text-muted" />
      <p class="text-sm text-muted">No users found.</p>
    </div>

    <!-- User list -->
    <div v-else class="card p-0 divide-y divide-border">
      <UserRow
        v-for="u in users"
        :key="u.id"
        :user="u"
        :is-self="u.id === auth.user?.id"
        @updated="onUpdated"
      />
    </div>

    <!-- Invite modal -->
    <InviteUserModal
      :open="showInvite"
      @close="showInvite = false"
      @created="onCreated"
    />

  </div>
</template>