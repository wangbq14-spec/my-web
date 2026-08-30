<script setup>
import BrandMark from './BrandMark.vue'

defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'compact', 'hero'].includes(value),
  },
})
</script>

<template>
  <span
    class="brand-identity"
    :class="`is-${variant}`"
  >
    <BrandMark class="brand-symbol" />
    <span class="brand-lettering">
      <span class="brand-wordmark brand-name">Omnixa</span>
      <span class="brand-tagline">AI WORKSPACE</span>
    </span>
  </span>
</template>

<style scoped>
.brand-identity {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--color-secondary-identity);
  line-height: 1;
  white-space: nowrap;
}

.brand-symbol {
  width: 31px;
  height: 31px;
  flex: 0 0 auto;
}

.brand-lettering {
  display: grid;
  gap: 3px;
}

.brand-wordmark {
  font-family: Iowan Old Style, Baskerville, Georgia, 'Times New Roman', serif;
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.055em;
}

.brand-tagline {
  color: var(--color-text-secondary);
  font-family: var(--font-sans);
  font-size: 7px;
  font-weight: 700;
  letter-spacing: 0.3em;
}

.is-compact {
  gap: 7px;
}

.is-compact .brand-symbol {
  width: 25px;
  height: 25px;
}

.is-compact .brand-wordmark {
  font-size: 18px;
}

.is-compact .brand-tagline {
  font-size: 6px;
  letter-spacing: 0.24em;
}

.is-hero {
  flex-direction: column;
  gap: var(--space-3);
  text-align: center;
}

.is-hero .brand-symbol {
  width: 42px;
  height: 42px;
}

.is-hero .brand-lettering {
  justify-items: center;
  gap: 5px;
}

.is-hero .brand-wordmark {
  font-size: 25px;
}

.is-hero .brand-tagline {
  font-size: 8px;
  letter-spacing: 0.32em;
}

@media (max-width: 600px) {
  .brand-symbol {
    width: 28px;
    height: 28px;
  }

  .brand-wordmark {
    font-size: 20px;
  }
}
</style>
