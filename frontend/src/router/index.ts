import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../components/layout/AppShell.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard',
        component: () => import('../views/DashboardView.vue') },
      { path: 'plots', name: 'plots',
        component: () => import('../views/PlotsView.vue') },
      { path: 'plots/:id', name: 'plot-detail',
        component: () => import('../views/PlotDetailView.vue') },
      { path: 'tasks', name: 'tasks',
        component: () => import('../views/TasksView.vue') },
      { path: 'diagnosis', name: 'diagnosis',
        component: () => import('../views/DiagnosisView.vue'),
        meta: { feature: 'diagnosis' } },
      { path: 'finance', name: 'finance',
        component: () => import('../views/FinanceView.vue'),
        meta: { feature: 'finance' } },
      { path: 'chat', name: 'chat',
        component: () => import('../views/ChatView.vue'),
        meta: { feature: 'chat' } },
      { path: 'admin', name: 'admin',
        component: () => import('../views/AdminView.vue'),
        meta: { feature: 'users' } },

      // --- Platform plane (Phase 10.7) ---
      { path: 'platform', name: 'platform-dashboard',
        component: () => import('../views/platform/PlatformDashboard.vue'),
        meta: { platformOnly: true } },
      { path: 'platform/sessions', name: 'platform-sessions',
        component: () => import('../views/platform/SupportSessions.vue'),
        meta: { platformOnly: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (auth.isAuthenticated && to.name === 'login') {
      return { name: 'dashboard' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Platform-only pages require a platform user
  if (to.meta.platformOnly && !auth.isPlatformUser) {
    return { name: 'dashboard' }
  }

  // Tenant feature flags — skip when the user has no tenant (platform staff).
  // Platform users bypass feature checks because feature flags are per-tenant.
  const requiredFeature = to.meta.feature as string | undefined
  if (requiredFeature && auth.user?.tenant_id && !auth.hasFeature(requiredFeature)) {
    return { name: 'dashboard' }
  }

  return true
})

export default router