<script setup>
import { onMounted, ref } from 'vue'
import { applyTheme, readTheme } from '../../utils/theme'

const theme = ref('light')

function chooseTheme(nextTheme) {
  theme.value = applyTheme(nextTheme)
}

onMounted(() => {
  theme.value = applyTheme(readTheme())
})
</script>

<template>
  <section
    class="settings-section"
    aria-label="外观"
  >
    <h2>外观</h2>
    <p class="settings-section-hint">选择界面主题。切换会立即生效并保存到本机。</p>
    <div
      class="theme-options"
      role="radiogroup"
      aria-label="主题"
    >
      <button
        type="button"
        class="theme-option"
        :class="{ active: theme === 'light' }"
        role="radio"
        :aria-checked="theme === 'light' ? 'true' : 'false'"
        @click="chooseTheme('light')"
      >
        <span
          class="theme-swatch theme-swatch-light"
          aria-hidden="true"
        />
        <span class="theme-option-label">浅色</span>
      </button>
      <button
        type="button"
        class="theme-option"
        :class="{ active: theme === 'dark' }"
        role="radio"
        :aria-checked="theme === 'dark' ? 'true' : 'false'"
        @click="chooseTheme('dark')"
      >
        <span
          class="theme-swatch theme-swatch-dark"
          aria-hidden="true"
        />
        <span class="theme-option-label">深色</span>
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

.theme-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-5);
}

.theme-option {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-3);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);
}

.theme-option:hover,
.theme-option:focus-visible {
  border-color: var(--color-border);
  background: var(--color-surface-hover);
}

.theme-option.active {
  border-color: color-mix(in srgb, var(--color-accent) 60%, var(--color-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 40%, transparent);
}

.theme-option:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.theme-swatch {
  display: block;
  width: var(--space-9);
  height: var(--space-9);
  flex: 0 0 auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.theme-swatch-light {
  background: #f6f5f2;
}

.theme-swatch-dark {
  background: #23262d;
}

.theme-option-label {
  font-weight: 550;
}

@media (max-width: 480px) {
  .theme-options {
    grid-template-columns: 1fr;
  }
}
</style>
