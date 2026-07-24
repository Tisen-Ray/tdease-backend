<template>
  <svg class="data-edge-svg" style="overflow: visible">
    <g class="data-edge-group">
      <path
        :d="path"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        class="data-edge-path"
      />

      <text
        v-if="showLabel && !showCountBadge"
        :x="labelPosition.x"
        :y="labelPosition.y"
        class="data-edge-label"
        text-anchor="middle"
        font-size="10"
        fill="currentColor"
      >
        {{ label }}
      </text>

      <EdgeBadge
        v-if="showCountBadge"
        :count="count"
        :transform="`translate(${labelPosition.x}, ${labelPosition.y})`"
      />
    </g>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EdgeProps } from '@vue-flow/core'
import { useEdgePath } from '@/composables/useEdgePath'
import { dataEdgeLabel } from '@/services/workflow/edge-labels'
import EdgeBadge from './EdgeBadge.vue'

interface DataEdgeProps extends Omit<EdgeProps, 'data'> {
  data: {
    dataType?: string
    count?: number
    edgeIds?: string[]
  }
}

const props = withDefaults(defineProps<DataEdgeProps>(), {
  data: () => ({}),
})

const { path, labelPosition } = useEdgePath(props)

const showLabel = computed(() => !!props.data?.dataType)
const label = computed(() => dataEdgeLabel(props.data?.dataType))

// Aggregated edges carry count + edgeIds; show ×N when more than one underlying edge.
const count = computed(() => (typeof props.data?.count === 'number' ? props.data.count : 1))
const showCountBadge = computed(() => count.value > 1)
</script>

<style scoped>
.data-edge-svg {
  overflow: visible;
  color: var(--ctp-overlay1);
}

.data-edge-group {
  pointer-events: stroke;
  cursor: pointer;
}

.data-edge-path {
  transition: stroke-width 0.2s ease;
  shape-rendering: geometricPrecision;
}

.data-edge-path:hover {
  stroke-width: 3;
}

.data-edge-label {
  font-weight: 500;
  pointer-events: none;
  text-shadow: 0 1px 2px var(--color-bg-card);
}
</style>
