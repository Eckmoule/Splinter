<script setup>
// `collapsible` : contenu masqué par défaut (sauf `open`), lien « Afficher / Masquer <what> » à droite du titre.
import { ref } from 'vue'

const props = defineProps({
  title: String,
  subtitle: String,
  collapsible: Boolean,
  open: Boolean,
  what: { type: String, default: 'le tableau' },
})
const isOpen = ref(!props.collapsible || props.open)
const id = `card-${Math.random().toString(36).slice(2, 8)}`
</script>

<template>
  <section class="card" :class="{ closed: !isOpen }">
    <header>
      <div>
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div class="actions">
        <slot v-if="isOpen" name="actions" />
        <button v-if="collapsible" type="button" class="link" :aria-expanded="isOpen" :aria-controls="id" @click="isOpen = !isOpen">
          {{ isOpen ? 'Masquer' : 'Afficher' }} {{ what }}
        </button>
      </div>
    </header>
    <div v-show="isOpen" :id="id"><slot /></div>
  </section>
</template>

<style scoped>
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 20px 12px;
  min-width: 0;
}
.card.closed { padding-bottom: 16px; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.closed header { margin-bottom: 0; }
h2 { font-size: 15px; font-weight: 600; margin: 0; }
p { margin: 2px 0 0; font-size: 13px; color: var(--ink-2); }
.actions { display: flex; gap: 8px; align-items: center; }
</style>
