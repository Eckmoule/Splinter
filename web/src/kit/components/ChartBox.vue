<script setup>
// Conteneur ECharts : `build(theme)` renvoie l'option du graphique. Le composant la recalcule quand
// `build` change (données, filtres), quand le thème clair/sombre change, et au redimensionnement.
// `theme` = jetons de couleur lus dans styles/theme.css (voir lib/charts.js pour les utiliser).
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
// ECharts modulaire : seuls les types de graphiques et composants utilisés sont inclus (bundle allégé)
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { GridComponent, MarkAreaComponent, MarkLineComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, LineChart, PieChart, ScatterChart,
  GridComponent, MarkAreaComponent, MarkLineComponent, TitleComponent, TooltipComponent, CanvasRenderer,
])

const props = defineProps({
  build: { type: Function, required: true },
  height: { type: Number, default: 320 },
  label: { type: String, default: '' }, // description lue par les lecteurs d'écran
})

const el = ref(null)
let chart = null
let stopObserve = null

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Jetons de couleur courants. */
function theme() {
  return {
    surface: css('--surface'),
    ink: css('--ink'),
    ink2: css('--ink-2'),
    muted: css('--ink-muted'),
    grid: css('--grid'),
    axis: css('--axis'),
    good: css('--good'),
    bad: css('--bad'),
    warn: css('--warn'),
    accent: css('--accent'),
    series: [css('--s1'), css('--s2'), css('--s3'), css('--s4')],
  }
}

function render() {
  if (!chart) return
  chart.setOption(props.build(theme()), true)
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  const ro = new ResizeObserver(() => chart.resize())
  ro.observe(el.value)
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', render)
  stopObserve = () => {
    ro.disconnect()
    mq.removeEventListener('change', render)
  }
})

onBeforeUnmount(() => {
  stopObserve?.()
  chart?.dispose()
})

watch(() => props.build, render)
</script>

<template>
  <div ref="el" role="img" :aria-label="label" :style="{ height: height + 'px', width: '100%' }" />
</template>
