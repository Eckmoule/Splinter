<script setup>
// Entraînement : est-ce que je m'entraîne correctement, en ce moment et de manière générale ?
// En ce moment : résumé par règles, charge (Forme / Fatigue / Fraîcheur), récupération.
// En général : répartition de l'intensité, régularité, montée en charge, variété des séances.
import { computed, inject, onMounted, ref, watch } from 'vue'
import Card from '../kit/components/Card.vue'
import ChartBox from '../kit/components/ChartBox.vue'
import InfoTip from '../kit/components/InfoTip.vue'
import KpiCard from '../kit/components/KpiCard.vue'
import Segmented from '../kit/components/Segmented.vue'
import { bandOption, datedOption, donutOption, stackedBarOption, thresholdBarOption } from '../kit/lib/charts'
import { MONTHS, num, weekLabel } from '../kit/lib/format'

const MONTH_OPTIONS = [
  { id: '3', label: '3 mois' },
  { id: '6', label: '6 mois' },
  { id: '12', label: '12 mois' },
]
const LOAD_OPTIONS = [
  { id: 'recent', label: '90 jours' },
  { id: 'all', label: 'Tout l’historique' },
]
const STATUS = {
  ok: { label: 'OK', color: 'var(--good)' },
  attention: { label: 'Attention', color: 'var(--warn)' },
  alerte: { label: 'Alerte', color: 'var(--bad)' },
  neutre: { label: '–', color: 'var(--ink-muted)' },
}

const data = ref(null)
const error = ref('')
const months = ref('3')
const loadRange = ref('recent')

async function load() {
  try {
    const res = await fetch(`/api/training?months=${months.value}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data.value = await res.json()
  } catch (e) {
    error.value = `Impossible de charger les données (${e.message}).`
  }
}
onMounted(load)
watch(months, load)
watch(inject('dataVersion'), load) // après une mise à jour des données

const fr = (v, d = 0) => num(v, d)
const hours = (v) => `${Math.floor(v)} h ${String(Math.round((v % 1) * 60)).padStart(2, '0')}`
const shortDay = (iso) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`

// --- en ce moment ------------------------------------------------------------------------------

const loadChart = computed(() => {
  const all = loadRange.value === 'all'
  const f = all ? data.value.fitness_all : data.value.now.fitness
  const span = all ? f.length : 90
  return (t) =>
    datedOption(t, {
      span,
      series: [
        { name: 'Forme', data: f.map((x) => [x.date, x.ctl]), color: t.series[0] },
        { name: 'Fatigue', data: f.map((x) => [x.date, x.atl]), color: t.series[1] },
        { name: 'Fraîcheur', data: f.map((x) => [x.date, x.tsb]), color: t.series[2], dashed: true },
      ],
      format: (v) => fr(v),
    })
})

const ratioChart = computed(() => {
  const f = data.value.now.fitness
  const [lo, hi, peak] = data.value.rules.ratio
  return (t) =>
    datedOption(t, {
      span: 90,
      series: [{ name: 'Fatigue ÷ Forme', data: f.map((x) => [x.date, x.ratio]), color: t.series[1] }],
      zone: { from: lo, to: hi },
      limits: [{ value: peak, label: 'pic' }],
      format: (v) => fr(v, 2),
    })
})

const hrvChart = computed(() => {
  const n = data.value.now
  return (t) => bandOption(t, { points: n.hrv, band: n.hrv_band, name: 'HRV', bandName: 'Normale', span: 90, format: (v) => `${fr(v)} ms`, color: t.series[2] })
})
const rhrChart = computed(() => {
  const n = data.value.now
  return (t) => datedOption(t, { span: 90, zoomed: true, series: [{ name: 'FC repos', data: n.rhr }], format: (v) => `${fr(v)} bpm` })
})
const sleepChart = computed(() => {
  const n = data.value.now
  return (t) =>
    datedOption(t, {
      span: 90,
      series: [{ name: 'Sommeil', type: 'bar', data: n.sleep_h, color: t.series[0] }],
      limits: [{ value: 6.5, label: '6 h 30' }],
      format: hours,
    })
})
const readinessChart = computed(() => {
  const n = data.value.now
  return (t) => datedOption(t, { span: 90, series: [{ name: 'Disposition', data: n.readiness, color: t.series[3] }], format: (v) => fr(v) })
})

// --- en général --------------------------------------------------------------------------------

const g = computed(() => data.value?.general)
const zoneShare = computed(() => {
  const z = g.value.zones_total_s
  const total = z.reduce((a, b) => a + b, 0)
  return total ? Math.round((100 * (z[0] + z[1])) / total) : null
})

const zonesChart = computed(() => {
  const rows = g.value.zones_by_month
  const pct = (z, i, j) => {
    const total = z.reduce((a, b) => a + b, 0)
    return total ? Math.round((100 * z.slice(i, j).reduce((a, b) => a + b, 0)) / total) : 0
  }
  return (t) =>
    stackedBarOption(t, {
      dates: rows.map((r) => `${r.month}-01`),
      series: [
        { name: 'Facile (zones 1-2)', values: rows.map((r) => pct(r.zones_s, 0, 2)), color: t.series[3] },
        { name: 'Modéré (zone 3)', values: rows.map((r) => pct(r.zones_s, 2, 3)), color: t.series[1] },
        { name: 'Intense (zones 4-5)', values: rows.map((r) => pct(r.zones_s, 3, 5)), color: t.series[2] },
      ],
      format: (v) => `${fr(v)} %`,
      axisFormat: (v) => `${fr(v)} %`,
    })
})

const weeklyChart = computed(() => {
  const w = g.value.weeks
  return (t) =>
    stackedBarOption(t, {
      dates: w.map((x) => x.week),
      series: [
        { name: 'Semaine complète', values: w.map((x) => (x.partial ? 0 : x.km)), color: t.series[0] },
        { name: 'Semaine en cours', values: w.map((x) => (x.partial ? x.km : 0)), color: t.axis },
      ],
      format: (v) => `${fr(v, 1)} km`,
      title: weekLabel,
    })
})

const rampChart = computed(() => {
  const w = g.value.weeks.filter((x) => !x.partial)
  return (t) =>
    thresholdBarOption(t, {
      labels: w.map((x) => x.week),
      values: w.map((x) => x.ramp_pct),
      limit: g.value.ramp_limit_pct,
      format: (v) => `${v > 0 ? '+' : ''}${fr(v)} %`,
      title: weekLabel,
      axisLabels: shortDay,
    })
})
const rampOver = computed(() => g.value.weeks.filter((x) => x.ramp_pct != null && x.ramp_pct > g.value.ramp_limit_pct).length)

const effectsChart = computed(() => {
  const slices = g.value.effects.map(([name, value]) => ({ name, value }))
  return (t) => donutOption(t, { slices, sub: 'sorties', format: (v) => fr(v), othersBelow: 0 })
})
</script>

<template>
  <div class="page">
    <header class="page-title">
      <h2>Entraînement</h2>
      <span>Est-ce que je m'entraîne correctement, en ce moment et en général ?</span>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!data" class="muted">Chargement…</p>

    <template v-else>
      <!-- résumé -->
      <section class="summary" :style="{ borderColor: STATUS[data.summary.level].color }">
        <div class="headline">
          <span class="dot" :style="{ background: STATUS[data.summary.level].color }" />
          <strong>{{ data.summary.sentence }}</strong>
          <InfoTip label="Comment est fait ce résumé">
            Règles simples, sur les derniers jours. <b>Rouge</b> : pic de charge, ou HRV basse <i>et</i> FC repos en
            hausse (signe classique de surmenage). <b>Orange</b> : au moins un signal d'attention.
            <b>Vert</b> : rien à signaler. Survoler chaque signal pour sa règle.
          </InfoTip>
        </div>
        <ul class="signals">
          <li v-for="s in data.summary.signals" :key="s.label" :title="s.rule">
            <i :style="{ background: STATUS[s.status].color }" />
            <span class="muted">{{ s.label }}</span>
            <span>{{ s.value }}</span>
          </li>
        </ul>
      </section>

      <h3 class="section">En ce moment</h3>

      <Card title="Forme, fatigue et fraîcheur" subtitle="Charge d'entraînement calculée depuis la FC de chaque séance">
        <template #actions>
          <Segmented v-model="loadRange" :options="LOAD_OPTIONS" />
          <InfoTip label="Méthode">
            Charge de chaque séance : TRIMP de Banister, calculé seconde par seconde à partir de la FC (FC repos du jour,
            FC max de tes zones). <b>Forme</b> = moyenne exponentielle sur {{ data.rules.ctl_days }} jours (ce que tu
            encaisses dans la durée), <b>Fatigue</b> = sur {{ data.rules.atl_days }} jours, <b>Fraîcheur</b> = Forme − Fatigue :
            négative après un bloc chargé, positive après du repos (idéal autour d'une course).
          </InfoTip>
        </template>
        <ul class="legend">
          <li><i style="background: var(--s1)" />Forme</li>
          <li><i style="background: var(--s2)" />Fatigue</li>
          <li><i class="dashed" style="border-color: var(--s3)" />Fraîcheur</li>
        </ul>
        <ChartBox :build="loadChart" :height="300" label="Forme, fatigue, fraîcheur et charge quotidienne" />
      </Card>

      <div class="two">
        <Card title="Fatigue ÷ Forme" subtitle="Zone grisée : montée en charge saine">
          <template #actions>
            <InfoTip label="Lecture">
              Ratio entre la charge des derniers jours et celle des dernières semaines. Entre
              {{ num(data.rules.ratio[0], 1) }} et {{ num(data.rules.ratio[1], 1) }} : progression maîtrisée. Au-delà de
              {{ num(data.rules.ratio[2], 1) }} : pic de charge, risque de blessure plus élevé. En dessous de
              {{ num(data.rules.ratio[0], 1) }} : charge en baisse.
            </InfoTip>
          </template>
          <ChartBox :build="ratioChart" :height="240" label="Ratio fatigue sur forme, 90 derniers jours" />
        </Card>
        <Card title="HRV nocturne" subtitle="Bande grisée : ta normale (moyenne ± écart-type des 2 mois précédents)">
          <ChartBox :build="hrvChart" :height="240" label="HRV nocturne et normale, 90 derniers jours" />
        </Card>
      </div>

      <div class="two">
        <Card title="FC au repos">
          <ChartBox :build="rhrChart" :height="200" label="FC au repos, 90 derniers jours" />
        </Card>
        <Card title="Sommeil" subtitle="Ligne : 6 h 30">
          <ChartBox :build="sleepChart" :height="200" label="Durée de sommeil, 90 derniers jours" />
        </Card>
      </div>

      <Card v-if="data.now.readiness.length" title="Disposition à l'entraînement" subtitle="Score Garmin du matin (0-100)">
        <ChartBox :build="readinessChart" :height="200" label="Disposition à l'entraînement, 90 derniers jours" />
      </Card>

      <div class="section-head">
        <h3 class="section">En général</h3>
        <Segmented v-model="months" :options="MONTH_OPTIONS" />
      </div>

      <section class="kpis">
        <KpiCard label="Sorties par semaine" :value="num(g.runs_per_week, 1)" :note="`${g.full_weeks} semaines complètes`" />
        <KpiCard label="Semaines sans course" :value="num(g.empty_weeks)" :note="`sur ${g.full_weeks}`" />
        <KpiCard label="Semaines avec une sortie longue" :value="num(g.long_run_weeks)" :note="`sur ${g.full_weeks} (sortie ≥ 1 h 15)`" />
        <KpiCard label="Temps en zones 1-2" :value="zoneShare == null ? '–' : `${zoneShare} %`" note="repère courant : ~80 % en facile">
          <template #info>
            <InfoTip label="Repère">
              Les plans d'entraînement d'endurance visent en général environ 80 % du temps à intensité facile
              (zones 1-2) et 20 % plus intense. Courir trop souvent en zone 3-4 fatigue sans développer autant
              l'endurance de base.
            </InfoTip>
          </template>
        </KpiCard>
      </section>

      <Card title="Répartition de l'intensité" subtitle="Part du temps de course par zone cardiaque, par mois">
        <ul class="legend">
          <li><i style="background: var(--s4)" />Facile (zones 1-2)</li>
          <li><i style="background: var(--s2)" />Modéré (zone 3)</li>
          <li><i style="background: var(--s3)" />Intense (zones 4-5)</li>
        </ul>
        <ChartBox :build="zonesChart" :height="260" label="Répartition du temps par intensité, par mois" />
      </Card>

      <div class="two">
        <Card title="Volume par semaine">
          <ChartBox :build="weeklyChart" :height="240" label="Distance par semaine" />
        </Card>
        <Card title="Montée en charge" :subtitle="`Volume vs moyenne des 4 semaines précédentes ; ${rampOver} semaine(s) au-delà de +${g.ramp_limit_pct} %`">
          <template #actions>
            <InfoTip label="Repère">
              Augmenter le volume de plus de {{ g.ramp_limit_pct }} % par rapport aux semaines précédentes accroît le
              risque de blessure. En rouge : les semaines au-delà. Une forte hausse après une semaine de coupure est
              normale.
            </InfoTip>
          </template>
          <ChartBox :build="rampChart" :height="240" label="Variation du volume hebdomadaire" />
        </Card>
      </div>

      <Card title="Types de séances" subtitle="Bénéfice principal de chaque sortie selon Garmin">
        <ChartBox :build="effectsChart" :height="280" label="Répartition des sorties par type de séance" />
      </Card>
    </template>
  </div>
</template>

<style scoped>
.summary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid;
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.headline { display: flex; align-items: center; gap: 10px; font-size: 16px; }
.headline strong { flex: 1; font-weight: 600; }
.dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
.signals { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 13px; }
.signals li { display: inline-flex; align-items: center; gap: 6px; cursor: help; }
.signals i { width: 8px; height: 8px; border-radius: 50%; }
.section { margin: 8px 0 0; font-size: 16px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.legend i.dashed { background: none; border-top: 2px dashed; height: 0; width: 14px; border-radius: 0; }
</style>
