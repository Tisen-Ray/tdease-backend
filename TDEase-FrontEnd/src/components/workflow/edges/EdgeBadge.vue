<script setup lang="ts">
/**
 * EdgeBadge — the ×N aggregation pill shared by DataEdge and StateEdge.
 *
 * Both edge components render the identical `<g><rect/><text>×N</text></g>`
 * markup when an aggregated edge represents more than one underlying edge.
 * This is the single owner of that markup + its theme.
 */
defineProps<{
  /** How many underlying edges were collapsed into the aggregate. */
  count: number
}>()
</script>

<template>
  <g class="edge-badge">
    <rect x="-14" y="-9" width="28" height="16" rx="8" />
    <text text-anchor="middle" y="3" font-size="10" font-weight="600">×{{ count }}</text>
  </g>
</template>

<style scoped>
/* Themed via tokens so the pill reads on both light/dark canvases. */
.edge-badge rect {
  fill: var(--lab-panel-bg);
  stroke: var(--lab-panel-border);
  stroke-width: 1;
}

.edge-badge text {
  fill: var(--lab-text-strong);
  pointer-events: none;
}
</style>
