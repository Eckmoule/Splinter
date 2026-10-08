<script setup>
// Sélecteur de période (boutons exclusifs).
defineProps({ options: Array, modelValue: String })
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="seg" role="group">
    <button
      v-for="o in options"
      :key="o.id"
      :class="{ on: o.id === modelValue }"
      :aria-pressed="o.id === modelValue"
      @click="$emit('update:modelValue', o.id)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
button { background: transparent; border: 0; padding: 5px 11px; cursor: pointer; font-size: 13px; color: var(--ink-2); }
button + button { border-left: 1px solid var(--border); }
button:hover { background: var(--grid); }
button.on { background: var(--ink); color: var(--surface); }
</style>
