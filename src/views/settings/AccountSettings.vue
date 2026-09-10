<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const router = useRouter()

const user = computed(() => authStore.user || {})

const createdAt = computed(() => {
  const raw = user.value.created_at
  if (!raw) return null
  const parsed = new Date(raw)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString('zh-CN')
})

const roleLabel = computed(() => {
  if (user.value.role === 'admin') return '管理员'
  if (user.value.role) return '普通用户'
  return null
})

function handleLogout() {
  authStore.logout()
  router.replace('/login')
}
</script>

<template>
  <section
    class="settings-section"
    aria-label="账号"
  >
    <h2>账号</h2>
    <p class="settings-section-hint">你的登录身份与账号信息。</p>
    <dl class="account-fields">
      <div class="account-field">
        <dt>用户名</dt>
        <dd>{{ user.username || '—' }}</dd>
      </div>
      <div class="account-field">
        <dt>邮箱</dt>
        <dd>{{ user.email || '—' }}</dd>
      </div>
      <div
        v-if="createdAt"
        class="account-field"
      >
        <dt>注册时间</dt>
        <dd>{{ createdAt }}</dd>
      </div>
      <div
        v-if="roleLabel"
        class="account-field"
      >
        <dt>角色</dt>
        <dd>{{ roleLabel }}</dd>
      </div>
    </dl>
    <div class="settings-actions">
      <button
        type="button"
        class="logout-btn"
        @click="handleLogout"
      >
        退出登录
      </button>
    </div>
  </section>
</template>

<style scoped>
.settings-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  padding: var(--space-6);
  background: var(--color-surface);
}

.settings-section h2 {
  margin: 0;
  font-size: var(--text-lg);
}

.settings-section-hint {
  margin: var(--space-2) 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.account-fields {
  display: grid;
  gap: 0;
  margin: var(--space-5) 0 0;
  border-top: 1px solid var(--color-border-subtle);
}

.account-field {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.account-field dt {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.account-field dd {
  margin: 0;
  font-weight: 550;
  word-break: break-all;
  text-align: right;
}

.settings-actions {
  display: flex;
  margin-top: var(--space-6);
}

.logout-btn {
  min-height: var(--space-11);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-5);
  background: transparent;
  color: var(--color-danger);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.logout-btn:hover:not(:disabled),
.logout-btn:focus-visible:not(:disabled) {
  background: var(--color-danger-soft);
}

@media (max-width: 640px) {
  .account-field {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--space-1);
  }

  .account-field dd {
    text-align: left;
  }
}
</style>
