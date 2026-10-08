// Formats français pour Splinter. Tout nombre affiché passe par ces fonctions : cohérence partout.

export const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']

// useGrouping 'always' : « 1 435 » (sinon le français ne groupe pas les nombres à 4 chiffres)
const nf = (digits) =>
  new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits, minimumFractionDigits: 0, useGrouping: 'always' })

/** 1234.5 -> « 1 235 » (ou « 1 234,5 » avec digits = 1) */
export const num = (v, digits = 0) => (v == null || Number.isNaN(v) ? '–' : nf(digits).format(v))

/** 1435.2 -> « 1 435 km » ; sous 100 km une décimale : « 12,7 km » */
export const km = (v) => (v == null ? '–' : `${num(v, Math.abs(v) < 100 ? 1 : 0)} km`)

/** 18018 -> « 18 018 m » */
export const meters = (v) => (v == null ? '–' : `${num(v)} m`)

/** secondes -> « 156 h 54 » ou « 42 min » */
export const duration = (s) => {
  if (s == null) return '–'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h ? `${num(h)} h ${String(m).padStart(2, '0')}` : `${m} min`
}

/** secondes par km -> « 5:42 /km » */
export const pace = (sPerKm) => {
  if (!sPerKm) return '–'
  const s = Math.round(sPerKm)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} /km`
}

/** 10.5 -> « +10,5 % » */
export const pct = (v) => (v == null || !Number.isFinite(v) ? '–' : `${v > 0 ? '+' : ''}${num(v, 1)} %`)

/** écart signé avec unité : (12.3, km) -> « +12,3 km » ; (-4, num) -> « −4 » */
export const signed = (v, fmt = num) => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt(Math.abs(v))}`)

const toDate = (iso) => new Date(`${iso.slice(0, 10)}T00:00:00`)

/** '2026-09' ou '2026-09-14' -> « sept. 2026 » */
export const monthLabel = (iso) => {
  const [y, m] = iso.split('-')
  return `${MONTHS[Number(m) - 1]} ${y}`
}

/** '2026-09-14' -> « 14 sept. 2026 » */
export const dayLabel = (iso) => {
  const d = toDate(iso)
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** '2026-09-14' (lundi) -> « semaine du 14 sept. 2026 » */
export const weekLabel = (iso) => `semaine du ${dayLabel(iso)}`
