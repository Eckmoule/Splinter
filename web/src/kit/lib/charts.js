// Options ECharts réutilisables, au style du kit. Chaque fonction reçoit `t` (jetons de couleur fournis
// par ChartBox.vue) et renvoie l'option complète :
//   <ChartBox :build="(t) => lineOption(t, { dates, series })" />
// Dans un composant, envelopper dans un `computed` qui lit ses dépendances (voir views/).
import { MONTHS, monthLabel, num } from './format'

// --- briques communes ---------------------------------------------------------------------------

export const base = (t) => ({
  animationDuration: 400,
  textStyle: { color: t.ink2, fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' },
  grid: { left: 8, right: 16, top: 24, bottom: 24, containLabel: true },
})

export const tooltipBox = (t) => ({
  backgroundColor: t.surface,
  borderColor: t.grid,
  textStyle: { color: t.ink, fontSize: 13 },
  extraCssText: 'box-shadow:0 4px 16px rgba(0,0,0,.15);border-radius:8px;',
})

/** Petit carré de couleur pour les infobulles. */
export const dot = (color) =>
  `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px"></span>`

/** Ligne « ■ libellé ........ valeur » d'une infobulle. */
export const row = (color, name, value) =>
  `<div style="display:flex;justify-content:space-between;gap:20px"><span>${dot(color)}${name}</span><b>${value}</b></div>`

/** Bas d'axe arrondi un peu sous le minimum (pas de 1, 2 ou 5 × 10^n) : axe « zoomé » sur les données. */
export const niceMin = ({ min, max }) => {
  if (min <= 0) return min
  const span = Math.max(max - min, max * 0.05)
  const raw = span / 5
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].find((s) => s * pow >= raw) * pow
  return Math.max(0, Math.floor((min - span * 0.1) / step) * step)
}

/**
 * Axe des valeurs : quadrillage discret, pas de ligne d'axe. Part de 0 (ou descend sous 0 s'il y a des
 * valeurs négatives) ; `zoomed` = commence juste sous le minimum des données.
 */
export const valueAxis = (t, { zoomed = false, formatter = (v) => num(v) } = {}) => ({
  type: 'value',
  min: zoomed ? niceMin : ({ min }) => (min < 0 ? undefined : 0), // undefined : ECharts arrondit sous le minimum
  axisLabel: { color: t.muted, formatter },
  splitLine: { lineStyle: { color: t.grid } },
  axisLine: { show: false },
})

/**
 * Axe de catégories datées (« AAAA-MM » ou « AAAA-MM-JJ ») : une étiquette par mois (le 1er mois de
 * chaque année porte l'année), espacées selon la plage ; années seules au-delà de 3 ans.
 */
export const timeAxis = (t, dates, { boundaryGap = false } = {}) => {
  const ym = dates.map((d) => d.slice(0, 7))
  const months = [...new Set(ym)]
  const step = months.length <= 14 ? 1 : months.length <= 30 ? 2 : months.length <= 40 ? 3 : 12
  const shown = new Set(months.filter((m) => (Number(m.slice(5, 7)) - 1) % step === 0))
  const firstOfMonth = ym.map((m, i) => i === 0 || m !== ym[i - 1])
  const ticks = ym.map((m, i) => firstOfMonth[i] && shown.has(m))
  // premier mois à peine entamé (ex. une seule semaine) : sa graduation chevaucherait la suivante
  const next = ticks.indexOf(true, 1)
  if (dates.length > months.length && next > 0 && next < 3) ticks[0] = false
  const firstTick = dates[ticks.indexOf(true)]
  return {
    type: 'category',
    data: dates,
    boundaryGap,
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: {
      color: t.muted,
      interval: (i) => ticks[i],
      hideOverlap: true,
      formatter: (v) => {
        const [y, m] = v.split('-')
        if (step === 12) return y
        return m === '01' || v === firstTick ? `${MONTHS[Number(m) - 1]} ${y}` : MONTHS[Number(m) - 1]
      },
    },
  }
}

const axisTooltip = (t, { format = num, title = monthLabel } = {}) => ({
  ...tooltipBox(t),
  trigger: 'axis',
  axisPointer: { type: 'line', lineStyle: { color: t.muted } },
  formatter: (items) =>
    `<div style="margin-bottom:4px;color:${t.ink2}">${title(items[0].axisValue)}</div>` +
    items.filter((i) => i.value != null).map((i) => row(i.color, i.seriesName, format(i.value))).join(''),
})

// --- graphiques prêts à l'emploi -----------------------------------------------------------------

/**
 * Courbes dans le temps. `series` : [{ name, values, color? }], valeurs alignées sur `dates`.
 * Couleurs : séries du thème dans l'ordre (4 au plus, au-delà regrouper).
 */
export function lineOption(t, { dates, series, zoomed = false, area = false, format = num, title = monthLabel }) {
  return {
    ...base(t),
    tooltip: axisTooltip(t, { format, title }),
    xAxis: timeAxis(t, dates),
    yAxis: valueAxis(t, { zoomed, formatter: (v) => format(v) }),
    series: series.map((s, i) => ({
      name: s.name,
      type: 'line',
      symbol: 'none',
      data: s.values,
      color: s.color ?? t.series[i % t.series.length],
      lineStyle: { width: 2 },
      ...(area ? { areaStyle: { opacity: 0.12 } } : {}),
    })),
  }
}

/**
 * Barres empilées par période (semaine, mois…). `series` : [{ name, values, color? }] alignées sur
 * `dates` ; `title(date)` = en-tête de l'infobulle ; `format` = format des valeurs. Seul le segment
 * visible le plus haut de chaque barre a les coins arrondis ; l'infobulle donne aussi le total.
 */
export function stackedBarOption(t, { dates, series, format = num, axisFormat = (v) => num(v), title = monthLabel }) {
  const top = dates.map((_, j) => series.reduce((last, s, i) => (s.values[j] > 0 ? i : last), -1))
  return {
    ...base(t),
    tooltip: {
      ...tooltipBox(t),
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: t.grid, opacity: 0.4 } },
      formatter: (items) => {
        const total = items.reduce((s, i) => s + (i.value || 0), 0)
        const rows = items.length > 1 ? items.map((i) => row(i.color, i.seriesName, format(i.value || 0))).join('') : ''
        return (
          `<div style="margin-bottom:4px;color:${t.ink2}">${title(items[0].axisValue)}</div>` +
          rows +
          `<div style="display:flex;justify-content:space-between;gap:20px;margin-top:${rows ? 4 : 0}px">` +
          `<span>${items.length > 1 ? 'Total' : items[0].seriesName}</span><b>${format(total)}</b></div>`
        )
      },
    },
    xAxis: timeAxis(t, dates, { boundaryGap: true }),
    yAxis: valueAxis(t, { formatter: axisFormat }),
    series: series.map((s, i) => {
      const color = s.color ?? t.series[i % t.series.length]
      return {
        name: s.name,
        type: 'bar',
        stack: 'total',
        barMaxWidth: 24,
        color,
        data: s.values.map((v, j) => ({
          value: v,
          itemStyle: { color, borderRadius: top[j] === i ? [4, 4, 0, 0] : 0 },
        })),
      }
    }),
  }
}

/** Barres verticales simples, étiquette au-dessus ; valeurs négatives en rouge. */
export function barOption(t, { labels, values, format = num }) {
  return {
    ...base(t),
    tooltip: {
      ...tooltipBox(t),
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: t.grid, opacity: 0.4 } },
      formatter: ([p]) => `<div style="color:${t.ink2};margin-bottom:4px">${p.name}</div><b>${format(p.value)}</b>`,
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      axisLabel: { color: t.muted },
    },
    yAxis: valueAxis(t),
    series: [
      {
        type: 'bar',
        barMaxWidth: 28,
        data: values.map((v) => ({
          value: v,
          itemStyle: { color: v >= 0 ? t.accent : t.bad, borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
        })),
        label: { show: true, position: 'top', color: t.ink2, formatter: (p) => format(p.value) },
      },
    ],
  }
}

/**
 * Anneau (camembert) : total au centre, étiquettes « nom / valeur · % ». `slices` : [{ name, value, color? }].
 * Les parts sous `othersBelow` (2 %) sont regroupées dans « Autres » (détail dans l'infobulle).
 */
export function donutOption(t, { slices, center, sub = '', othersBelow = 0.02, format = num }) {
  const total = slices.reduce((s, x) => s + x.value, 0)
  const big = slices.filter((x) => x.value / total >= othersBelow)
  const small = slices.filter((x) => x.value / total < othersBelow)
  const data = big.map((x, i) => ({ name: x.name, value: x.value, itemStyle: { color: x.color ?? t.series[i % t.series.length] } }))
  if (small.length) {
    data.push({
      name: 'Autres',
      value: small.reduce((s, x) => s + x.value, 0),
      detail: small.map((x) => `${x.name} : ${format(x.value)}`),
      itemStyle: { color: t.muted },
    })
  }
  return {
    ...base(t),
    tooltip: {
      ...tooltipBox(t),
      trigger: 'item',
      formatter: (p) =>
        `${p.name} · ${p.percent.toLocaleString('fr-FR')} %<br/><b>${format(p.value)}</b>` +
        (p.data.detail ? `<div style="color:${t.ink2};margin-top:4px">${p.data.detail.join('<br/>')}</div>` : ''),
    },
    title: {
      text: center ?? format(total),
      subtext: sub,
      left: 'center',
      top: 'center',
      itemGap: 2,
      textStyle: { color: t.ink, fontSize: 18, fontWeight: 600 },
      subtextStyle: { color: t.ink2, fontSize: 12 },
    },
    series: [
      {
        type: 'pie',
        radius: ['38%', '60%'],
        startAngle: 90,
        data,
        itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
        label: {
          color: t.ink2,
          formatter: (p) => `${p.name}\n{v|${format(p.value)} · ${Math.round(p.percent)} %}`,
          rich: { v: { color: t.ink, fontWeight: 600, padding: [2, 0, 0, 0] } },
        },
        labelLine: { lineStyle: { color: t.axis } },
        emphasis: { scale: true, scaleSize: 4 },
      },
    ],
  }
}

// --- graphiques sur axe de dates (points datés « AAAA-MM-JJ ») ----------------------------------

const DAY_MS = 86400000

/**
 * Axe des dates : mois (et année en janvier) sur les longues périodes, jour + mois sur les courtes.
 * `span` = nombre de jours affichés (choisit le format des étiquettes).
 */
export const dateAxis = (t, { span = 365, min, max } = {}) => ({
  type: 'time',
  min,
  max,
  axisLine: { lineStyle: { color: t.axis } },
  axisTick: { show: false },
  splitLine: { show: false },
  minInterval: span > 120 ? 28 * DAY_MS : DAY_MS,
  axisLabel: {
    color: t.muted,
    hideOverlap: true,
    formatter: (v) => {
      const d = new Date(v)
      if (span <= 120) return `${d.getDate()} ${MONTHS[d.getMonth()]}`
      return d.getMonth() === 0 ? `${MONTHS[0]} ${d.getFullYear()}` : MONTHS[d.getMonth()]
    },
  },
})

/** Insère un point vide quand deux mesures sont espacées de plus de `maxGapDays` : la courbe se coupe. */
export const withGaps = (data, maxGapDays = 2) => {
  const out = []
  data.forEach((p, i) => {
    if (i && new Date(p[0]) - new Date(data[i - 1][0]) > maxGapDays * DAY_MS) out.push([data[i - 1][0], null])
    out.push(p)
  })
  return out
}

const isoDay = (v) => {
  const d = new Date(v)
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** Infobulle d'un graphique daté ; les séries dont le nom commence par « _ » sont masquées. */
export const dateTooltip = (t, { format = num, title = isoDay } = {}) => ({
  ...tooltipBox(t),
  trigger: 'axis',
  axisPointer: { type: 'line', lineStyle: { color: t.muted } },
  formatter: (items) => {
    const shown = items.filter((i) => !i.seriesName.startsWith('_') && i.value?.[1] != null)
    if (!shown.length) return ''
    return (
      `<div style="margin-bottom:4px;color:${t.ink2}">${title(shown[0].value[0])}</div>` +
      shown.map((i) => row(i.color, i.seriesName, format(i.value[1]))).join('')
    )
  },
})

/**
 * Nuage de points (une valeur par sortie) + courbe de tendance lissée.
 * `points`, `trend` : [[date, valeur]].
 */
export function trendOption(t, { points, trend, name, trendName = 'Tendance', format = num, zoomed = true, color, span }) {
  const c = color ?? t.series[0]
  return {
    ...base(t),
    tooltip: dateTooltip(t, { format }),
    xAxis: dateAxis(t, { span }),
    yAxis: valueAxis(t, { zoomed, formatter: (v) => format(v) }),
    series: [
      {
        name,
        type: 'scatter',
        data: points,
        symbolSize: 7,
        itemStyle: { color: c, opacity: 0.35 },
      },
      ...(trend
        ? [{ name: trendName, type: 'line', data: trend, symbol: 'none', color: c, lineStyle: { width: 2 } }]
        : []),
    ],
  }
}

/**
 * Courbes et barres datées sur un même axe (même unité). `series` : [{ name, data: [[date, v]],
 * type: 'line' | 'bar', color?, dashed?, area?, gaps? }] ; les courbes se coupent sur les trous de plus
 * de 2 jours (sauf `gaps: false`, ex. séries mensuelles). `zone` : { from, to } bande de référence grisée ;
 * `limits` : [{ value, label }] lignes horizontales.
 */
export function datedOption(t, { series, format = num, zoomed = false, span, zone, limits = [] }) {
  const marks = {
    ...(zone ? { markArea: { silent: true, itemStyle: { color: t.grid, opacity: 0.5 }, data: [[{ yAxis: zone.from }, { yAxis: zone.to }]] } } : {}),
    ...(limits.length
      ? {
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: t.muted, type: 'dashed', width: 1 },
            label: { color: t.muted, formatter: (p) => p.data.label ?? '', position: 'insideEndTop' },
            data: limits.map((l) => ({ yAxis: l.value, label: l.label })),
          },
        }
      : {}),
  }
  return {
    ...base(t),
    tooltip: dateTooltip(t, { format }),
    xAxis: dateAxis(t, { span }),
    yAxis: valueAxis(t, { zoomed, formatter: (v) => format(v) }),
    series: series.map((s, i) => {
      const color = s.color ?? t.series[i % t.series.length]
      const common = { name: s.name, data: s.data, color, ...(i === 0 ? marks : {}) }
      if (s.type === 'bar') return { ...common, type: 'bar', barMaxWidth: 24, itemStyle: { color, borderRadius: [3, 3, 0, 0] } }
      return {
        ...common,
        data: s.gaps === false ? s.data : withGaps(s.data),
        type: 'line',
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 2, type: s.dashed ? 'dashed' : 'solid' },
        ...(s.area ? { areaStyle: { opacity: 0.12 } } : {}),
      }
    }),
  }
}

/**
 * Valeur quotidienne + bande « normale » (ex. HRV : moyenne ± écart-type des semaines précédentes).
 * `band` : [[date, bas, haut]].
 */
export function bandOption(t, { points, band, name, bandName = 'Normale', format = num, span, color }) {
  const c = color ?? t.series[0]
  return {
    ...base(t),
    tooltip: {
      ...dateTooltip(t, { format }),
      formatter: (items) => {
        const day = items[0]?.value?.[0]
        const v = items.find((i) => i.seriesName === name)
        const b = band.find((x) => x[0] === day)
        return (
          `<div style="margin-bottom:4px;color:${t.ink2}">${isoDay(day)}</div>` +
          (v ? row(c, name, format(v.value[1])) : '') +
          (b ? row(t.grid, bandName, `${format(b[1])} – ${format(b[2])}`) : '')
        )
      },
    },
    xAxis: dateAxis(t, { span }),
    yAxis: valueAxis(t, { zoomed: true, formatter: (v) => format(v) }),
    series: [
      { name: '_bas', type: 'line', data: band.map((b) => [b[0], b[1]]), stack: 'band', symbol: 'none', lineStyle: { opacity: 0 } },
      {
        name: '_bande',
        type: 'line',
        data: band.map((b) => [b[0], b[2] - b[1]]),
        stack: 'band',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: t.grid, opacity: 0.7 },
      },
      { name, type: 'line', data: withGaps(points), color: c, symbol: 'circle', symbolSize: 5, lineStyle: { width: 2 } },
    ],
  }
}

/** Barres par catégorie colorées selon un seuil (au-delà de `limit` : couleur d'alerte), ligne au seuil. */
export function thresholdBarOption(t, { labels, values, limit, format = num, title = (l) => l, axisLabels }) {
  return {
    ...base(t),
    tooltip: {
      ...tooltipBox(t),
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: t.grid, opacity: 0.4 } },
      formatter: ([p]) => `<div style="color:${t.ink2};margin-bottom:4px">${title(p.name)}</div><b>${p.value == null ? '–' : format(p.value)}</b>`,
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, hideOverlap: true, formatter: axisLabels ?? ((v) => v) },
    },
    yAxis: valueAxis(t, { formatter: (v) => format(v) }),
    series: [
      {
        type: 'bar',
        barMaxWidth: 24,
        data: values.map((v) => ({
          value: v,
          itemStyle: { color: v != null && v > limit ? t.bad : t.accent, borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] },
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: t.muted, type: 'dashed', width: 1 },
          label: { color: t.muted, formatter: () => format(limit), position: 'insideEndTop' },
          data: [{ yAxis: limit }],
        },
      },
    ],
  }
}
