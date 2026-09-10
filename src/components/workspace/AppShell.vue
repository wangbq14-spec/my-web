<script setup>
import { storeToRefs } from 'pinia'
import { RouterView } from 'vue-router'
import { useWorkspaceStore } from '../../stores/workspace'
import WorkspaceSidebar from './WorkspaceSidebar.vue'

const workspaceStore = useWorkspaceStore()
const { drawerMode, drawerOpen } = storeToRefs(workspaceStore)
</script>

<template>
  <div class="app-shell">
    <WorkspaceSidebar />
    <div
      class="main workspace-main"
      :inert="drawerMode && drawerOpen ? '' : undefined"
    >
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  width: 100vw;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.workspace-main {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  background: var(--color-bg);
}

.workspace-main > :deep(*) {
  width: 100%;
}

@media (max-width: 768px) {
  .workspace-main {
    padding-top: var(--space-12);
  }
}
</style>
