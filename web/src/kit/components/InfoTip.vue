<script setup>
// Icône « i » ; son contenu (slot) s'affiche au survol ou au focus clavier.
// La bulle s'ouvre vers la gauche, ou vers la droite si elle sortirait de l'écran.
import { ref } from 'vue'

defineProps({ label: { type: String, default: 'Explications' } })
const id = `infotip-${Math.random().toString(36).slice(2, 8)}`
const root = ref(null)
const toRight = ref(false)
const BUBBLE_MAX = 440 // largeur max de la bulle (voir .bubble)
const MARGIN = 16

function place() {
  const r = root.value.getBoundingClientRect()
  const width = Math.min(BUBBLE_MAX, window.innerWidth * 0.85)
  toRight.value = r.right - width < MARGIN
}
</script>

<template>
  <span ref="root" class="infotip" :class="{ 'to-right': toRight }" @mouseenter="place" @focusin="place">
    <button type="button" class="icon" :aria-label="label" :aria-describedby="id">i</button>
    <span :id="id" role="tooltip" class="bubble"><slot /></span>
  </span>
</template>

<style scoped>
.infotip { position: relative; display: inline-flex; }
.icon {
  width: 24px; height: 24px; border-radius: 50%; cursor: help; padding: 0;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  font: italic 600 13px/1 Georgia, serif;
}
.icon:hover, .icon:focus-visible { background: var(--grid); color: var(--ink); }
.bubble {
  position: absolute; top: calc(100% + 8px); right: 0; z-index: 20; width: min(440px, 85vw);
  padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18); color: var(--ink); font-size: 13px; line-height: 1.5; text-align: left;
  font-weight: 400; visibility: hidden; opacity: 0; transition: opacity 0.12s;
}
.to-right .bubble { right: auto; left: 0; }
.infotip:hover .bubble, .infotip:focus-within .bubble { visibility: visible; opacity: 1; }
</style>
