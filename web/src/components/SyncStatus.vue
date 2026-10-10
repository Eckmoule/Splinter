<script setup>
// Indicateur de fraîcheur des données + bouton de mise à jour (récupération Garmin et export Drive).
// Pendant une synchro, l'état est relu toutes les 3 s ; à la fin, l'événement `updated` permet aux
// pages de recharger leurs données.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { MONTHS } from '../kit/lib/format'

const emit = defineEmits(['updated'])
const POLL_MS = 3000

const status = ref(null)
const error = ref('')
let timer = null

const when = (iso) => {
  if (!iso) return '–'
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(Date.now() - 86400000)
  const hm = `${d.getHours()} h ${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === today.toDateString()) return `aujourd'hui à ${hm}`
  if (d.toDateString() === yesterday.toDateString()) return `hier à ${hm}`
  return `le ${d.getDate()} ${MONTHS[d.getMonth()]} à ${hm}`
}

async function refresh() {
  try {
    const res = await fetch('/api/sync')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const wasRunning = status.value?.running
    status.value = await res.json()
    error.value = ''
    if (wasRunning && !status.value.running && status.value.ok) emit('updated')
    schedule()
  } catch (e) {
    error.value = `état indisponible (${e.message})`
  }
}

function schedule() {
  clearTimeout(timer)
  if (status.value?.running) timer = setTimeout(refresh, POLL_MS)
}

async function start() {
  error.value = ''
  const res = await fetch('/api/sync', { method: 'POST' })
  if (!res.ok && res.status !== 409) {
    error.value = `lancement impossible (HTTP ${res.status})`
    return
  }
  status.value = { ...status.value, running: true }
  schedule()
}

onMounted(refresh)
onBeforeUnmount(() => clearTimeout(timer))

const failed = computed(() => status.value && !status.value.running && status.value.ok === false)
const detail = computed(() => {
  const s = status.value
  if (!s) return ''
  return [
    s.last_ok && `Dernière synchro réussie ${when(s.last_ok)}`,
    s.last_run && `Dernière sortie ${when(s.last_run)}`,
    s.last_health_day && `Santé à jour au ${new Date(s.last_health_day).toLocaleDateString('fr-FR')}`,
    failed.value && `Échec de la dernière tentative : ${s.message}`,
  ].filter(Boolean).join('\n')
})
</script>

<template>
  <div class="sync" :title="detail">
    <template v-if="status">
      <span class="state" :class="{ bad: failed }" aria-live="polite">
        <i :class="status.running ? 'spin' : failed ? 'ko' : 'ok'" />
        <template v-if="status.running">Mise à jour…</template>
        <template v-else-if="failed">Échec de la mise à jour</template>
        <template v-else>Données {{ when(status.last_ok) }}</template>
      </span>
      <button type="button" class="btn" :disabled="status.running" aria-label="Mettre à jour les données" @click="start">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" :class="{ rotating: status.running }">
          <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="label">Mettre à jour</span>
      </button>
    </template>
    <span v-if="error" class="muted">{{ error }}</span>
  </div>
</template>

<style scoped>
.sync { margin-left: auto; display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--ink-2); }
.state { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.state.bad { color: var(--bad); }
.state i { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.state i.ok { background: var(--good); }
.state i.ko { background: var(--bad); }
.state i.spin { background: var(--warn); }
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 5px 10px; cursor: pointer; font-size: 13px; color: var(--ink);
}
.btn:hover:not(:disabled) { background: var(--grid); }
.btn:disabled { opacity: 0.6; cursor: progress; }
.rotating { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 560px) {
  .label { display: none; }
}
</style>
