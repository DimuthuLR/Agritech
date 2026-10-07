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

  // Public routes — always allowed
  if (to.meta.public) {
    if (auth.isAuthenticated && to.name === 'login') {
      return { name: 'dashboard' }
    }
    return true
  }

  // Otherwise require auth
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Platform-only pages require a platform user
  if (to.meta.platformOnly && !auth.isPlatformUser) {
    return { name: 'dashboard' }
  }

  // Feature-flagged routes: redirect to dashboard if the tenant
  // doesn't have this feature enabled. `hasFeature` fails open
  // pre-load, so this is safe even on the first navigation.
  const requiredFeature = to.meta.feature as string | undefined
  if (requiredFeature && !auth.hasFeature(requiredFeature)) {
    return { name: 'dashboard' }
  }

  return true
})

export default router