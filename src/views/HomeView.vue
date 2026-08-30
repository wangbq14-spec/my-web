
<script setup>
import { RouterLink } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'

const features = [
  {
    icon: 'chat',
    title: '智能对话',
    desc: '提问、写作、分析，直接对话协作。',
  },
  {
    icon: 'knowledge',
    title: '使用资料',
    desc: '从你添加的资料中查找依据并标出来源。',
  },
  {
    icon: 'agent',
    title: 'Agent',
    desc: '把目标拆成步骤，交付可执行建议。',
  },
]
</script>
<template>
  <div class="page">
    <header class="nav">
      <a
        class="logo"
        href="#hero"
      >
        <BrandIdentity variant="compact" />
      </a>
      <nav class="links">
        <a href="#hero">首页</a>
        <a href="#features">功能</a>
        <a href="#about">关于</a>
      </nav>
      <ThemeToggle />
      <RouterLink
        class="nav-cta"
        to="/login"
      >
        登录
      </RouterLink>
    </header>

    <section
      id="hero"
      class="hero"
    >
      <span class="badge">新一代智能助手</span>
      <h1>让 AI 成为你的<br><span class="gradient">得力伙伴</span></h1>
      <p class="subtitle">
        简单对话，即可获得写作、编程、分析与创作的全能支持。<br>
        让智能真正融入你的每一次思考。
      </p>
      <div class="actions">
        <RouterLink
          id="start"
          to="/register"
          class="btn btn-primary"
        >
          开始使用
        </RouterLink>
        <RouterLink
          to="/login"
          class="btn btn-ghost"
        >
          登录
        </RouterLink>
      </div>

      <div
        id="experience"
        class="chat-preview"
      >
        <div class="msg user">
          帮我写一段产品介绍
        </div>
        <div class="msg ai">
          好的，这是为您准备的内容 ——
        </div>
      </div>
    </section>

    <section
      id="features"
      class="features"
    >
      <h2>核心能力</h2>
      <p class="lead">
        一个入口，解锁创作与思考的无限可能。
      </p>
      <div class="grid">
        <div
          v-for="f in features"
          :key="f.title"
          class="card"
        >
          <div class="icon">
            <svg
              v-if="f.icon === 'chat'"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v5a3.5 3.5 0 0 1-3.5 3.5H10l-4.5 3v-3.8A3.5 3.5 0 0 1 5 11.5z" />
            </svg>
            <svg
              v-else-if="f.icon === 'knowledge'"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M6 3.5h8.5L18 7v13.5H6zM14 3.5V7h4M9 11h6M9 14h6M9 17h4" />
            </svg>
            <svg
              v-else
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z" />
            </svg>
          </div>
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
        </div>
      </div>
    </section>

    <footer
      id="about"
      class="footer"
    >
      <p>© 2025 Omnixa · 让智能触手可及</p>
    </footer>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

/* ---- 顶部导航 ---- */
.nav {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 20px 48px;
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
  animation: fadeInDown var(--duration-normal) var(--ease-standard) both;
}

.logo {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  font-size: var(--text-md);
  color: var(--color-text-primary);
  text-decoration: none;
  transition: transform var(--duration-fast) var(--ease-standard);
}
.logo:hover {
  transform: translateY(-2px);
}

.links {
  display: flex;
  gap: var(--space-7);
  margin-left: auto;
}
.links a {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: var(--text-base);
  position: relative;
  transition: color var(--duration-fast) var(--ease-standard);
}
.links a::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: calc(var(--space-1) * -1.5);
  width: 0;
  height: 2px;
  background: var(--color-accent);
  transition: width var(--duration-fast) var(--ease-standard);
}
.links a:hover {
  color: var(--color-text-primary);
}
.links a:hover::after {
  width: 100%;
}

.nav-cta {
  margin-left: var(--space-4);
  padding: var(--space-2) var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  color: var(--color-text-primary);
  text-decoration: none;
  font-size: var(--text-sm);
  transition: border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);
}
.nav-cta:hover {
  border-color: var(--color-border-strong);
  color: var(--color-accent);
  background: var(--color-surface-hover);
}

/* ---- Hero ---- */
.hero {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: var(--space-14) var(--space-6) var(--space-13);
}

.badge {
  display: inline-block;
  padding: var(--space-1) var(--space-4);
  border-radius: var(--radius-pill);
  font-size: var(--text-sm);
  color: var(--color-accent);
  background: var(--color-accent-soft);
  border: 1px solid color-mix(in srgb, var(--color-accent) 28%, transparent);
}

h1 {
  margin: var(--space-6) 0 var(--space-4);
  font-size: var(--text-display);
  line-height: 1.15;
  letter-spacing: -0.75px;
}
.gradient {
  color: var(--color-accent);
}

.subtitle {
  color: var(--color-text-secondary);
  font-size: var(--text-lg);
  line-height: 1.7;
}

.actions {
  display: flex;
  gap: var(--space-4);
  margin-top: var(--space-8);
}

.btn {
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  font-size: var(--text-md);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-8);
  font-family: inherit;
  transition: transform var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}
.btn-primary {
  color: var(--color-action-text);
  background: var(--color-action);
  box-shadow: var(--shadow-float);
}
.btn-primary:hover {
  transform: translateY(-2px);
  background: var(--color-action-hover);
  box-shadow: var(--shadow-float);
}
.btn-ghost {
  color: var(--color-text-primary);
  background: transparent;
  border: 1px solid var(--color-border);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.btn-ghost:hover {
  border-color: var(--color-border-strong);
  color: var(--color-accent);
  background: var(--color-surface-hover);
  transform: translateY(-2px);
}

/* ---- 对话预览卡片 ---- */
.chat-preview {
  margin-top: var(--space-13);
  width: min(460px, 100%);
  padding: var(--space-6);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-float);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  text-align: left;
}
.msg {
  max-width: 82%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  line-height: 1.5;
}
.msg.user {
  align-self: flex-end;
  background: var(--color-user-message);
  color: var(--color-text-primary);
  border-bottom-right-radius: var(--radius-xs);
}
.msg.ai {
  align-self: flex-start;
  background: var(--color-surface-sunken);
  color: var(--color-text-primary);
  border-bottom-left-radius: var(--radius-xs);
}

/* ---- 功能卡片 ---- */
.features {
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
  padding: var(--space-12) var(--space-6) var(--space-14);
  text-align: center;
}
.features h2 {
  font-size: var(--text-page-title);
  margin: 0 0 8px;
  letter-spacing: -0.5px;
}
.lead {
  color: var(--color-text-secondary);
  margin: 0 0 var(--space-10);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-6);
}
.card {
  padding: var(--space-8) var(--space-6);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  border: 1px solid var(--color-border-subtle);
  text-align: left;
  transition: transform var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}
.card:hover {
  transform: translateY(-4px);
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-float);
}
.icon {
  display: grid;
  width: var(--space-6);
  height: var(--space-6);
  place-items: center;
  margin-bottom: var(--space-4);
  color: var(--color-accent);
}
.icon svg {
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}
.card h3 {
  margin: 0 0 var(--space-2);
  font-size: var(--text-section-title);
}
.card p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.6;
}

/* ---- 页脚 ---- */
.footer {
  border-top: 1px solid var(--color-border-subtle);
  padding: var(--space-6);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

/* ---- 动画 ---- */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .nav {
    padding: var(--space-4) var(--space-5);
    gap: var(--space-3);
  }
  .links {
    display: none;
  }
  h1 {
    font-size: var(--text-page-title);
  }
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
