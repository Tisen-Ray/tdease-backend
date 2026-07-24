<template>
  <div class="ptm-viewer-stub">
    <div class="stub-header">Validation Report</div>
    <div class="stub-desc">Fallback scientific viewer preview.</div>
    <pre class="stub-data">{{ formatted }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ data: unknown }>()
const formatted = computed(() => JSON.stringify(props.data, null, 2))
</script>

<style scoped>
.ptm-viewer-stub { padding: 16px }
.stub-header { font-size: 16px; font-weight: 600; margin-bottom: 4px }
.stub-desc { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 12px }
.stub-data { font-size: 12px; max-height: 400px; overflow: auto; background: var(--color-bg-secondary); padding: 12px; border-radius: 6px }
</style>
