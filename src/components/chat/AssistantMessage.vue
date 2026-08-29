<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const copyLabel = ref('Copy')
const expandedSourceIndexes = ref(new Set())
let copyResetTimer = null

const agentStatusLabel = computed(() => {
  if (!props.message.agentStatus) return ''
  if (props.message.activeTool === 'calculator') return '⌕ 正在计算…'
  if (props.message.activeTool === 'knowledge_search') return '⌕ 正在搜索知识库…'
  if (props.message.activeTool) return '正在使用工具…'
  return '✦ 正在分析…'
})

function toggleSource(index) {
  const next = new Set(expandedSourceIndexes.value)
  if (next.has(index)) {
    next.delete(index)
  } else {
    next.add(index)
  }
  expandedSourceIndexes.value = next
}

function formatScore(score) {
  const value = Number(score)
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : ''
}

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
      <div
        v-if="agentStatusLabel"
        class="agent-status"
      >
        {{ agentStatusLabel }}
      </div>
      <MarkdownRenderer :content="message.content" />
      <section
        v-if="(message.sources || []).length > 0"
        class="sources"
        aria-label="Sources"
      >
        <div class="sources-title">
          Sources
        </div>
        <div
          v-for="(source, index) in message.sources || []"
          :key="`${source.document_id}-${source.chunk_index}-${index}`"
          class="source-item"
        >
          <button
            type="button"
            class="source-toggle"
            :aria-expanded="expandedSourceIndexes.has(index)"
            :aria-controls="`source-detail-${index}`"
            @click="toggleSource(index)"
          >
            <span>{{ index + 1 }}. {{ source.filename || 'Unknown document' }} · Chunk {{ source.chunk_index ?? 0 }}</span>
            <span aria-hidden="true">⌄</span>
          </button>
          <div
            v-if="expandedSourceIndexes.has(index)"
            :id="`source-detail-${index}`"
            class="source-detail"
          >
            <p>{{ source.excerpt || 'No excerpt available.' }}</p>
            <span v-if="formatScore(source.score)">Score {{ formatScore(source.score) }}</span>
          </div>
        </div>
      </section>
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

.agent-status {
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
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

.sources {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
}

.sources-title {
  margin-bottom: 4px;
  font-weight: 600;
}

.source-item {
  border-top: 1px solid var(--border, #e8e8ea);
}

.source-toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.source-toggle:hover,
.source-toggle:focus-visible {
  color: var(--accent, #4f46e5);
}

.source-detail {
  margin: -1px 0 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--surface-hover, #f4f4f5);
  overflow-wrap: anywhere;
}

.source-detail p {
  margin: 0 0 4px;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
