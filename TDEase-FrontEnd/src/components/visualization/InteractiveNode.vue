<template>
  <!--
    Vue Flow node shell for interactive viewer nodes on the WORKFLOW page.
    Responsibilities that only make sense inside a <VueFlow> provider live
    here and ONLY here:
      - PortList (which renders <Handle> and calls useVueFlow().updateNodeInternals)
      - the .interactive-node grid frame that positions the port columns

    The actual visualization body is delegated to ResultViewer, which has
    ZERO Vue Flow dependency. Explore renders ResultViewer directly and never
    touches this shell — that is what keeps the read-only page from crashing
    on `useVueFlow()` / `<Handle>` node-context lookups.
  -->
  <div class="interactive-node" :class="{ selected: !!isSelected }">
    <div class="ports-column left">
      <PortList side="left" :node-id="nodeId" :ports="inputs" />
    </div>

    <ResultViewer
      :node-id="nodeId"
      :label="label"
      :tool-id="data?.toolId || ''"
      :visualization-config="data?.visualizationConfig"
      :projection-config="data?.projectionConfig || null"
      :node-config="{ inputs: data?.nodeConfig?.inputs, outputs: data?.nodeConfig?.outputs }"
      :selected="isSelected"
      :dragging="dragging"
      :resizing="resizing"
      :position-absolute-x="positionAbsoluteX"
      :position-absolute-y="positionAbsoluteY"
      :explorer-result-context="explorerResultContext"
      @config-change="onViewerConfigChange"
    />

    <div class="ports-column right">
      <PortList side="right" :node-id="nodeId" :ports="outputs" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AxisMapping } from '@/types/visualization'
import { useWorkflowStore } from '@/stores/workflow'
import PortList from '@/components/node/PortList.vue'
import ResultViewer, {
  type ResultViewerNodePort,
  type ResultViewerConfig,
  type ExplorerResultContext,
} from './ResultViewer.vue'

interface InteractiveNodeData {
  nodeId?: string
  label?: string
  toolId?: string
  visualizationConfig?: ResultViewerConfig
  /** Unified projection config — supersedes visualizationConfig when present. */
  projectionConfig?: Record<string, unknown> | null
  nodeConfig?: {
    inputs?: ResultViewerNodePort[]
    outputs?: ResultViewerNodePort[]
  }
}

interface Props {
  id: string
  data: InteractiveNodeData
  selected?: boolean
  dragging?: boolean
  resizing?: boolean
  positionAbsoluteX?: number
  positionAbsoluteY?: number
  /** Forwarded to ResultViewer for workflow-independent badge rendering. */
  explorerResultContext?: ExplorerResultContext | null
}

const props = defineProps<Props>()

const workflowStore = useWorkflowStore()

const nodeId = computed(() => props.data?.nodeId || props.id)
const label = computed(() => props.data?.label || 'Interactive Viewer')

// Use workflowStore's selectedNodeId instead of VueFlow's internal selected prop,
// which can desync when the :nodes array recomputes. This ensures showVis stays
// true as long as the store tracks selection.
const isSelected = computed<boolean>(() =>
  props.selected || workflowStore.selectedNodeId === nodeId.value,
)

const inputs = computed<ResultViewerNodePort[]>(() => {
  const configured = props.data?.nodeConfig?.inputs
  if (configured?.length) return configured
  const node = workflowStore.nodes.find((item) => item.id === nodeId.value)
  return ((node?.inputs || []) as ResultViewerNodePort[])
})

const outputs = computed<ResultViewerNodePort[]>(() => {
  const configured = props.data?.nodeConfig?.outputs
  if (configured?.length) return configured
  const node = workflowStore.nodes.find((item) => item.id === nodeId.value)
  return ((node?.outputs || []) as ResultViewerNodePort[])
})

/**
 * Persist viewer config adjustments back to the workflow graph. This is the
 * workflow-only side-effect that was previously buried inside the shared
 * viewer body — by handling it here, the Explore page (which renders
 * ResultViewer directly and ignores this event) can no longer mutate the
 * graph store from a read-only context.
 */
function onViewerConfigChange(payload: { config: Record<string, unknown>; axisMapping: AxisMapping }) {
  const visualizationType = props.data?.visualizationConfig?.type || 'table'
  const currentData = workflowStore.nodes.find((n) => n.id === nodeId.value)?.data ?? {}
  workflowStore.updateNode(nodeId.value, {
    data: {
      ...currentData,
      visualizationConfig: {
        type: visualizationType,
        config: payload.config,
      },
    },
  })
}
</script>

<script lang="ts">
export default {
  name: 'InteractiveNode'
}
</script>

<style scoped>
.interactive-node {
  display: grid;
  --vis-min-width: 420px;
  /* Port columns are now content-driven (auto) — the compact PortRow sizes
     itself. Only the viewer center keeps a min-width. */
  grid-template-columns: auto minmax(var(--vis-min-width), 1fr) auto;
  align-items: stretch;
  gap: 8px;
  padding: 8px;
  min-height: 360px;
  max-height: 100%;
  width: 100%;
  background: var(--ctp-mantle);
  border: 1px solid var(--ctp-surface0);
  border-radius: 10px;
  overflow: hidden;
  container-type: inline-size;
}

.interactive-node.selected {
  filter: saturate(1.02);
}

/* Port columns must paint ABOVE the viewer body so the handle dots aren't
   covered by .vis-main's opaque background. Establishing a stacking context
   here lifts every Handle (position: absolute) above the sibling viewer. */
.ports-column {
  min-width: 0;
  position: relative;
  z-index: 2;
}

.ports-column.left {
  padding-top: 8px;
}

.ports-column.right {
  padding-top: 8px;
}

@container (max-width: 960px) {
  .interactive-node {
    --vis-min-width: 320px;
    min-height: 320px;
  }
}

@container (max-width: 640px) {
  .interactive-node {
    --vis-min-width: 260px;
  }
}

@supports not (container-type: inline-size) {
  @media (max-width: 960px) {
    .interactive-node {
      --vis-min-width: 320px;
      min-height: 320px;
    }
  }

  @media (max-width: 640px) {
    .interactive-node {
      --vis-min-width: 260px;
    }
  }
}
</style>
