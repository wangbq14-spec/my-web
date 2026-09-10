import { createRouter, createWebHistory } from 'vue-router'
import pinia from '../stores'
import { useAuthStore } from '../stores/auth'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import DashboardView from '../views/DashboardView.vue'
import ChatView from '../views/ChatView.vue'
import AppShell from '../components/workspace/AppShell.vue'
import ProjectsView from '../views/ProjectsView.vue'
import ProjectDetailView from '../views/ProjectDetailView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import TasksView from '../views/TasksView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import SettingsView from '../views/SettingsView.vue'
import AdminView from '../views/AdminView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: true },
    },
    {
      path: '/',
      component: AppShell,
      meta: { requiresAuth: true },
      children: [
        { path: 'chat', name: 'chat', component: ChatView, meta: { requiresAuth: true } },
        { path: 'projects', name: 'projects', component: ProjectsView, meta: { requiresAuth: true } },
        { path: 'projects/:id', name: 'project-detail', component: ProjectDetailView, meta: { requiresAuth: true } },
        { path: 'knowledge', name: 'knowledge', component: KnowledgeView, meta: { requiresAuth: true } },
        { path: 'tasks', name: 'tasks', component: TasksView, meta: { requiresAuth: true } },
        { path: 'tasks/:id', name: 'task-detail', component: TaskDetailView, meta: { requiresAuth: true } },
        { path: 'settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
        { path: 'settings/account', name: 'settings-account', component: SettingsView, meta: { requiresAuth: true } },
        { path: 'settings/appearance', name: 'settings-appearance', component: SettingsView, meta: { requiresAuth: true } },
        { path: 'settings/usage', name: 'settings-usage', component: SettingsView, meta: { requiresAuth: true } },
        { path: 'settings/billing', name: 'settings-billing', component: SettingsView, meta: { requiresAuth: true } },
        { path: 'admin', name: 'admin', component: AdminView, meta: { requiresAuth: true, requiresAdmin: true } },
        // Legacy compatibility redirects: keep old links working.
        { path: 'usage', redirect: '/settings/usage' },
        { path: 'pricing', redirect: '/settings/billing' },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return {
      name: 'login',
      query: { redirect: to.fullPath },
    }
  }

  if ((to.name === 'login' || to.name === 'register') && authStore.isAuthenticated) {
    return { name: 'chat' }
  }

  if (to.meta.requiresAdmin) {
    if (!authStore.user && authStore.isAuthenticated) {
      try {
        await authStore.fetchCurrentUser()
      } catch {
        // Token invalid; the API layer already cleared it and redirected.
      }
    }
    if (authStore.user?.role !== 'admin') {
      return { name: 'chat' }
    }
  }

  return true
})

export default router
