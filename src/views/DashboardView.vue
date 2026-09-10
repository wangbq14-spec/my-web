<script setup>
import { useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

function handleLogout() {
  authStore.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="dashboard-page">
    <header class="topbar">
      <span class="brand">
        <BrandIdentity variant="compact" />
      </span>
      <div class="topbar-actions">
        <ThemeToggle />
        <button
          type="button"
          class="logout"
          @click="handleLogout"
        >
          退出登录
        </button>
      </div>
    </header>

    <main class="content">
      <h1 class="heading">
        欢迎回来
      </h1>
      <p class="hint">
        这是受保护页面，只有登录后才能访问。
      </p>

      <section class="profile">
        <h2 class="profile-title">
          当前用户
        </h2>
        <dl class="list">
          <dt>用户名</dt>
          <dd>{{ authStore.user?.username ?? '—' }}</dd>
          <dt>邮箱</dt>
          <dd>{{ authStore.user?.email ?? '—' }}</dd>
        </dl>
      </section>
    </main>
  </div>
</template>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border-subtle);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  font-size: var(--text-md);
}


.logout {
  min-width: 44px;
  min-height: 44px;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);
}

.logout:hover {
  border-color: var(--color-border-strong);
  color: var(--color-accent);
  background: var(--color-surface-hover);
}

.content {
  flex: 1;
  width: min(720px, 100%);
  margin: 0 auto;
  padding: var(--space-10) var(--space-6);
  box-sizing: border-box;
}

.heading {
  margin: 0 0 8px;
  font-size: var(--text-page-title);
  letter-spacing: -0.5px;
}

.hint {
  margin: 0 0 32px;
  color: var(--color-text-secondary);
}

.profile {
  padding: var(--space-6);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  border: 1px solid var(--color-border-subtle);
}

.profile-title {
  margin: 0 0 16px;
  font-size: var(--text-section-title);
}

.list {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 12px;
  margin: 0;
}

.list dt {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.list dd {
  margin: 0;
  font-size: var(--text-base);
}
</style>
