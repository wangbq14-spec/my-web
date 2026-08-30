<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BrandMark from '../BrandMark.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import StreamingGlyph from './StreamingGlyph.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const copyFeedback = ref('')
const sourcesExpanded = ref(false)
const assistantBody = ref(null)
const markdownRenderer = ref(null)
const glyphAnchorStyle = ref({})
let copyResetTimer = null
let glyphPositionFrame = null
let glyphResizeObserver = null

const agentStatusLabel = computed(() => {
  const { activeTool, agentStatus, isStreaming } = props.message
  if (!isStreaming || !['thinking', 'using_tool'].includes(agentStatus)) return ''
  if (activeTool === 'calculator') return '正在计算…'
  if (activeTool === 'knowledge_search') return '正在搜索资料…'
  return '正在分析…'
})

const glyphState = computed(() => {
  if (props.message.isStreaming) return agentStatusLabel.value ? 'hidden' : 'streaming'
  if (props.message.stopped) return 'stopped'
  if (props.message.error || props.message.streamError || props.message.status === 'error') return 'error'
  return 'done'
})

function sourceName(source) {
  return source.filename || '未命名文档'
}

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copyFeedback.value = '已复制'
    clearTimeout(copyResetTimer)
    copyResetTimer = setTimeout(() => {
      copyFeedback.value = ''
    }, 1800)
  } catch {
    // Clipboard access can be unavailable in non-secure contexts.
  }
}

function queueGlyphPosition() {
  if (glyphPositionFrame) {
    if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(glyphPositionFrame)
    else clearTimeout(glyphPositionFrame)
  }
  const schedule = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : setTimeout
  glyphPositionFrame = schedule(() => {
    glyphPositionFrame = null
    const body = assistantBody.value
    const markdown = markdownRenderer.value?.root
    if (!body || !markdown) return

    const bodyBox = body.getBoundingClientRect()
    const markdownBox = markdown.getBoundingClientRect()
    const fallbackPosition = {
      left: Math.max(0, markdownBox.left - bodyBox.left),
      top: Math.max(0, markdownBox.bottom - bodyBox.top + 2),
    }

    try {
      const range = document.createRange()
      range.selectNodeContents(markdown)
      range.collapse(false)
      const endBox = range.getBoundingClientRect()
      const hasEndPosition = endBox.width || endBox.height || endBox.left || endBox.top
      const inlineLeft = endBox.right - bodyBox.left + 4

      if (hasEndPosition && inlineLeft + 14 <= bodyBox.width) {
        glyphAnchorStyle.value = {
          left: `${Math.max(0, inlineLeft)}px`,
          top: `${Math.max(0, endBox.bottom - bodyBox.top - 14)}px`,
        }
        return
      }
    } catch {
      // A collapsed range is unavailable in a few non-layout test environments.
    }

    glyphAnchorStyle.value = {
      left: `${fallbackPosition.left}px`,
      top: `${fallbackPosition.top}px`,
    }
  })
}

onMounted(async () => {
  await nextTick()
  const markdown = markdownRenderer.value?.root
  if (!markdown) return

  if (typeof ResizeObserver !== 'undefined') {
    glyphResizeObserver = new ResizeObserver(queueGlyphPosition)
    glyphResizeObserver.observe(markdown)
  }
  queueGlyphPosition()
})

watch(
  () => props.message.content,
  async () => {
    await nextTick()
    queueGlyphPosition()
  },
  { flush: 'post' },
)

onBeforeUnmount(() => {
  clearTimeout(copyResetTimer)
  glyphResizeObserver?.disconnect()
  if (glyphPositionFrame) {
    if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(glyphPositionFrame)
    else clearTimeout(glyphPositionFrame)
  }
})
</script>

<template>
  <div class="assistant-message">
    <div
      class="assistant-avatar"
      :class="{ 'is-streaming': message.isStreaming }"
      aria-hidden="true"
    >
      <BrandMark />
    </div>
    <div
      ref="assistantBody"
      class="assistant-body assistant-editorial-width"
    >
      <div
        v-if="agentStatusLabel"
        class="agent-status"
        role="status"
        aria-live="polite"
      >
        {{ agentStatusLabel }}
      </div>
      <MarkdownRenderer
        ref="markdownRenderer"
        :content="message.content"
      />
      <span
        class="streaming-anchor"
        :class="`is-${glyphState}`"
        :style="glyphAnchorStyle"
        :data-streaming-anchor-state="glyphState"
        data-streaming-anchor
      >
        <StreamingGlyph :state="glyphState" />
      </span>

      <section
        v-if="(message.sources || []).length > 0"
        class="sources sources-radius-lg"
        aria-label="参考资料"
      >
        <button
          type="button"
          class="sources-toggle"
          :aria-expanded="sourcesExpanded"
          @click="sourcesExpanded = !sourcesExpanded"
        >
          <span>参考资料 · {{ message.sources.length }}</span>
          <span
            class="sources-chevron"
            aria-hidden="true"
          >
            <svg viewBox="0 0 24 24">
              <path d="m7 10 5 5 5-5" />
            </svg>
          </span>
        </button>
        <div
          v-if="sourcesExpanded"
          class="sources-list"
        >
          <article
            v-for="(source, index) in message.sources || []"
            :key="`${source.document_id}-${source.chunk_index}-${index}`"
            class="source-item source-item-radius-lg"
          >
            <p class="source-name">
              {{ sourceName(source) }}
            </p>
            <p
              v-if="source.excerpt"
              class="source-excerpt"
            >
              {{ source.excerpt }}
            </p>
            <p
              v-else
              class="source-excerpt"
            >
              暂无可展示摘录。
            </p>
          </article>
        </div>
      </section>

      <footer class="message-footer">
        <button
          type="button"
          class="copy-btn copy-touch-target"
          aria-label="复制"
          @click="copyMessage"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <rect
              x="9"
              y="9"
              width="11"
              height="11"
              rx="2"
            />
            <path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" />
          </svg>
          <span
            v-if="copyFeedback"
            class="copy-feedback"
          >{{ copyFeedback }}</span>
        </button>
        <span
          class="sr-only"
          role="status"
          aria-live="polite"
        >{{ copyFeedback }}</span>
      </footer>

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
  gap: var(--space-3);
  width: 100%;
  min-width: 0;
  animation: assistant-message-in 180ms var(--ease-standard) both;
}

@keyframes assistant-message-in {
  from {
    transform: translateY(6px);
  }

  to {
    transform: translateY(0);
  }
}

.assistant-avatar {
  width: var(--space-8);
  height: var(--space-8);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-surface-hover);
  color: var(--color-secondary-identity);
  font-size: var(--text-base);
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.assistant-avatar :deep(.brand-mark-svg) {
  width: var(--space-5);
  height: var(--space-5);
}

.assistant-body {
  position: relative;
  flex: 1;
  min-width: 0;
  max-width: 84ch;
  padding-top: var(--space-1);
}

.assistant-avatar.is-streaming {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.agent-status {
  display: flex;
  align-items: center;
  min-height: var(--space-6);
  margin-bottom: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: var(--space-6);
}

.streaming-anchor {
  position: absolute;
  z-index: 1;
  display: flex;
  width: 14px;
  height: 14px;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  transition: opacity 180ms var(--ease-standard);
}

.streaming-anchor.is-hidden {
  opacity: 0;
}

.sources {
  margin-top: var(--space-5);
  overflow: hidden;
  border: thin solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.sources-toggle {
  display: inline-flex;
  width: 100%;
  min-height: var(--space-11);
  align-items: center;
  gap: var(--space-1);
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border: 0;
  border-radius: var(--radius-lg);
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  line-height: var(--space-5);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.sources-toggle:hover,
.sources-toggle:focus-visible {
  border-color: var(--color-border-strong);
  background: var(--color-surface-hover);
  color: var(--color-accent);
  outline: none;
}

.sources-toggle:focus-visible,
.copy-btn:focus-visible {
  box-shadow: 0 0 0 var(--space-1) var(--color-focus-ring);
}

.sources-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  transition: transform var(--duration-fast) var(--ease-standard);
}

.sources-chevron svg {
  width: var(--space-4);
  height: var(--space-4);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.sources-toggle[aria-expanded='true'] .sources-chevron {
  transform: rotate(180deg);
}

.sources-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: var(--space-2);
  padding: 0 var(--space-3) var(--space-3);
}

.source-item {
  min-width: 0;
  padding: var(--space-3);
  border: thin solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-surface-hover);
}

.source-name,
.source-excerpt {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.source-name {
  color: var(--color-text-primary);
  font-weight: 600;
  line-height: var(--space-5);
}

.source-excerpt {
  display: -webkit-box;
  margin-top: var(--space-1);
  overflow: hidden;
  color: var(--color-text-secondary);
  line-height: var(--space-5);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.message-footer {
  display: flex;
  position: absolute;
  right: 0;
  bottom: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.assistant-message:hover .message-footer,
.assistant-message:focus-within .message-footer {
  opacity: 1;
  pointer-events: auto;
}

.copy-btn {
  display: inline-flex;
  min-width: var(--space-11);
  min-height: var(--space-11);
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  padding: var(--space-1);
  border: thin solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-xs);
  line-height: var(--space-4);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.copy-btn svg {
  width: var(--space-4);
  height: var(--space-4);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.copy-btn:hover,
.copy-btn:focus-visible {
  background: var(--color-surface-hover);
  color: var(--color-accent);
  outline: none;
}

.stopped-hint {
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: var(--space-5);
}

/* This remains local to the chat composition while keeping the view stylesheet untouched. */
:global(.message.user .bubble) {
  border: thin solid var(--color-border-subtle);
  background: var(--color-surface-sunken);
  color: var(--color-text-primary);
}

@media (hover: none) {
  .message-footer {
    opacity: 1;
    pointer-events: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation: none !important;
    transition: none !important;
  }

  .assistant-message {
    animation: none;
  }

  .sources-chevron,
  .sources-toggle,
  .message-footer,
  .copy-btn,
  .assistant-avatar {
    transition: none;
  }
}
</style>
