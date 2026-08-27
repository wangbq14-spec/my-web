
<script setup>
import { RouterLink } from 'vue-router'

const features = [
  {
    icon: '💬',
    title: '自然对话',
    desc: '像与人交流一样与 AI 对话，理解上下文，回答自然流畅。',
  },
  {
    icon: '🧠',
    title: '深度思考',
    desc: '多轮推理与知识整合，帮你分析问题、生成完整方案。',
  },
  {
    icon: '⚡',
    title: '极速响应',
    desc: '毫秒级流式输出，让灵感与效率都不被打断。',
  },
]
</script>
<template>
  <div class="page">
    <header class="nav">
      <a
        class="logo"
        href="#hero"
      >✨ 智行 AI</a>
      <nav class="links">
        <a href="#hero">首页</a>
        <a href="#features">功能</a>
        <a href="#about">关于</a>
      </nav>
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
          to="/dashboard"
          class="btn btn-primary"
        >
          开始体验
        </RouterLink>
        <a
          href="#features"
          class="btn btn-ghost"
        >了解更多</a>
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
            {{ f.icon }}
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
      <p>© 2025 智行 AI · 让智能触手可及</p>
    </footer>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(60rem 30rem at 70% -10%, rgba(124, 58, 237, 0.12), transparent 60%),
    radial-gradient(50rem 28rem at 15% 0%, rgba(79, 70, 229, 0.12), transparent 60%),
    #ffffff;
  color: #1a1a2e;
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
  animation: fadeInDown 0.6s ease both;
}

.logo {
  font-weight: 700;
  font-size: 20px;
  color: #1a1a2e;
  text-decoration: none;
  transition: transform 0.3s ease;
}
.logo:hover {
  transform: scale(1.05);
}

.links {
  display: flex;
  gap: 28px;
  margin-left: auto;
}
.links a {
  color: #4b5563;
  text-decoration: none;
  font-size: 15px;
  position: relative;
  transition: color 0.3s ease;
}
.links a::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: -6px;
  width: 0;
  height: 2px;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  transition: width 0.3s ease;
}
.links a:hover {
  color: #1a1a2e;
}
.links a:hover::after {
  width: 100%;
}

.nav-cta {
  margin-left: 16px;
  padding: 8px 20px;
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  color: #1a1a2e;
  text-decoration: none;
  font-size: 14px;
  transition: border-color 0.3s ease, color 0.3s ease, background 0.3s ease;
}
.nav-cta:hover {
  border-color: #4f46e5;
  color: #4f46e5;
  background: rgba(79, 70, 229, 0.06);
}

/* ---- Hero ---- */
.hero {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 72px 24px 56px;
}

.badge {
  display: inline-block;
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13px;
  color: #4f46e5;
  background: rgba(79, 70, 229, 0.08);
  border: 1px solid rgba(79, 70, 229, 0.2);
  animation: fadeInUp 0.6s 0.05s ease both;
}

h1 {
  margin: 24px 0 16px;
  font-size: 56px;
  line-height: 1.15;
  letter-spacing: -1.5px;
  animation: fadeInUp 0.6s 0.15s ease both;
}
.gradient {
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  color: #6b7280;
  font-size: 18px;
  line-height: 1.7;
  animation: fadeInUp 0.6s 0.25s ease both;
}

.actions {
  display: flex;
  gap: 16px;
  margin-top: 32px;
  animation: fadeInUp 0.6s 0.35s ease both;
}

.btn {
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  font-size: 16px;
  border-radius: 12px;
  padding: 14px 32px;
  font-family: inherit;
  transition: transform 0.3s ease, box-shadow 0.3s ease, background 0.3s ease,
    border-color 0.3s ease, color 0.3s ease;
}
.btn-primary {
  color: #fff;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  box-shadow: 0 10px 24px -8px rgba(79, 70, 229, 0.5);
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 32px -8px rgba(79, 70, 229, 0.6);
}
.btn-ghost {
  color: #1a1a2e;
  background: transparent;
  border: 1px solid #e5e7eb;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.btn-ghost:hover {
  border-color: #4f46e5;
  color: #4f46e5;
  transform: translateY(-2px);
}

/* ---- 对话预览卡片 ---- */
.chat-preview {
  margin-top: 56px;
  width: min(460px, 100%);
  padding: 24px;
  border-radius: 20px;
  background: #fff;
  border: 1px solid #eef0f4;
  box-shadow: 0 24px 60px -24px rgba(30, 30, 60, 0.25);
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: left;
  animation: fadeInUp 0.6s 0.45s ease both;
}
.msg {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.5;
}
.msg.user {
  align-self: flex-end;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg.ai {
  align-self: flex-start;
  background: #f4f5f9;
  color: #1a1a2e;
  border-bottom-left-radius: 4px;
}

/* ---- 功能卡片 ---- */
.features {
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 24px 72px;
  text-align: center;
}
.features h2 {
  font-size: 32px;
  margin: 0 0 8px;
  letter-spacing: -0.5px;
}
.lead {
  color: #6b7280;
  margin: 0 0 40px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}
.card {
  padding: 32px 24px;
  border-radius: 18px;
  background: #fff;
  border: 1px solid #eef0f4;
  text-align: left;
  transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
}
.card:hover {
  transform: translateY(-6px);
  border-color: rgba(79, 70, 229, 0.35);
  box-shadow: 0 24px 48px -24px rgba(30, 30, 60, 0.3);
}
.icon {
  font-size: 30px;
  margin-bottom: 16px;
}
.card h3 {
  margin: 0 0 8px;
  font-size: 18px;
}
.card p {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.6;
}

/* ---- 页脚 ---- */
.footer {
  border-top: 1px solid #eef0f4;
  padding: 24px;
  text-align: center;
  color: #9ca3af;
  font-size: 14px;
}

/* ---- 动画 ---- */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .nav {
    padding: 16px 20px;
    gap: 12px;
  }
  .links {
    display: none;
  }
  h1 {
    font-size: 38px;
  }
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
