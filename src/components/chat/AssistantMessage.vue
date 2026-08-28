<script setup>
import { onBeforeUnmount, ref } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const copyLabel = ref('Copy')
let copyResetTimer = null

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copyLabel.value = 'Copied'
    clearTimeout(copyResetTimer)
    copyResetTimer = setTimeout(() => {
      copyLabel.value = 'Copy'
    }, 1800)
  } catch {
    // Clipboard access can be unavailable in non-secure contexts.
  }
}

onBeforeUnmount(() => clearTimeout(copyResetTimer))
</script>

<template>
  <div class="assistant-message">
    <div
      class="assistant-avatar"
      aria-hidden="true"
    >
      ✦
    </div>
    <div class="assistant-body">
      <MarkdownRenderer :content="message.content" />
      <span
        v-if="message.isStreaming"
        class="caret"
      />
      <button
        v-if="!message.isStreaming"
        type="button"
        class="copy-btn"
        aria-label="复制"
        @click="copyMessage"
      >
        {{ copyLabel }}
      </button>
      <div
        v-if="message.stopped"
        class="stopped-hint"
      >
        已停止生成 · 本轮未保存
      </div>
    </div>
  </div>
</template>

<style scoped>
.assistant-message {
  display: flex;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.assistant-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--accent-soft, rgba(79, 70, 229, 0.08));
  color: var(--accent, #4f46e5);
  font-size: 15px;
}

.assistant-body {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}

.caret {
  display: inline-block;
  width: 8px;
  height: 16px;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--accent, #4f46e5);
  animation: blink 1s steps(1) infinite;
}

.stopped-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
}

.copy-btn {
  margin-top: 8px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-secondary, #71717a);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.copy-btn:hover,
.copy-btn:focus-visible {
  color: var(--accent, #4f46e5);
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
