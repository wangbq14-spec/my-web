<script setup>
import { useRouter } from 'vue-router'
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
        智行 AI 控制台
      </span>
      <button
        type="button"
        class="logout"
        @click="handleLogout"
      >
        退出登录
      </button>
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
  background: #f6f7fb;
  color: #1a1a2e;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #eef0f4;
}

.brand {
  font-weight: 700;
  font-size: 18px;
}

.logout {
  padding: 8px 18px;
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  background: #fff;
  color: #1a1a2e;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease, background 0.2s ease;
}

.logout:hover {
  border-color: #4f46e5;
  color: #4f46e5;
  background: rgba(79, 70, 229, 0.06);
}

.content {
  flex: 1;
  width: min(720px, 100%);
  margin: 0 auto;
  padding: 40px 24px;
  box-sizing: border-box;
}

.heading {
  margin: 0 0 8px;
  font-size: 30px;
  letter-spacing: -0.5px;
}

.hint {
  margin: 0 0 32px;
  color: #6b7280;
}

.profile {
  padding: 24px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #eef0f4;
}

.profile-title {
  margin: 0 0 16px;
  font-size: 18px;
}

.list {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 12px;
  margin: 0;
}

.list dt {
  color: #6b7280;
  font-size: 14px;
}

.list dd {
  margin: 0;
  font-size: 15px;
}
</style>
