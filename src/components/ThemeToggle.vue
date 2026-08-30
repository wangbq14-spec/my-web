<script setup>
import { onMounted, ref } from 'vue'

const theme = ref('light')

function readTheme() {
  if (typeof document === 'undefined') return 'light'
  const activeTheme = document.documentElement.dataset.theme
  if (activeTheme === 'dark' || activeTheme === 'light') return activeTheme

  try {
    return window.localStorage.getItem('omnixa-theme') === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function applyTheme(nextTheme) {
  theme.value = nextTheme
  document.documentElement.dataset.theme = nextTheme
  try {
    window.localStorage.setItem('omnixa-theme', nextTheme)
  } catch {
    // Theme preference remains available for the current session.
  }
}

function toggleTheme() {
  applyTheme(theme.value === 'light' ? 'dark' : 'light')
}

onMounted(() => applyTheme(readTheme()))
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :aria-label="theme === 'light' ? '切换到夜间模式' : '切换到白天模式'"
    :title="theme === 'light' ? '夜间模式' : '白天模式'"
    @click="toggleTheme"
  >
    <svg
      v-if="theme === 'light'"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z" />
    </svg>
    <svg
      v-else
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="3.4"
      />
      <path d="M12 2.5v2M12 19.5v2M21.5 12h-2M4.5 12h-2M18.72 5.28l-1.42 1.42M6.7 17.3l-1.42 1.42M18.72 18.72l-1.42-1.42M6.7 6.7 5.28 5.28" />
    </svg>
  </button>
</template>

<style scoped>
.theme-toggle {
  display: inline-grid;
  width: 40px;
  height: 40px;
  place-items: center;
  flex: 0 0 auto;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-surface) 74%, transparent);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-standard);
}

.theme-toggle:hover {
  border-color: var(--color-border);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.theme-toggle:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.theme-toggle svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.7;
}

@media (prefers-reduced-motion: reduce) {
  .theme-toggle {
    transition: none;
  }
}
</style>
