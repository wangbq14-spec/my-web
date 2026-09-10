<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  state: {
    type: String,
    default: 'done',
    validator: (value) => ['streaming', 'hidden', 'done', 'stopped', 'error'].includes(value),
  },
})

const visible = ref(props.state === 'streaming')
const phase = ref(props.state === 'streaming' ? 'streaming' : 'hidden')
const reducedMotion = ref(false)
let leaveTimer = null
let motionQuery = null

const leaveDelay = computed(() => (props.state === 'done' ? 200 : 100))

function clearLeaveTimer() {
  if (leaveTimer) clearTimeout(leaveTimer)
  leaveTimer = null
}

watch(
  () => props.state,
  (state) => {
    clearLeaveTimer()
    if (state === 'streaming') {
      visible.value = true
      phase.value = 'streaming'
      return
    }

    if (state === 'hidden') {
      visible.value = false
      phase.value = 'hidden'
      return
    }

    if (!visible.value) return
    phase.value = state === 'done' ? 'leaving' : 'leaving-fast'
    leaveTimer = setTimeout(() => {
      visible.value = false
      phase.value = 'hidden'
      leaveTimer = null
    }, leaveDelay.value)
  },
)

onBeforeUnmount(clearLeaveTimer)

function syncMotionPreference(event) {
  reducedMotion.value = event?.matches ?? motionQuery?.matches ?? false
}

onMounted(() => {
  if (typeof globalThis.matchMedia !== 'function') return
  motionQuery = globalThis.matchMedia('(prefers-reduced-motion: reduce)')
  syncMotionPreference()
  motionQuery.addEventListener?.('change', syncMotionPreference)
})

onBeforeUnmount(() => motionQuery?.removeEventListener?.('change', syncMotionPreference))
</script>

<template>
  <span
    v-if="visible"
    class="streaming-glyph"
    :class="[
      `is-${phase}`,
      {
        'is-inward-breathing': phase === 'streaming' && !reducedMotion,
        'is-static': reducedMotion,
      },
    ]"
    :data-state="phase"
    :data-reduced-motion="reducedMotion"
    aria-hidden="true"
  >
    <svg
      class="glyph-orbit"
      viewBox="0 0 16 16"
      focusable="false"
    >
      <path
        class="glyph-ring"
        d="M8 1.7a6.3 6.3 0 1 1-4.45 1.85"
      />
      <path
        class="glyph-accent"
        d="M3.55 3.55A6.3 6.3 0 0 1 8 1.7"
      />
      <path
        class="glyph-core"
        d="m5.3 5.3 5.4 5.4m0-5.4-5.4 5.4"
      />
    </svg>
  </span>
</template>

<style scoped>
.streaming-glyph {
  display: inline-flex;
  width: 14px;
  height: 14px;
  align-items: center;
  justify-content: center;
  color: var(--color-accent);
  opacity: 1;
  pointer-events: none;
  transform-origin: center;
  transition: opacity 200ms var(--ease-standard), transform 200ms var(--ease-standard);
}

.streaming-glyph svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.streaming-glyph path {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.streaming-glyph .glyph-ring {
  stroke-width: 1.35;
  color: var(--color-secondary-identity);
}

.streaming-glyph .glyph-accent {
  color: var(--color-accent);
  stroke-width: 1.7;
}

.streaming-glyph .glyph-core {
  stroke-width: 1.35;
}

.streaming-glyph.is-streaming {
  animation: glyph-arrive 180ms var(--ease-standard) both;
}

.streaming-glyph.is-inward-breathing .glyph-orbit {
  animation: glyph-signal 1.2s ease-in-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}

.streaming-glyph.is-leaving,
.streaming-glyph.is-leaving-fast {
  opacity: 0;
  transform: scale(0.92);
}

.streaming-glyph.is-leaving-fast {
  transition-duration: 100ms;
}

@keyframes glyph-arrive {
  from {
    opacity: 0;
    transform: scale(0.84);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes glyph-signal {
  0%,
  100% {
    opacity: 0.54;
    transform: scale(0.92);
  }

  50% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .streaming-glyph,
  .streaming-glyph.is-leaving,
  .streaming-glyph.is-leaving-fast,
  .streaming-glyph.is-inward-breathing .glyph-orbit {
    animation: none;
    transform: none;
    transition: none;
  }
}
</style>
