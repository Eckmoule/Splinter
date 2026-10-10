<script setup>
// Coquille de l'application : en-tête, menu des pages, routage par ancre (#/page).
import { computed, onBeforeUnmount, onMounted, provide, ref } from 'vue'
import SyncStatus from './components/SyncStatus.vue'
import NavMenu from './kit/components/NavMenu.vue'
import Progression from './views/Progression.vue'
import Training from './views/Training.vue'

const routes = [
  { path: '/', label: 'Progression', component: Progression },
  { path: '/entrainement', label: 'Entraînement', component: Training },
]

const hash = () => window.location.hash.replace(/^#/, '') || '/'
const current = ref(hash())
const onHash = () => (current.value = hash())
onMounted(() => window.addEventListener('hashchange', onHash))
onBeforeUnmount(() => window.removeEventListener('hashchange', onHash))

const route = computed(() => routes.find((r) => r.path === current.value) ?? routes[0])

// incrémenté après une synchro réussie : les pages rechargent leurs données
const dataVersion = ref(0)
provide('dataVersion', dataVersion)
</script>

<template>
  <header class="topbar">
    <NavMenu :routes="routes" :current="route.path" />
    <span class="brand">Splinter</span>
    <span class="muted">{{ route.label }}</span>
    <SyncStatus @updated="dataVersion++" />
  </header>
  <main>
    <component :is="route.component" />
  </main>
</template>

<style scoped>
.topbar {
  max-width: 1180px;
  margin: 0 auto;
  padding: 16px 16px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand { font-weight: 600; font-size: 16px; }
</style>
