<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AccountSettings from './settings/AccountSettings.vue'
import AppearanceSettings from './settings/AppearanceSettings.vue'
import PricingView from './PricingView.vue'
import UsageView from './UsageView.vue'

const route = useRoute()
const router = useRouter()

const TABS = [
  { key: 'account', label: '账号', path: '/settings/account' },
  { key: 'appearance', label: '外观', path: '/settings/appearance' },
  { key: 'usage', label: '用量', path: '/settings/usage' },
  { key: 'billing', label: '定价与充值', path: '/settings/billing' },
]

const tab = computed(() => {
  const name = route.name
  if (name === 'settings-appearance') return 'appearance'
  if (name === 'settings-usage') return 'usage'
  if (name === 'settings-billing') return 'billing'
  return 'account'
})

function go(path) {
  if (route.path !== path) router.push(path)
}
</script>

<template>
  <main class="settings-page">
    <div class="settings-inner">
      <header class="settings-header">
        <h1>设置</h1>
        <p>管理你的账号、外观、用量与充值。</p>
      </header>
      <nav
        class="settings-tabs"
        aria-label="设置分类"
      >
        <button
          v-for="item in TABS"
          :key="item.key"
          type="button"
          class="settings-tab"
          :class="{ active: tab === item.key }"
          :aria-current="tab === item.key ? 'page' : undefined"
          @click="go(item.path)"
        >
          {{ item.label }}
        </button>
      </nav>
      <div class="settings-content">
        <AccountSettings v-if="tab === 'account'" />
        <AppearanceSettings v-else-if="tab === 'appearance'" />
        <UsageView v-else-if="tab === 'usage'" />
        <PricingView v-else-if="tab === 'billing'" />
      </div>
    </div>
  </main>
</template>

<style scoped>
.settings-page {
  min-height: 100%;
  padding: var(--space-8) var(--space-5) var(--space-12);
  color: var(--color-text-primary);
}

.settings-inner {
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
}

.settings-header h1 {
  margin: 0;
  font-size: 1.5rem;
}

.settings-header p {
  margin: var(--space-2) 0 0;
  color: var(--color-text-secondary);
}

.settings-tabs {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-6);
  border-bottom: 1px solid var(--color-border-subtle);
  overflow-x: auto;
  scrollbar-width: none;
}

.settings-tabs::-webkit-scrollbar {
  display: none;
}

.settings-tab {
  flex: 0 0 auto;
  min-height: var(--space-11);
  border: 0;
  border-bottom: 2px solid transparent;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.settings-tab:hover,
.settings-tab:focus-visible {
  color: var(--color-text-primary);
}

.settings-tab:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: -2px;
  border-radius: var(--radius-md);
}

.settings-tab.active {
  border-bottom-color: var(--color-accent);
  color: var(--color-text-primary);
  font-weight: 600;
}

.settings-content {
  width: 100%;
  min-width: 0;
  margin-top: var(--space-6);
}

@media (max-width: 640px) {
  .settings-page {
    padding: var(--space-6) var(--space-4) var(--space-10);
  }
}
</style>
