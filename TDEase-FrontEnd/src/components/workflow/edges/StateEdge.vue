<template>
  <svg class="state-edge-svg" style="overflow: visible">
    <g class="state-edge-group">
      <path
        :d="path"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-dasharray="5,5"
        class="state-edge-path"
      />

      <!-- Animated flow indicator for active state propagation -->
      <circle
        v-if="isActive"
        r="4"
        fill="currentColor"
        class="state-edge-flow"
      >
        <animateMotion
          :dur="animationDuration + 's'"
          repeatCount="indefinite"
          :path="path"
        />
      </circle>

      <text
        v-if="showLabel && !showCountBadge"
        :x="labelPosition.x"
        :y="labelPosition.y"
        class="state-edge-label"
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
import { stateEdgeLabel } from '@/services/workflow/edge-labels'
import EdgeBadge from './EdgeBadge.vue'

interface StateEdgeProps extends Omit<EdgeProps, 'data'> {
  data: {
    semanticType?: string
    active?: boolean
    count?: number
    edgeIds?: string[]
  }
}

const props = withDefaults(defineProps<StateEdgeProps>(), {
  data: () => ({}),
})

const { path, labelPosition } = useEdgePath(props)

// Aggregated state edges carry count + edgeIds; show ×N when more than one underlying edge.
const count = computed(() => (typeof props.data?.count === 'number' ? props.data.count : 1))
const showCountBadge = computed(() => count.value > 1)

const isActive = computed(() => props.data?.active ?? false)

// Animation duration scales with path length: ~1s for short, ~3s for 600px+.
// Bezier length approximated as 1.3× straight-line distance.
const animationDuration = computed(() => {
  const dx = props.targetX - props.sourceX
  const dy = props.targetY - props.sourceY
  const length = Math.hypot(dx, dy) * 1.3
  return Math.max(1, Math.min(3, length / 200))
})

const showLabel = computed(
  () => !!props.data?.semanticType && props.data.semanticType.startsWith('state/'),
)
const label = computed(() => stateEdgeLabel(props.data?.semanticType))
</script>

<style scoped>
.state-edge-svg {
  overflow: visible;
  color: var(--color-warning);
}

.state-edge-group {
  pointer-events: stroke;
  cursor: pointer;
}

.state-edge-path {
  transition: stroke-width 0.2s ease;
  shape-rendering: geometricPrecision;
}

.state-edge-path:hover {
  stroke-width: 3;
}

.state-edge-flow {
  filter: drop-shadow(0 0 2px color-mix(in srgb, var(--color-warning) 60%, transparent));
}

.state-edge-label {
  font-weight: 500;
  pointer-events: none;
  text-shadow: 0 1px 2px var(--color-bg-card);
}
</style>
