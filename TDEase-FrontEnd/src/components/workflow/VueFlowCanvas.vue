<template>
  <div
    class="vue-flow-container"
    tabindex="0"
    role="application"
    :aria-label="$t('workflow.canvas.ariaLabel')"
    @keydown="handleKeyDown"
  >
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypesRaw"
      :edge-types="edgeTypesRaw"
      :fit-view-on-init="true"
      :snap-to-grid="true"
      :snap-grid="[20, 20]"
      :connection-mode="ConnectionMode.Strict"
      :connection-line-type="ConnectionLineType.SmoothStep"
      :nodes-draggable="props.interactive"
      :nodes-connectable="props.interactive"
      class="vue-flow-editor"
      @dragover="onDragOver"
      @node-drag-start="onNodeDragStart"
      @node-drag-stop="onNodeDragStop"
      @node-click="onNodeClick"
      @node-context-menu="onNodeContextMenu"
      @connect="onConnect"
      @edge-click="onEdgeClick"
      @edge-context-menu="onEdgeContextMenu"
      @drop="onDrop"
    >
      <!-- 背景组件 -->
      <Background
        :gap="20"
        :pattern-size="1"
      />

      <!-- 控制组件 -->
      <Controls
        :show-zoom="true"
        :show-fit-view="true"
        :show-interactive="true"
      />

      <!-- 小地图组件 -->
      <MiniMap />

      <!-- Empty state hint -->
      <div v-if="nodes.length === 0 && !readOnly" class="empty-state">
        <div class="empty-content">
          <el-icon class="empty-icon" :size="48">
            <Operation />
          </el-icon>
          <h3>{{ $t('workflow.panel.emptyTitle') }}</h3>
          <p>{{ $t('workflow.panel.emptyDesc') }}</p>
        </div>
      </div>

      <!-- Frozen watermark -->
      <div v-if="false" class="canvas-frozen-watermark">
        🔒 {{ $t('workflow.canvas.frozenWatermark', { runId: shortRunId }) }}
      </div>
    </VueFlow>

    <!-- Canvas floating toolbar (Figma-style): undo / redo / auto-layout.
         Workflow editing ops live here, not in the top app bar — the top bar
         is reserved for app-level/global concerns. -->
    <div
      v-if="props.interactive && !props.readOnly"
      class="canvas-floating-toolbar"
      role="toolbar"
      :aria-label="$t('workflow.canvas.toolbarAriaLabel')"
    >
      <button
        type="button"
        class="canvas-floating-toolbar__btn"
        :disabled="!canUndo"
        :title="$t('workflow.toolbar.undo')"
        :aria-label="$t('workflow.toolbar.undo')"
        @click="handleUndo"
      >
        <CatppuccinIcon name="RefreshLeft" :size="16" />
      </button>
      <button
        type="button"
        class="canvas-floating-toolbar__btn"
        :disabled="!canRedo"
        :title="$t('workflow.toolbar.redo')"
        :aria-label="$t('workflow.toolbar.redo')"
        @click="handleRedo"
      >
        <CatppuccinIcon name="RefreshRight" :size="16" />
      </button>
      <span class="canvas-floating-toolbar__divider" />
      <button
        type="button"
        class="canvas-floating-toolbar__btn"
        :title="$t('workflow.toolbar.layout')"
        :aria-label="$t('workflow.toolbar.layout')"
        @click="autoLayout"
      >
        <CatppuccinIcon name="AutoLayout" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueFlow, ConnectionMode, ConnectionLineType, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import type {
  Node,
  Edge,
  NodeMouseEvent,
  NodeDragEvent,
  EdgeMouseEvent,
  Connection,
  NodeTypesObject,
} from '@vue-flow/core'
import { ElMessage } from 'element-plus'
import { useWorkflowStore } from '@/stores/workflow'
import type { NodeDefinition as WorkflowNodeDefinition } from '@/stores/workflow'
import { useStateBusStore } from '@/stores/state-bus'
import { Operation } from '@element-plus/icons-vue'
import { CatppuccinIcon } from '@/components/icons'
// Node types are resolved via ViewerRegistry with lazy-loaded components
import { viewerRegistry } from '@/services/visualization/ViewerRegistry'
import { edgeTypes } from './edges'
import { parseConnectionHandle } from '@/services/workflow/handle-parse'
import {
  buildAggregatedEdgeProjections,
  buildVueFlowNodeProjection,
  isDuplicateWorkflowConnection,
  toStatePortDefinition,
  type CachedVueFlowEdgeEntry,
  type CachedVueFlowNodeEntry,
} from '@/services/workflow/graph-projection'
import { nodeDefinitionFromPayload } from '@/services/workflow/node-payload'
import { areWorkflowPortsCompatible } from '@/services/workflow/port-compatibility'

const props = withDefaults(defineProps<{
  /** When false, nodes are not draggable, connectable, or deletable. */
  interactive?: boolean
  /** When true, blocks node drag, drop, connect, and delete. */
  readOnly?: boolean
  /** Short run id shown in the watermark. */
  shortRunId?: string
}>(), {
  interactive: true,
  readOnly: false,
  shortRunId: '',
})

function resolveVueFlowNodeType(node: WorkflowNodeDefinition): string {
  return viewerRegistry.resolveNodeType(node)
}





// VueFlow projection caches live in the canvas store (non-reactive, scoped to
// the store lifetime) rather than module-level `let`s here, which leaked
// across mounts (HMR / route changes). The projection computeds read them
// without tracking and write back via the store setters — the cache is a
// memo scratch space (an output of the projection), so making it reactive
// would re-trigger the projection on every write (infinite loop).
function readNodeCache(): Map<string, CachedVueFlowNodeEntry> {
  return workflowStore.getVueFlowNodeCache() as Map<string, CachedVueFlowNodeEntry>
}
function readEdgeCache(): Map<string, CachedVueFlowEdgeEntry> {
  return workflowStore.getVueFlowEdgeCache() as Map<string, CachedVueFlowEdgeEntry>
}

const emit = defineEmits<{
  nodeSelect: [nodeId: string | null]
  contextMenu: [event: MouseEvent | TouchEvent, context: string, data: unknown]
}>()

const workflowStore = useWorkflowStore()

const stateBus = useStateBusStore()
const { onPaneReady, fitView, zoomIn, zoomOut } = useVueFlow()
const { t } = useI18n()

// History state for the floating undo/redo buttons. The store exposes
// historyManager as a getter object (see stores/workflow.ts), so we read
// canUndo/canRedo reactively through a computed.
const canUndo = computed(() => workflowStore.historyManager?.canUndo ?? false)
const canRedo = computed(() => workflowStore.historyManager?.canRedo ?? false)

function handleUndo() {
  if (workflowStore.undo()) {
    ElMessage.success(t('workflow.messages.undoSuccess'))
  } else {
    ElMessage.info(t('workflow.messages.cannotUndo'))
  }
}

function handleRedo() {
  if (workflowStore.redo()) {
    ElMessage.success(t('workflow.messages.redoSuccess'))
  } else {
    ElMessage.info(t('workflow.messages.cannotRedo'))
  }
}

// Progressive data loading: fetch and display output data as each node completes
import { useProgressiveDataLoading } from '@/composables/workflow/useProgressiveDataLoading'
useProgressiveDataLoading()

// 从 store 获取数据并转换为 Vue Flow 格式
const nodes = computed<Node[]>(() => {
  const currentCache = readNodeCache()
  const nextCachedNodes = new Map<string, CachedVueFlowNodeEntry>()
  const mappedNodes = workflowStore.nodes.map((node) => {
    const nodeType = resolveVueFlowNodeType(node)
    const executionPresentation = workflowStore.nodeExecutionPresentations[node.id]
    const projection = buildVueFlowNodeProjection({
      node,
      nodeType,
      executionPresentation,
    })

    const cachedEntry = currentCache.get(node.id)
    if (
      cachedEntry &&
      cachedEntry.sourceNode === node &&
      cachedEntry.executionPresentation === executionPresentation &&
      cachedEntry.nodeType === nodeType &&
      cachedEntry.label === projection.label &&
      cachedEntry.color === projection.color &&
      cachedEntry.resolvedToolId === projection.resolvedToolId
    ) {
      nextCachedNodes.set(node.id, cachedEntry)
      return cachedEntry.value
    }

    nextCachedNodes.set(node.id, {
      sourceNode: node,
      executionPresentation,
      nodeType,
      label: projection.label,
      color: projection.color,
      resolvedToolId: projection.resolvedToolId,
      value: projection.value
    })

    return projection.value
  })

  workflowStore.setVueFlowNodeCache(nextCachedNodes)
  return mappedNodes
})

const edges = computed<Edge[]>(() => {
  // Aggregate raw store edges into one rendered line per (source|port|target|port|kind).
  // N file-level edges between the same port pair collapse to a single line with a
  // ×N badge; the aggregate carries the underlying edgeIds[] so deletion maps back.
  const projections = buildAggregatedEdgeProjections(workflowStore.edges, stateBus.isConnectionActive)
  const currentCache = readEdgeCache()
  const nextCachedEdges = new Map<string, CachedVueFlowEdgeEntry>()
  const mappedEdges = projections.map((projection) => {
    const id = projection.id
    const edgeType: 'data' | 'state' = projection.value.type === 'state' ? 'state' : 'data'
    const cachedEntry = currentCache.get(id)
    if (
      cachedEntry &&
      cachedEntry.sourceHandle === projection.value.sourceHandle &&
      cachedEntry.targetHandle === projection.value.targetHandle &&
      cachedEntry.edgeType === edgeType &&
      cachedEntry.active === projection.active &&
      cachedEntry.count === projection.count
    ) {
      nextCachedEdges.set(id, cachedEntry)
      return cachedEntry.value
    }

    nextCachedEdges.set(id, {
      sourceEdge: null,
      sourceHandle: projection.value.sourceHandle,
      targetHandle: projection.value.targetHandle,
      edgeType,
      active: projection.active,
      count: projection.count,
      value: projection.value
    })

    return projection.value
  })

  workflowStore.setVueFlowEdgeCache(nextCachedEdges)
  return mappedEdges
})

const nodeTypes = viewerRegistry.getNodeTypeMap()
Object.keys(nodeTypes).forEach((key) => {
  nodeTypes[key] = markRaw(nodeTypes[key])
})
const nodeTypesRaw = nodeTypes as unknown as NodeTypesObject

// Wrap edge types with markRaw to prevent Vue reactivity overhead
const edgeTypesRaw = {
  state: markRaw(edgeTypes.state),
  data: markRaw(edgeTypes.data)
}

const waitForFrame = () => new Promise<void>((resolve) => {
  requestAnimationFrame(() => resolve())
})

onPaneReady((instance) => {
  instance.fitView()
})

// 自动布局函数 - 使用 dagre 算法，根据节点实际尺寸自动调整间距
const autoLayout = async () => {
  const { default: dagre } = await import('dagre')
  const currentNodes = nodes.value
  const currentEdges = edges.value

  if (currentNodes.length === 0) {
    ElMessage.info(t('workflow.canvas.noNodesForLayout'))
    return
  }

  // 等待 DOM 更新，确保节点已渲染
  await nextTick()
  await waitForFrame()
  await waitForFrame()

  // 获取节点的实际尺寸 - 优先使用缓存
  const nodeDimensions = new Map<string, { width: number; height: number }>()
  const minNodeWidth = 180  // 最小节点宽度
  const minNodeHeight = 100 // 最小节点高度
  const basePadding = 10    // 基础间距

  // 对于 interactive 节点，使用更大的默认尺寸和间距
  const interactiveNodeDefaultWidth = 600
  const interactiveNodeDefaultHeight = 500
  const interactivePadding = 70  // interactive 节点需要稍大的间距

  currentNodes.forEach((node) => {
    // 优先从缓存获取节点尺寸
    const cachedSize = workflowStore.getNodeSize(node.id)

    if (cachedSize && cachedSize.width > 0 && cachedSize.height > 0) {
      // 使用缓存的尺寸
      nodeDimensions.set(node.id, {
        width: Math.max(cachedSize.width, node.type === 'interactive' ? interactiveNodeDefaultWidth : minNodeWidth),
        height: Math.max(cachedSize.height, node.type === 'interactive' ? interactiveNodeDefaultHeight : minNodeHeight)
      })
    } else {
      // 缓存未命中，尝试从 DOM 获取
      let nodeElement: HTMLElement | null

      // 方法1: 通过 data-id 属性查找
      nodeElement = document.querySelector(`[data-id="${node.id}"]`) as HTMLElement

      // 方法2: 如果找不到，尝试通过 Vue Flow 的节点 class 和 id 查找
      if (!nodeElement) {
        nodeElement = document.querySelector(`.vue-flow__node[data-id="${node.id}"]`) as HTMLElement
      }

      // 方法3: 通过 id 属性查找
      if (!nodeElement) {
        nodeElement = document.getElementById(`vue-flow-node-${node.id}`) as HTMLElement
      }

      if (nodeElement) {
        const rect = nodeElement.getBoundingClientRect()
        // 确保尺寸有效且不小于最小值
        let width = rect.width > 0 ? rect.width : minNodeWidth
        let height = rect.height > 0 ? rect.height : minNodeHeight

        // 对于 interactive 节点，如果检测到的尺寸太小，使用默认尺寸
        if (node.type === 'interactive') {
          if (width < interactiveNodeDefaultWidth) {
            width = interactiveNodeDefaultWidth
          }
          if (height < interactiveNodeDefaultHeight) {
            height = interactiveNodeDefaultHeight
          }
        }

        const finalWidth = Math.max(width, node.type === 'interactive' ? interactiveNodeDefaultWidth : minNodeWidth)
        const finalHeight = Math.max(height, node.type === 'interactive' ? interactiveNodeDefaultHeight : minNodeHeight)

        nodeDimensions.set(node.id, { width: finalWidth, height: finalHeight })

        // 更新缓存
        workflowStore.setNodeSize(node.id, finalWidth, finalHeight)
      } else {
        // 如果找不到元素，根据节点类型使用不同的默认尺寸
        if (node.type === 'interactive') {
          nodeDimensions.set(node.id, {
            width: interactiveNodeDefaultWidth,
            height: interactiveNodeDefaultHeight
          })
        } else {
          nodeDimensions.set(node.id, {
            width: minNodeWidth,
            height: minNodeHeight
          })
        }
      }
    }
  })

  // 计算最大节点尺寸（而不是平均），用于设置更保守的布局参数
  const maxWidth = Math.max(...Array.from(nodeDimensions.values()).map(dim => dim.width))
  const maxHeight = Math.max(...Array.from(nodeDimensions.values()).map(dim => dim.height))

  // 检查是否有 interactive 节点
  const hasInteractive = currentNodes.some(node => node.type === 'interactive')
  const padding = hasInteractive ? interactivePadding : basePadding

  // 创建 dagre 图
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))

  // 使用最大节点尺寸 + 间距，确保不会重叠
  g.setGraph({ 
    rankdir: 'LR', // 从左到右布局
    nodesep: Math.max(maxWidth + padding, 10),  // 节点水平间距（基于最大宽度 + 间距）
    ranksep: Math.max(maxHeight + padding, 10),  // 层级垂直间距（基于最大高度 + 间距）
    marginx: 5,   // 左右边距
    marginy: 5    // 上下边距
  })

  // 添加节点到 dagre 图，使用实际尺寸加上安全边距
  currentNodes.forEach((node) => {
    const dim = nodeDimensions.get(node.id) || { 
      width: node.type === 'interactive' ? interactiveNodeDefaultWidth : minNodeWidth, 
      height: node.type === 'interactive' ? interactiveNodeDefaultHeight : minNodeHeight 
    }
    // 为每个节点添加小的安全边距（特别是 interactive 节点）
    const safetyMargin = node.type === 'interactive' ? 4 : 2
    g.setNode(node.id, { 
      width: dim.width + safetyMargin, 
      height: dim.height + safetyMargin 
    })
  })

  // 添加边到 dagre 图
  currentEdges.forEach((edge) => {
    if (edge.source && edge.target) {
      g.setEdge(edge.source, edge.target)
    }
  })

  // 计算布局
  dagre.layout(g)

  // 更新节点位置到 store（使用每个节点的实际尺寸）
  currentNodes.forEach((node) => {
    const nodeWithPosition = g.node(node.id)
    const dim = nodeDimensions.get(node.id) || { 
      width: node.type === 'interactive' ? interactiveNodeDefaultWidth : minNodeWidth, 
      height: node.type === 'interactive' ? interactiveNodeDefaultHeight : minNodeHeight 
    }
    if (nodeWithPosition) {
      const newPosition = {
        x: nodeWithPosition.x - dim.width / 2,
        y: nodeWithPosition.y - dim.height / 2
      }
      workflowStore.moveNode(node.id, newPosition)
    }
  })

  // 调整视口以适应新布局
  await nextTick()
  await waitForFrame()
  fitView({ padding: 0.1, duration: 300 })

  ElMessage.success(t('workflow.messages.autoLayoutComplete'))
}

// 暴露方法给父组件
defineExpose({
  fitView,
  zoomIn,
  zoomOut,
  autoLayout
})

// 事件处理函数
// Required by VueFlow for internal drag tracking — keep binding even though handler is empty.
const onNodeDragStart = (_evt: NodeDragEvent) => {}

const onNodeDragStop = (evt: NodeDragEvent) => {
  workflowStore.moveNode(evt.node.id, evt.node.position)
}

const onNodeClick = (evt: NodeMouseEvent) => {
  emit('nodeSelect', evt.node.id)
}

const onNodeContextMenu = (evt: NodeMouseEvent) => {
  evt.event.preventDefault()
  emit('contextMenu', evt.event, 'node', evt.node)
}

const onConnect = (connection: Connection) => {
  const sourceId = connection.source
  const targetId = connection.target
  if (sourceId === targetId) {
    ElMessage.error(t('workflow.messages.selfConnectionNotAllowed'))
    return false
  }
  const { port: sPort, suffix: sSuffix } = parseConnectionHandle(connection.sourceHandle ?? undefined, 'output')
  const { port: tPort, suffix: tSuffix } = parseConnectionHandle(connection.targetHandle ?? undefined, 'input')
  const sNode = workflowStore.nodes.find(n => n.id === sourceId)
  const tNode = workflowStore.nodes.find(n => n.id === targetId)
  if (!sNode || !tNode) return false
  const sDef = sNode.outputs.find(o => o.id === sPort)
  const tDef = tNode.inputs.find(i => i.id === tPort)
  if (!sDef || !tDef) {
    ElMessage.error(t('workflow.messages.portInfoChanged'))
    return false
  }
  const stateValidation = stateBus.validateConnection(
    toStatePortDefinition(sDef),
    toStatePortDefinition(tDef)
  )
  if (!stateValidation.ok) {
    ElMessage.error(t('workflow.messages.portIncompatible', { reason: stateValidation.reason }))
    return false
  }
  const sourceKind = sDef.portKind || 'data'
  const targetKind = tDef.portKind || 'data'
  const isStateConnection = sourceKind === 'state-out' && targetKind === 'state-in'

  if (!isStateConnection && !areWorkflowPortsCompatible(sNode, tNode, sDef, tDef)) {
    ElMessage.error(t('workflow.messages.portIncompatibleDetail', { source: sDef.name || sDef.id, target: tDef.name || tDef.id }))
    return false
  }
  if (isDuplicateWorkflowConnection({
    edges: workflowStore.edges,
    sourceId,
    targetId,
    sourcePort: sPort,
    targetPort: tPort,
    sourceSuffix: sSuffix,
    targetSuffix: tSuffix,
  })) {
    ElMessage.warning(t('workflow.messages.connectionAlreadyExists'))
    return false
  }
  if (isStateConnection) {
    const hasCycle = stateBus.detectCycle(sourceId, targetId, workflowStore.edges)
    if (hasCycle) {
      ElMessage.error(t('workflow.messages.stateCycleDetected'))
      return false
    }
  }

  workflowStore.addEdge({
    source: sourceId,
    target: targetId,
    sourceHandle: connection.sourceHandle ?? undefined,
    targetHandle: connection.targetHandle ?? undefined,
    dataPath: { s: sSuffix || undefined, t: tSuffix || undefined }
  })
}

const onEdgeClick = (_evt: EdgeMouseEvent) => {
  emit('nodeSelect', null)
}

const onEdgeContextMenu = (evt: EdgeMouseEvent) => {
  evt.event.preventDefault()
  emit('contextMenu', evt.event, 'edge', evt.edge)
}

const onDragOver = (event: DragEvent) => {
  if (!props.interactive) return
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

const onDrop = (event: DragEvent) => {
  event.preventDefault()
  if (!props.interactive) return
  if (props.readOnly) {
    ElMessage.warning(t('workflow.canvas.frozenNoEdit'))
    return
  }

  // 获取拖拽的数据
  const raw = event.dataTransfer?.getData('text/plain') || '{}'
  const nodeData = JSON.parse(raw) as Record<string, unknown>

  // 获取鼠标在画布中的位置
  const rect = (event.target as HTMLElement).getBoundingClientRect()
  const position = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  }

  // 添加新节点到 store
  const newNode = workflowStore.addNode(nodeDefinitionFromPayload(nodeData, position))

  // 选中新创建的节点
  emit('nodeSelect', newNode.id)
}

const handleKeyDown = (event: KeyboardEvent) => {
  const selected = workflowStore.selectedNode
  if (!selected) return

  // Delete/Backspace node deletion is owned by the document-level
  // useWorkflowKeyboardbindings → deleteSelectedNode path (it gives the user a
  // toast and is the single source of truth). This canvas-scoped handler only
  // owns canvas-specific keystrokes: Escape (deselect) and arrow nudges.

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('nodeSelect', null)
    return
  }

  const step = event.shiftKey ? 20 : 10
  const deltaMap: Record<string, { x: number; y: number }> = {
    ArrowUp: { x: 0, y: -step },
    ArrowDown: { x: 0, y: step },
    ArrowLeft: { x: -step, y: 0 },
    ArrowRight: { x: step, y: 0 },
  }
  const delta = deltaMap[event.key]
  if (!delta) return

  event.preventDefault()
  workflowStore.moveNode(selected.id, {
    x: selected.position.x + delta.x,
    y: selected.position.y + delta.y,
  })
}
</script>

<style scoped>
.vue-flow-container {
  width: 100%;
  height: 100%;
  min-width: 400px;
  min-height: 400px;
  position: relative;
  overflow: hidden;
  outline: none;
}

.vue-flow-container:focus-visible {
  box-shadow: inset 0 0 0 2px var(--lab-accent-info);
}

.vue-flow-editor {
  background: var(--lab-shell-bg);
  border-radius: var(--lab-radius-md);
}


.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}

.empty-content {
  background: var(--lab-panel-bg);
  border: 1px dashed var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  padding: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.empty-icon {
  color: var(--lab-accent-info);
  opacity: 0.6;
}

.empty-content h3 {
  margin: 0;
  color: var(--lab-text-strong);
  font-size: 18px;
  font-weight: 600;
}

.empty-content p {
  margin: 0;
  color: var(--lab-text-muted);
  font-size: 14px;
  line-height: 1.4;
}

/* ── Frozen watermark ── */
.canvas-frozen-watermark {
  position: absolute;
  right: 16px;
  bottom: 16px;
  pointer-events: none;
  user-select: none;
  opacity: 0.55;
  font-size: 12px;
  color: var(--ctp-subtext0);
  background: var(--ctp-surface0);
  padding: 4px 8px;
  border-radius: 4px;
  z-index: 20;
}

/* ── Floating canvas toolbar (undo / redo / auto-layout) ──
   Workflow editing ops live on the canvas itself, freeing the top app bar
   for global/app-level concerns. Mirrors the .canvas-frozen-watermark
   positioning idiom (absolute, z-index 20) but anchored top-right. */
.canvas-floating-toolbar {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  background: var(--lab-panel-bg);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  box-shadow: var(--lab-shadow-md);
}

.canvas-floating-toolbar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: var(--lab-radius-sm);
  background: transparent;
  color: var(--lab-text-primary);
  cursor: pointer;
  transition: background-color var(--lab-transition-fast), color var(--lab-transition-fast);
}

.canvas-floating-toolbar__btn:hover:not(:disabled) {
  background: var(--lab-control-bg-hover);
}

.canvas-floating-toolbar__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.canvas-floating-toolbar__divider {
  width: 1px;
  height: 18px;
  margin: 0 2px;
  background: var(--lab-panel-border);
  flex-shrink: 0;
}

/* Vue Flow Handle 样式覆盖 */
:deep(.vue-flow__handle) {
  width: 12px;
  height: 12px;
  border: 2px solid var(--ctp-base);
  border-radius: 50%;
  background: var(--ctp-overlay1);
  transition: all 0.2s ease;
}

@media (hover: none) and (pointer: coarse) {
  :deep(.vue-flow__handle) {
    width: 16px;
    height: 16px;
  }
}

:deep(.vue-flow__handle:hover) {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  background: var(--lab-accent-info);
}

:deep(.vue-flow__handle.source) {
  right: -6px;
}

:deep(.vue-flow__handle.target) {
  left: -6px;
}

/* Vue Flow Edge 样式覆盖 */
:deep(.vue-flow__edge.selected) {
  stroke: var(--lab-accent-info) !important;
  stroke-width: 3 !important;
}

:deep(.vue-flow__edge.selected .vue-flow__edge-path) {
  stroke: var(--lab-accent-info) !important;
  stroke-width: 3 !important;
}

/* Vue Flow Controls 样式覆盖 */
:deep(.vue-flow__controls) {
  bottom: 20px;
  left: 20px;
}

/* Vue Flow MiniMap 样式覆盖 */
:deep(.vue-flow__minimap) {
  bottom: 20px;
  right: 20px;
  background: var(--lab-panel-bg);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
}

/* Vue Flow 节点样式覆盖 - 确保高度自适应内容 */
:deep(.vue-flow__node) {
  height: auto !important;
  min-height: unset !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
}

:deep(.vue-flow__node.selected) {
  box-shadow: none !important;
}
</style>
