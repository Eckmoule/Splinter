<script setup>
defineProps({ label: String, value: String, note: String, tone: { type: String, default: '' } })
</script>

<template>
  <div class="kpi">
    <span class="label">{{ label }}<span class="info"><slot name="info" /></span></span>
    <strong>{{ value }}</strong>
    <span class="note" :class="tone">{{ note }}</span>
    <slot />
  </div>
</template>

<style scoped>
.kpi {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.label { font-size: 13px; color: var(--ink-2); display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.info:empty { display: none; }
strong { font-size: 28px; font-weight: 600; letter-spacing: -0.01em; }
.note { font-size: 13px; color: var(--ink-2); }
.note.up { color: var(--good); }
.note.down { color: var(--bad); }
</style>
