<template>
  <div class="evidence-graph" data-testid="evidence-graph-viewer">
    <div class="evidence-graph__canvas">
      <svg
        :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
        role="img"
        aria-label="Evidence graph"
      >
        <defs>
          <marker
            id="evidence-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>

        <line
          v-for="edge in renderedEdges"
          :key="edge.id"
          data-evidence-edge
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          :class="['evidence-graph__edge', `evidence-graph__edge--${edge.kind}`]"
          marker-end="url(#evidence-arrow)"
        />

        <g
          v-for="node in positionedNodes"
          :key="node.id"
          data-evidence-node
          :data-node-id="node.id"
          :transform="`translate(${node.x}, ${node.y})`"
          :class="['evidence-graph__node', `evidence-graph__node--${node.kind}`, { 'is-selected': selectedId === node.id }]"
          role="button"
          tabindex="0"
          @click="selectedId = node.id"
          @keydown.enter="selectedId = node.id"
        >
          <rect :width="nodeWidth" :height="nodeHeight" rx="6" />
          <text x="12" y="20" class="evidence-graph__kind">{{ node.kind }}</text>
          <text x="12" y="40" class="evidence-graph__label">{{ node.label }}</text>
        </g>
      </svg>
    </div>

    <aside
      v-if="selectedNode"
      class="evidence-graph__detail"
      data-testid="evidence-node-detail"
    >
      <div class="evidence-graph__detail-kind">{{ selectedNode.kind }}</div>
      <div class="evidence-graph__detail-title">{{ selectedNode.statement || selectedNode.id }}</div>
      <div v-if="selectedNode.rationale" class="evidence-graph__detail-copy">
        {{ selectedNode.rationale }}
      </div>
      <div
        v-for="(review, index) in selectedNode.reviews"
        :key="`${review.verdict}:${index}`"
        class="evidence-graph__review"
      >
        <div class="evidence-graph__review-status">
          {{ review.verdict }} / {{ review.status }}
        </div>
        <div v-if="review.rationale" class="evidence-graph__detail-copy">
          {{ review.rationale }}
        </div>
      </div>
      <div class="evidence-graph__detail-ref">{{ selectedNode.id }}</div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'

import type { Dataset } from '@/types/visualization'

type EvidenceNode = Record<string, unknown> & {
  id: string
  kind: string
  statement?: string
  rationale?: string
  reviews: Array<{ verdict: string; status: string; rationale?: string }>
}

type EvidenceEdge = {
  from: string
  to: string
  kind: string
}

const props = withDefaults(defineProps<{
  datasets: Dataset[]
  viewSpec?: Record<string, unknown>
}>(), {
  datasets: () => [],
  viewSpec: () => ({}),
})

const nodeWidth = 196
const nodeHeight = 54
const columnGap = 82
const rowGap = 28
const canvasWidth = 3 * nodeWidth + 2 * columnGap + 80

const nodes = computed<EvidenceNode[]>(() => {
  const dataset = props.datasets.find((item) => item.id === 'nodes' || item.kind === 'evidence_nodes')
  return (dataset?.rows ?? [])
    .filter((row) => typeof row.id === 'string' && row.id.trim())
    .map((row) => ({
      ...row,
      id: String(row.id),
      kind: String(row.kind || 'unknown'),
      statement: typeof row.statement === 'string' ? row.statement : undefined,
      rationale: typeof row.rationale === 'string' ? row.rationale : undefined,
      reviews: Array.isArray(row.reviews)
        ? row.reviews.flatMap((review) => {
          if (!review || typeof review !== 'object') return []
          const value = review as Record<string, unknown>
          if (typeof value.verdict !== 'string' || typeof value.status !== 'string') return []
          return [{
            verdict: value.verdict,
            status: value.status,
            rationale: typeof value.rationale === 'string' ? value.rationale : undefined,
          }]
        })
        : [],
    }))
})

const edges = computed<EvidenceEdge[]>(() => {
  const dataset = props.datasets.find((item) => item.id === 'edges' || item.kind === 'evidence_edges')
  return (dataset?.rows ?? [])
    .filter((row) => typeof row.from === 'string' && typeof row.to === 'string')
    .map((row) => ({ from: String(row.from), to: String(row.to), kind: String(row.kind || 'related') }))
})

function nodeColumn(kind: string): number {
  if (kind === 'inference') return 1
  if (['claim', 'hypothesis', 'conclusion'].includes(kind)) return 2
  return 0
}

const positionedNodes = computed(() => {
  const columnCounts = [0, 0, 0]
  return nodes.value.map((node) => {
    const column = nodeColumn(node.kind)
    const row = columnCounts[column]++
    const label = node.statement || node.rationale || node.id
    return {
      ...node,
      label: label.length > 28 ? `${label.slice(0, 25)}...` : label,
      x: 28 + column * (nodeWidth + columnGap),
      y: 24 + row * (nodeHeight + rowGap),
    }
  })
})

const canvasHeight = computed(() => {
  const counts = [0, 0, 0]
  positionedNodes.value.forEach((node) => counts[nodeColumn(node.kind)]++)
  return Math.max(240, Math.max(...counts) * (nodeHeight + rowGap) + 32)
})

const renderedEdges = computed(() => {
  const positions = new Map(positionedNodes.value.map((node) => [node.id, node]))
  return edges.value.flatMap((edge, index) => {
    const source = positions.get(edge.from)
    const target = positions.get(edge.to)
    if (!source || !target) return []
    return [{
      ...edge,
      id: `${edge.from}:${edge.to}:${edge.kind}:${index}`,
      x1: source.x + nodeWidth,
      y1: source.y + nodeHeight / 2,
      x2: target.x,
      y2: target.y + nodeHeight / 2,
    }]
  })
})

const rootRef = computed(() => {
  const options = props.viewSpec.options
  if (!options || typeof options !== 'object') return ''
  const value = (options as Record<string, unknown>).rootRef
  return typeof value === 'string' ? value : ''
})
const selectedId = ref('')
watchEffect(() => {
  if (!selectedId.value || !nodes.value.some((node) => node.id === selectedId.value)) {
    selectedId.value = rootRef.value || nodes.value[0]?.id || ''
  }
})
const selectedNode = computed(() => nodes.value.find((node) => node.id === selectedId.value) ?? null)
</script>

<style scoped>
.evidence-graph {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(210px, 28%);
  min-height: 320px;
  border: 1px solid var(--color-border, #d1d5db);
  background: var(--color-bg-primary, #ffffff);
}

.evidence-graph__canvas { overflow: auto; min-width: 0; }
.evidence-graph__canvas svg { display: block; width: 100%; min-width: 720px; height: auto; color: #64748b; }
.evidence-graph__edge { stroke: #94a3b8; stroke-width: 1.5; color: #94a3b8; }
.evidence-graph__edge--supports, .evidence-graph__edge--derives { stroke: #16835f; color: #16835f; }
.evidence-graph__edge--opposes { stroke: #c2414f; color: #c2414f; stroke-dasharray: 5 4; }
.evidence-graph__node { cursor: pointer; outline: none; }
.evidence-graph__node rect { fill: #ffffff; stroke: #94a3b8; stroke-width: 1.5; }
.evidence-graph__node--artifact rect { fill: #f8fafc; stroke: #64748b; }
.evidence-graph__node--inference rect { fill: #eff6ff; stroke: #2563a6; }
.evidence-graph__node--claim rect,
.evidence-graph__node--hypothesis rect,
.evidence-graph__node--conclusion rect { fill: #ecfdf5; stroke: #16835f; }
.evidence-graph__node.is-selected rect,
.evidence-graph__node:focus rect { stroke-width: 3; }
.evidence-graph__kind { fill: #475569; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.evidence-graph__label { fill: #111827; font-size: 12px; }
.evidence-graph__detail { padding: 18px; border-left: 1px solid var(--color-border, #d1d5db); background: #f8fafc; overflow-wrap: anywhere; }
.evidence-graph__detail-kind { color: #2563a6; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.evidence-graph__detail-title { margin-top: 8px; color: #111827; font-size: 14px; font-weight: 650; line-height: 1.45; }
.evidence-graph__detail-copy { margin-top: 12px; color: #475569; font-size: 12px; line-height: 1.5; }
.evidence-graph__review { margin-top: 14px; padding-top: 12px; border-top: 1px solid #d1d5db; }
.evidence-graph__review-status { color: #16835f; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.evidence-graph__detail-ref { margin-top: 16px; color: #64748b; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }

@media (max-width: 720px) {
  .evidence-graph { grid-template-columns: 1fr; }
  .evidence-graph__detail { border-top: 1px solid var(--color-border, #d1d5db); border-left: 0; }
}
</style>
