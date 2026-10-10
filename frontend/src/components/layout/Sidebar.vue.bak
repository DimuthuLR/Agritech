<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useTasksStore } from '../../stores/tasks'
import {
  LayoutDashboard,
  Sprout,
  CheckSquare,
  Leaf,
  Wallet,
  MessageCircle,
  Settings,
  Server,
  Users as UsersIcon,
  type LucideIcon,
} from 'lucide-vue-next'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const auth = useAuthStore()
const tasksStore = useTasksStore()

interface NavItem {
  name: string
  label: string
  icon: LucideIcon
  tenantAdminOnly?: boolean
  feature?: string
}

const tenantItems: NavItem[] = [
  { name: 'dashboard', label: 'Dashboard',  icon: LayoutDashboard },
  { name: 'plots',     label: 'Plots',      icon: Sprout },
  { name: 'tasks',     label: 'Tasks',      icon: CheckSquare },
  { name: 'diagnosis', label: 'Diagnosis',  icon: Leaf,          feature: 'diagnosis' },
  { name: 'finance',   label: 'Finance',    icon: Wallet,        feature: 'finance' },
  { name: 'chat',      label: 'Assistant',  icon: MessageCircle, feature: 'chat' },
  { name: 'admin',     label: 'Users',      icon: Settings,      tenantAdminOnly: true, feature: 'users' },
]

const platformItems: NavItem[] = [
  { name: 'platform-dashboard', label: 'Platform', icon: Server },
  { name: 'platform-sessions',  label: 'Support',  icon: UsersIcon },
]

const visibleItems = computed(() => {
  if (auth.isPlatformUser) {
    return platformItems
  }
  return tenantItems.filter((i) => {
    if (i.tenantAdminOnly && auth.user?.tenant_role !== 'tenant_admin') return false
    if (i.feature && !auth.hasFeature(i.feature)) return false
    return true
  })
})
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 bg-black/40 z-30 md:hidden"
    @click="emit('close')"
  />

  <aside
    :class="[
      'fixed md:static inset-y-0 left-0 z-40 md:z-auto',
      'w-64 flex flex-col py-5 transition-transform duration-200',
      'bg-surface border-r border-border',
      'shadow-[1px_0_2px_rgb(0_0_0_/_0.02)]',
      open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
    ]"
  >
    <nav class="flex flex-col gap-1 px-3">
      <router-link
        v-for="item in visibleItems"
        :key="item.name"
        :to="{ name: item.name }"
        class="group flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm
               transition-colors duration-150"
        :class="
          route.name === item.name
            ? 'bg-accent text-invert font-medium shadow-sm'
            : 'text-muted hover:text-text hover:bg-card-hover'
        "
        @click="emit('close')"
      >
        <component
          :is="item.icon"
          :size="18"
          :stroke-width="route.name === item.name ? 2.25 : 1.75"
        />
        <span class="flex-1">{{ item.label }}</span>
        <span
          v-if="item.name === 'tasks' && tasksStore.pendingCount"
          class="px-1.5 py-0.5 rounded-full text-[10px] font-semibold"
          :class="
            route.name === item.name
              ? 'bg-white/25 text-white'
              : 'bg-warning/15 text-warning'
          "
        >
          {{ tasksStore.pendingCount }}
        </span>
      </router-link>
    </nav>
  </aside>
</template>