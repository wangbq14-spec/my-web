<script setup>
import { computed, ref } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import sql from 'highlight.js/lib/languages/sql'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('sql', sql)

const props = defineProps({
  content: { type: String, required: true },
})

const emojiPattern = /(?:[\u{1F1E6}-\u{1F1FF}]|[\u{1F300}-\u{1FAFF}]|[\u{2600}-\u{27BF}]\uFE0F?|\uFE0F|\u200D)/gu

const root = ref(null)
defineExpose({ root })

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
})

const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

const defaultTableOpen =
  md.renderer.rules.table_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
const defaultTableClose =
  md.renderer.rules.table_close ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.table_open = (tokens, idx, options, env, self) =>
  '<div class="table-scroll" role="region" tabindex="0" aria-label="表格，可横向滚动">' +
  '<span class="table-scroll-hint" aria-hidden="true">可横向滚动</span>' +
  defaultTableOpen(tokens, idx, options, env, self)
md.renderer.rules.table_close = (tokens, idx, options, env, self) =>
  defaultTableClose(tokens, idx, options, env, self) + '</div>'

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = (token.info || '').trim().split(/\s+/)[0] || 'text'
  const code = token.content.replace(/\n$/, '')
  const highlighted = hljs.getLanguage(lang)
    ? hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    : escapeHtml(code)

  return (
    '<div class="code-block code-block-surface code-block-radius-lg">' +
    '<div class="code-toolbar">' +
    `<span class="code-lang">${escapeHtml(lang)}</span>` +
    '<button type="button" class="code-copy code-copy-touch-target code-copy-radius-sm" aria-label="复制代码">复制</button>' +
    '<span class="code-copy-status" role="status" aria-live="polite" aria-atomic="true"></span>' +
    '</div>' +
    `<pre><code class="hljs language-${escapeHtml(lang)}">${highlighted}</code></pre>` +
    '</div>'
  )
}

const renderedHtml = computed(() => {
  const raw = md.render(props.content.replace(emojiPattern, ''))
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel'],
  })
})

function onRootClick(event) {
  const button = event.target.closest('.code-copy')
  if (!button) return
  const block = button.closest('.code-block')
  const code = block?.querySelector('code')?.textContent || ''
  const status = block?.querySelector('.code-copy-status')

  navigator.clipboard
    ?.writeText(code)
    .then(() => {
      button.textContent = '已复制'
      if (status) status.textContent = '代码已复制'
      setTimeout(() => {
        button.textContent = '复制'
        if (status) status.textContent = ''
      }, 1800)
    })
    .catch(() => {
      // Clipboard failures do not interrupt reading.
    })
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- 已由 markdown-it(html:false) + DOMPurify 双重消毒 -->
  <div
    ref="root"
    class="markdown reading-prose"
    @click="onRootClick"
    v-html="renderedHtml"
  />
</template>

<style scoped>
.markdown {
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: var(--text-md);
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.markdown :deep(p) {
  margin: 0 0 var(--space-5);
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: var(--space-8) 0 var(--space-3);
  color: var(--color-text-primary);
  font-weight: 650;
  line-height: 1.35;
}

.markdown :deep(h1) {
  font-size: var(--text-2xl);
}

.markdown :deep(h2) {
  font-size: var(--text-lg);
}

.markdown :deep(h3) {
  font-size: var(--text-base);
}

.markdown :deep(h4) {
  font-size: var(--text-sm);
}

.markdown :deep(h1:first-child),
.markdown :deep(h2:first-child),
.markdown :deep(h3:first-child),
.markdown :deep(h4:first-child) {
  margin-top: 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 var(--space-4);
  padding-left: var(--space-7);
}

.markdown :deep(li) {
  margin: var(--space-2) 0;
  padding-left: var(--space-1);
}

.markdown :deep(li > ul),
.markdown :deep(li > ol) {
  margin: var(--space-2) 0 0;
}

.markdown :deep(blockquote) {
  margin: 0 0 var(--space-4);
  padding: var(--space-1) 0 var(--space-1) var(--space-3);
  border-left: thin solid var(--color-border-strong);
  color: var(--color-text-secondary);
}

.markdown :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 650;
}

.markdown :deep(code:not(.hljs)) {
  padding: 0 var(--space-1);
  border-radius: var(--radius-xs);
  background: var(--color-surface-sunken);
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: 0.9em;
}

.markdown :deep(hr) {
  margin: var(--space-5) 0;
  border: 0;
  border-top: thin solid var(--color-border-subtle);
}

.markdown :deep(a) {
  color: var(--color-accent);
  text-decoration-line: underline;
  text-decoration-color: var(--color-accent-soft);
  text-decoration-thickness: thin;
  text-underline-offset: var(--space-1);
  transition: color var(--duration-fast) var(--ease-standard), text-decoration-color var(--duration-fast) var(--ease-standard);
}

.markdown :deep(a:hover),
.markdown :deep(a:focus-visible) {
  color: var(--color-accent-hover);
  text-decoration-color: currentColor;
}

.markdown :deep(a:focus-visible) {
  outline: none;
  box-shadow: 0 0 0 var(--space-1) var(--color-focus-ring);
}

.markdown :deep(.table-scroll) {
  position: relative;
  max-width: 100%;
  margin: 0 0 var(--space-3);
  padding-bottom: var(--space-5);
  overflow-x: auto;
  border: thin solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.markdown :deep(.table-scroll::after) {
  position: absolute;
  top: 0;
  right: 0;
  bottom: var(--space-5);
  width: var(--space-6);
  background: linear-gradient(to right, transparent, var(--color-surface));
  content: '';
  pointer-events: none;
}

.markdown :deep(.table-scroll-hint) {
  position: absolute;
  right: var(--space-2);
  bottom: var(--space-1);
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  line-height: var(--space-4);
  pointer-events: none;
}

.markdown :deep(.table-scroll:focus-visible) {
  outline: none;
  box-shadow: 0 0 0 var(--space-1) var(--color-focus-ring);
}

.markdown :deep(table) {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
}

.markdown :deep(th),
.markdown :deep(td) {
  padding: var(--space-2) var(--space-3);
  border-bottom: thin solid var(--color-border-subtle);
  color: var(--color-text-primary);
  text-align: left;
  vertical-align: top;
}

.markdown :deep(th) {
  background: var(--color-surface-hover);
  font-weight: 650;
}

.markdown :deep(tr:last-child td) {
  border-bottom: 0;
}

.markdown :deep(.code-block) {
  margin: 0 0 var(--space-4);
  overflow: hidden;
  border: thin solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-surface-hover);
}

.markdown :deep(.code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  border-bottom: thin solid var(--color-border-subtle);
}

.markdown :deep(.code-lang) {
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--space-4);
  text-transform: lowercase;
}

.markdown :deep(.code-copy) {
  min-width: var(--space-11);
  min-height: var(--space-11);
  padding: var(--space-1) var(--space-2);
  border: thin solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-xs);
  line-height: var(--space-4);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.markdown :deep(.code-copy:hover),
.markdown :deep(.code-copy:focus-visible) {
  border-color: var(--color-border-strong);
  background: var(--color-surface-hover);
  color: var(--color-accent);
  outline: none;
}

.markdown :deep(.code-copy:focus-visible) {
  box-shadow: 0 0 0 var(--space-1) var(--color-focus-ring);
}

.markdown :deep(.code-copy-status) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.markdown :deep(pre) {
  margin: 0;
  padding: var(--space-4);
  overflow-x: auto;
  background: transparent;
}

.markdown :deep(pre code) {
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: var(--space-6);
  white-space: pre;
}

.markdown :deep(.hljs) {
  color: var(--color-text-primary);
  background: transparent;
}

.markdown :deep(.hljs-comment),
.markdown :deep(.hljs-quote) {
  color: var(--color-text-tertiary);
}

.markdown :deep(.hljs-keyword),
.markdown :deep(.hljs-selector-tag),
.markdown :deep(.hljs-literal),
.markdown :deep(.hljs-built_in),
.markdown :deep(.hljs-type) {
  color: var(--color-text-secondary);
  font-weight: 600;
}

.markdown :deep(.hljs-string),
.markdown :deep(.hljs-number),
.markdown :deep(.hljs-attr),
.markdown :deep(.hljs-attribute),
.markdown :deep(.hljs-meta) {
  color: var(--color-text-secondary);
}

.markdown :deep(.hljs-title),
.markdown :deep(.hljs-function),
.markdown :deep(.hljs-params),
.markdown :deep(.hljs-variable),
.markdown :deep(.hljs-property) {
  color: var(--color-text-primary);
}

.markdown :deep(img) {
  display: block;
  max-width: 100%;
  height: auto;
  margin: var(--space-3) 0;
  border-radius: var(--radius-md);
}

@media (prefers-reduced-motion: reduce) {
  .markdown :deep(a),
  .markdown :deep(.code-copy) {
    transition: none;
  }
}
</style>
