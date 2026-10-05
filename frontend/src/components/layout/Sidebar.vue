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
  platformOnly?: boolean
}

const items: NavItem[] = [
  { name: 'dashboard', label: 'Dashboard',  icon: LayoutDashboard },
  { name: 'plots',     label: 'Plots',      icon: Sprout },
  { name: 'tasks',     label: 'Tasks',      icon: CheckSquare },
  { name: 'diagnosis', label: 'Diagnosis',  icon: Leaf },
  { name: 'finance',   label: 'Finance',    icon: Wallet },
  { name: 'chat',      label: 'Assistant',  icon: MessageCircle },
  { name: 'admin',     label: 'Admin',      icon: Settings, platformOnly: true },
]

const visibleItems = computed(() =>
  items.filter((i) => !i.platformOnly || auth.isPlatformUser),
)
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
      'w-64 bg-card border-r border-border',
      'flex flex-col py-4 transition-transform duration-200',
      open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
    ]"
  >
    <nav class="flex flex-col gap-1 px-2">
      <router-link
        v-for="item in visibleItems"
        :key="item.name"
        :to="{ name: item.name }"
        class="flex items-center gap-3 px-3 py-2 rounded-sm text-sm
               text-muted hover:text-text hover:bg-card-hover transition-colors"
        :class="{ 'bg-accent-soft text-accent hover:bg-accent-soft': route.name === item.name }"
        @click="emit('close')"
      >
        <component :is="item.icon" :size="18" :stroke-width="1.75" />
        <span class="flex-1">{{ item.label }}</span>
        <span
          v-if="item.name === 'tasks' && tasksStore.pendingCount"
          class="px-1.5 py-0.5 rounded-full text-[10px] font-medium
                 bg-warning/15 text-warning"
        >
          {{ tasksStore.pendingCount }}
        </span>
      </router-link>
    </nav>
  </aside>
</template>