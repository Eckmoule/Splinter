<script setup>
// Menu « burger » : liste des pages ; se ferme au choix, au clic extérieur et avec Échap.
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({ routes: Array, current: String })

const open = ref(false)
const root = ref(null)

const onClick = (e) => {
  if (open.value && !root.value.contains(e.target)) open.value = false
}
const onKey = (e) => {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('click', onClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <nav ref="root" class="nav">
    <button class="burger" :aria-expanded="open" aria-controls="nav-menu" aria-label="Menu" @click="open = !open">
      <span /><span /><span />
    </button>
    <ul v-show="open" id="nav-menu" class="menu">
      <li v-for="r in routes" :key="r.path">
        <a :href="`#${r.path}`" :aria-current="r.path === current ? 'page' : undefined" @click="open = false">{{ r.label }}</a>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.nav { position: relative; }
.burger {
  width: 36px; height: 36px; display: grid; place-content: center; gap: 4px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px; cursor: pointer;
}
.burger span { display: block; width: 16px; height: 2px; border-radius: 1px; background: var(--ink); }
.burger:hover { background: var(--grid); }
.menu {
  position: absolute; top: 44px; left: 0; z-index: 10; min-width: 200px;
  list-style: none; margin: 0; padding: 6px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
.menu a { display: block; padding: 8px 12px; border-radius: 6px; color: var(--ink); text-decoration: none; font-size: 14px; }
.menu a:hover { background: var(--grid); }
.menu a[aria-current='page'] { font-weight: 600; background: var(--grid); }
</style>
