<script setup>
import { computed } from 'vue'
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
import 'highlight.js/styles/github.css'

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

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = (token.info || '').trim().split(/\s+/)[0] || 'text'
  const code = token.content.replace(/\n$/, '')
  const highlighted = hljs.getLanguage(lang)
    ? hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    : escapeHtml(code)

  return (
    '<div class="code-block">' +
    '<div class="code-toolbar">' +
    `<span class="code-lang">${escapeHtml(lang)}</span>` +
    '<button type="button" class="code-copy">Copy</button>' +
    '</div>' +
    `<pre><code class="hljs language-${escapeHtml(lang)}">${highlighted}</code></pre>` +
    '</div>'
  )
}

const renderedHtml = computed(() => {
  const raw = md.render(props.content)
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel'],
  })
})

function onRootClick(event) {
  const button = event.target.closest('.code-copy')
  if (!button) return
  const block = button.closest('.code-block')
  const code = block?.querySelector('code')?.textContent || ''

  navigator.clipboard
    ?.writeText(code)
    .then(() => {
      button.textContent = 'Copied'
      setTimeout(() => {
        button.textContent = 'Copy'
      }, 1800)
    })
    .catch(() => {
      // clipboard 失败不 alert
    })
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- 已由 markdown-it(html:false) + DOMPurify 双重消毒 -->
  <div
    class="markdown"
    @click="onRootClick"
    v-html="renderedHtml"
  />
</template>

<style scoped>
.markdown {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-primary, #1f1f23);
  word-break: break-word;
}

.markdown :deep(p) {
  margin: 0 0 12px;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 20px 0 10px;
  font-weight: 600;
  line-height: 1.4;
}

.markdown :deep(h1) {
  font-size: 1.35rem;
}

.markdown :deep(h2) {
  font-size: 1.2rem;
}

.markdown :deep(h3) {
  font-size: 1.1rem;
}

.markdown :deep(h4) {
  font-size: 1rem;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 12px;
  padding-left: 24px;
}

.markdown :deep(li) {
  margin: 4px 0;
}

.markdown :deep(blockquote) {
  margin: 0 0 12px;
  padding: 4px 0 4px 14px;
  border-left: 3px solid var(--accent, #4f46e5);
  color: var(--text-secondary, #71717a);
}

.markdown :deep(code:not(.hljs)) {
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface-hover, #f4f4f5);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.9em;
}

.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border, #e8e8ea);
  margin: 16px 0;
}

.markdown :deep(a) {
  color: var(--accent, #4f46e5);
  text-decoration: none;
}

.markdown :deep(a:hover) {
  text-decoration: underline;
}

.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0 0 12px;
  display: block;
  overflow-x: auto;
  max-width: 100%;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--border, #e8e8ea);
  padding: 8px 12px;
  text-align: left;
}

.markdown :deep(th) {
  background: var(--surface-hover, #f4f4f5);
  font-weight: 600;
}

.markdown :deep(.code-block) {
  margin: 0 0 16px;
  border: 1px solid var(--border, #e8e8ea);
  border-radius: 10px;
  overflow: hidden;
}

.markdown :deep(.code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--surface-hover, #f4f4f5);
  border-bottom: 1px solid var(--border, #e8e8ea);
}

.markdown :deep(.code-lang) {
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  text-transform: lowercase;
}

.markdown :deep(.code-copy) {
  border: 1px solid var(--border, #e8e8ea);
  border-radius: 6px;
  background: var(--surface, #ffffff);
  color: var(--text-primary, #1f1f23);
  font-size: 12px;
  padding: 3px 10px;
  cursor: pointer;
}

.markdown :deep(.code-copy:hover) {
  background: var(--surface-hover, #f4f4f5);
}

.markdown :deep(pre) {
  margin: 0;
  padding: 14px 16px;
  overflow-x: auto;
  background: #f8f8f8;
}

.markdown :deep(pre code) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre;
}
</style>
