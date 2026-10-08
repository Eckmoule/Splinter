<script setup>
// Progression : est-ce que je progresse sur le long terme ?
// Indicateurs principaux : FC à allure fixe, efficacité vitesse/FC, VO2max.
// Contexte : découplage des sorties longues, FC repos et HRV, volume et plus longue sortie.
import { computed, onMounted, ref } from 'vue'
import Card from '../kit/components/Card.vue'
import ChartBox from '../kit/components/ChartBox.vue'
import InfoTip from '../kit/components/InfoTip.vue'
import KpiCard from '../kit/components/KpiCard.vue'
import { datedOption, lineOption, stackedBarOption, trendOption } from '../kit/lib/charts'
import { km, num, signed } from '../kit/lib/format'

const data = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    const res = await fetch('/api/progression')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data.value = await res.json()
  } catch (e) {
    error.value = `Impossible de charger les données (${e.message}).`
  }
})

const bpm = (v) => `${num(v)} bpm`
const ef = (v) => num(v, 2)

/** Tuile : valeur des 3 derniers mois et écart avec les 3 mêmes mois un an plus tôt. */
function tile(key, fmt, lowerIsBetter, digits = 0, unit = '') {
  const t = data.value.tiles[key]
  if (t.now == null) return { value: '–', note: 'pas assez de données', tone: '' }
  if (t.year_ago == null) return { value: fmt(t.now), note: 'pas de valeur il y a un an', tone: '' }
  const diff = t.now - t.year_ago
  const better = lowerIsBetter ? diff < 0 : diff > 0
  const tone = Math.abs(diff) < 10 ** -digits / 2 ? '' : better ? 'up' : 'down'
  return { value: fmt(t.now), note: `${signed(diff, (v) => num(v, digits))}${unit} vs il y a un an`, tone }
}
const tiles = computed(() =>
  data.value
    ? {
        fixed: tile('hr_fixed_pace', bpm, true, 0, ' bpm'),
        ef: tile('ef', ef, false, 2),
        vo2: tile('vo2max', (v) => num(v), false),
        rhr: tile('rhr', bpm, true, 1, ' bpm'),
      }
    : null,
)

const fixedChart = computed(() => {
  const d = data.value?.hr_fixed_pace
  return (t) => trendOption(t, { points: d.points, trend: d.trend, name: 'Sortie', trendName: 'Médiane 6 semaines', format: bpm })
})
const efChart = computed(() => {
  const d = data.value?.ef
  return (t) => trendOption(t, { points: d.points, trend: d.trend, name: 'Sortie', trendName: 'Moyenne 6 semaines', format: ef, color: t.series[2] })
})
const vo2Chart = computed(() => {
  const d = data.value?.vo2max
  return (t) => datedOption(t, { series: [{ name: 'VO2max', data: d.points, color: t.series[1], gaps: false }], zoomed: true })
})
const decouplingChart = computed(() => {
  const d = data.value?.decoupling
  return (t) => {
    const option = trendOption(t, { points: d.points, trend: d.trend, name: 'Sortie longue', trendName: 'Médiane 3 mois', format: (v) => `${num(v, 1)} %`, zoomed: false, color: t.series[3] })
    // repère : sous 5 %, l'endurance tient bien sur la durée
    option.series[0].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { color: t.muted, type: 'dashed', width: 1 },
      label: { color: t.muted, formatter: '5 %', position: 'insideEndTop' },
      data: [{ yAxis: 5 }],
    }
    return option
  }
})
const healthChart = (key, name, unit, slot) =>
  computed(() => {
    const pts = data.value?.[key]
    return (t) => datedOption(t, { series: [{ name, data: pts, color: t.series[slot], gaps: false }], zoomed: true, format: (v) => `${num(v, 1)} ${unit}` })
  })
const rhrChart = healthChart('rhr', 'FC repos', 'bpm', 0)
const hrvChart = healthChart('hrv', 'HRV', 'ms', 2)

const volumeChart = computed(() => {
  const m = data.value?.months ?? []
  return (t) =>
    stackedBarOption(t, { dates: m.map((x) => `${x.month}-01`), series: [{ name: 'Distance', values: m.map((x) => x.km) }], format: km })
})
const longestChart = computed(() => {
  const m = data.value?.months ?? []
  return (t) =>
    lineOption(t, {
      dates: m.map((x) => `${x.month}-01`),
      series: [{ name: 'Plus longue sortie', values: m.map((x) => x.longest), color: t.series[1] }],
      format: km,
    })
})
</script>

<template>
  <div class="page">
    <header class="page-title">
      <h2>Progression</h2>
      <span>Est-ce que je progresse sur le long terme ?</span>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="!data" class="muted">Chargement…</p>

    <template v-else>
      <section class="kpis">
        <KpiCard :label="`FC à ${data.fixed_pace_band}/km`" :value="tiles.fixed.value" :note="tiles.fixed.note" :tone="tiles.fixed.tone">
          <template #info>
            <InfoTip label="Comparaison">
              Moyenne des 3 derniers mois comparée aux 3 mêmes mois un an plus tôt : même saison, donc même
              effet de la chaleur. Vert = mieux (FC plus basse, efficacité ou VO2max plus haute).
            </InfoTip>
          </template>
        </KpiCard>
        <KpiCard label="Efficacité (vitesse ÷ FC)" :value="tiles.ef.value" :note="tiles.ef.note" :tone="tiles.ef.tone" />
        <KpiCard label="VO2max" :value="tiles.vo2.value" :note="tiles.vo2.note" :tone="tiles.vo2.tone" />
        <KpiCard label="FC repos" :value="tiles.rhr.value" :note="tiles.rhr.note" :tone="tiles.rhr.tone" />
      </section>

      <Card :title="`FC sur le plat à ${data.fixed_pace_band}/km`" subtitle="Plus elle baisse, moins le cœur travaille pour la même vitesse">
        <template #actions>
          <InfoTip label="Méthode">
            Pour chaque sortie route : FC moyenne sur les portions plates (pente &lt; 2 %) courues entre
            {{ data.fixed_pace_band }}/km, hors 5 premières minutes, si au moins 5 minutes. La courbe est la médiane
            des 6 semaines précédentes. La chaleur fait monter la FC : comparer de préférence les mêmes saisons.
          </InfoTip>
        </template>
        <ul class="legend">
          <li><i class="pt" style="background: var(--s1)" />Sortie</li>
          <li><i style="background: var(--s1)" />Médiane 6 semaines</li>
        </ul>
        <ChartBox :build="fixedChart" :height="280" label="FC à allure fixe par sortie et tendance" />
      </Card>

      <Card title="Efficacité : vitesse ÷ FC" subtitle="Mètres par minute par battement de cœur, sorties continues sur route">
        <template #actions>
          <InfoTip label="Méthode">
            Vitesse moyenne (m/min) divisée par la FC moyenne sur les portions plates, hors 5 premières minutes.
            Sorties route d'au moins 30 min, hors séances de fractionné (tours de récupération). Plus c'est haut,
            plus tu cours vite pour un même effort cardiaque. Courbe : moyenne des 6 semaines précédentes.
          </InfoTip>
        </template>
        <ul class="legend">
          <li><i class="pt" style="background: var(--s3)" />Sortie</li>
          <li><i style="background: var(--s3)" />Moyenne 6 semaines</li>
        </ul>
        <ChartBox :build="efChart" :height="280" label="Efficacité vitesse sur FC par sortie et tendance" />
      </Card>

      <div class="two">
        <Card title="VO2max" subtitle="Estimation Garmin">
          <ChartBox :build="vo2Chart" :height="240" label="Évolution de la VO2max" />
        </Card>
        <Card title="Découplage des sorties longues" subtitle="Sorties route ≥ 1 h sur le plat ; plus bas = meilleure endurance">
          <template #actions>
            <InfoTip label="Méthode">
              Perte d'efficacité (vitesse ÷ FC) entre la 1re et la 2e moitié de la sortie. Sous 5 %, l'endurance
              aérobie tient bien sur cette durée. Courbe : médiane des 3 mois précédents.
            </InfoTip>
          </template>
          <ChartBox :build="decouplingChart" :height="240" label="Découplage des sorties longues" />
        </Card>
      </div>

      <div class="two">
        <Card title="FC au repos" subtitle="Moyenne mensuelle ; elle baisse quand la forme aérobie progresse">
          <ChartBox :build="rhrChart" :height="220" label="FC au repos, moyenne mensuelle" />
        </Card>
        <Card title="HRV nocturne" subtitle="Moyenne mensuelle ; elle monte avec la forme et la récupération">
          <ChartBox :build="hrvChart" :height="220" label="HRV nocturne, moyenne mensuelle" />
        </Card>
      </div>

      <div class="two">
        <Card title="Volume par mois" subtitle="Le travail fourni, pour mettre les progrès en contexte">
          <ChartBox :build="volumeChart" :height="220" label="Distance par mois" />
        </Card>
        <Card title="Plus longue sortie du mois">
          <ChartBox :build="longestChart" :height="220" label="Plus longue sortie de chaque mois" />
        </Card>
      </div>
    </template>
  </div>
</template>

<style scoped>
.legend i.pt { border-radius: 50%; opacity: 0.5; }
</style>
