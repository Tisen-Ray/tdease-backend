import type { Component } from 'vue'
import { canonicalizeViewerType } from './viewerTypeAliases'

// ---------------------------------------------------------------------------
// Accepts Contract — explicit declaration of what each viewer consumes.
// matchRules remains for legacy fallback scoring.
// ---------------------------------------------------------------------------

export interface DatasetAccept {
  /** Logical id within the viewer (used by dataMapping.source). */
  id: string
  /** Dataset kind (peak_table, annotation_table, error_scatter, …). */
  kind: string
  /** Column names the viewer requires for this dataset. */
  requiredColumns?: string[]
}

export interface AcceptContract {
  /** The dataset kinds this viewer can display. */
  datasets: DatasetAccept[]
  /** Whether the viewer supports multiple datasets (mirror/overlay/comparison). */
  supportsMultipleDatasets?: boolean
}

interface ResolvableNode {
  id?: string
  type: string
  executionMode?: string
}

export interface ViewerMatchRule {
  toolId?: string | RegExp
  executionMode?: string
  dataType?: string
  semanticType?: string
  columnPattern?: Array<{
    name: string | RegExp
    type?: 'numeric' | 'categorical' | 'any'
  }>
  portOutputType?: string
  fileExtension?: string
  priority?: number
}

export interface ViewerRegistration {
  id: string
  component: Component
  matchRules: ViewerMatchRule[]
  /** Explicit accepts contract — describes what datasets this viewer consumes. */
  accepts?: AcceptContract
  semanticTypes?: string[]
  defaultConfig?: Record<string, unknown>
  capabilities?: string[]
  label: string
  icon?: string
  category?: 'plot' | 'table' | 'scientific'
  nodeType?: string
  columnDetectPatterns?: Record<string, string[]>
  selectionKeyCandidates?: string[]
}

export interface ViewerContext {
  toolId?: string
  executionMode?: string
  dataType?: string
  kind?: string
  semanticType?: string
  columnNames?: string[]
  columnTypes?: Array<{ name: string; type: string }>
  portOutputType?: string
  fileExtension?: string
  displayHint?: {
    visualizationType?: string
  }
  visualizationConfig?: {
    type?: string
    config?: Record<string, unknown>
  }
}

export class ViewerRegistry {
  private viewers = new Map<string, ViewerRegistration>()
  private nodeTypeMap = new Map<string, string>()

  register(registration: ViewerRegistration): void {
    this.viewers.set(registration.id, registration)
    if (registration.nodeType) {
      this.nodeTypeMap.set(registration.nodeType, registration.id)
    }
  }

  unregister(viewerId: string): boolean {
    const existing = this.viewers.get(viewerId)
    if (!existing) {
      return false
    }

    this.viewers.delete(viewerId)
    if (existing.nodeType) {
      this.nodeTypeMap.delete(existing.nodeType)
    }
    return true
  }

  has(viewerId: string): boolean {
    return this.viewers.has(viewerId)
  }

  list(): ViewerRegistration[] {
    return Array.from(this.viewers.values())
  }

  resolve(ctx: ViewerContext): ViewerRegistration | undefined {
    if (ctx.visualizationConfig?.type) {
      const explicit = this.viewers.get(canonicalizeViewerType(ctx.visualizationConfig.type) || ctx.visualizationConfig.type)
      if (explicit) return explicit
    }

    if (ctx.kind) {
      const byKind = this.viewers.get(ctx.kind)
      if (byKind) return byKind
    }

    if (ctx.semanticType) {
      for (const registration of this.viewers.values()) {
        if (registration.semanticTypes?.includes(ctx.semanticType)) return registration
      }
    }

    const displayHintType = ctx.displayHint?.visualizationType

    const scored = Array.from(this.viewers.values())
      .map((registration) => {
        let score = this.scoreViewer(registration, ctx)
        if (
          displayHintType &&
          score > 0 &&
          (registration.id === displayHintType || registration.id.includes(displayHintType))
        ) {
          score += 200
        }
        return { registration, score }
      })
      .filter(({ score }) => score > 0)
      .sort((left, right) => right.score - left.score)

    return scored[0]?.registration ?? this.viewers.get('table')
  }

  resolveNodeType(node: ResolvableNode): string {
    if (node.executionMode === 'interactive') return 'interactive'
    if (node.type === 'filter') return 'filter'

    const matched = this.resolve({
      toolId: node.type,
      executionMode: node.executionMode,
    })

    if (matched?.nodeType) return matched.nodeType
    if (['custom', 'input', 'process', 'output', 'tool'].includes(node.type)) {
      return node.type
    }
    return 'tool'
  }

  discover(): void {
    this.viewers.clear()
    this.nodeTypeMap.clear()

    for (const path of Object.keys(_discoveryModules)) {
      const registration = (_discoveryModules[path] as { default?: ViewerRegistration }).default
      if (registration?.id) {
        this.register(registration)
      }
    }

    if (import.meta.env.DEV) {
      console.log(
        `[ViewerRegistry] discovered ${this.viewers.size} viewers from ${Object.keys(_discoveryModules).length} modules`,
        [...this.viewers.keys()],
      )
    }
  }

  /** Self-healing: re-discover if the registry is empty (e.g. after HMR cascade). */
  private ensureDiscovered(): void {
    if (this.viewers.size === 0) {
      this.discover()
    }
  }

  getNodeTypeMap(): Record<string, Component> {
    this.ensureDiscovered()
    const map: Record<string, Component> = {}
    const toolComponent = this.viewers.get('_node_tool')?.component
    const interactiveComponent = this.viewers.get('_node_interactive')?.component
    const filterComponent = this.viewers.get('_node_filter')?.component

    if (toolComponent) map.tool = toolComponent
    if (interactiveComponent) map.interactive = interactiveComponent
    if (filterComponent) map.filter = filterComponent

    if (map.tool) {
      for (const alias of ['custom', 'input', 'process', 'output']) {
        map[alias] = map.tool
      }
    }

    return map
  }

  getColumnDetectPatterns(viewerId: string): Record<string, string[]> | undefined {
    return this.viewers.get(viewerId)?.columnDetectPatterns
  }

  getSelectionKeyCandidates(viewerId: string): string[] {
    return this.viewers.get(viewerId)?.selectionKeyCandidates ?? []
  }

  getAcceptsContract(viewerId: string): AcceptContract | undefined {
    return this.viewers.get(viewerId)?.accepts
  }

  get(viewerId: string): ViewerRegistration | undefined {
    return this.viewers.get(viewerId)
  }

  getByViewer(viewer: string, version: number): ViewerRegistration | undefined {
    // 1. Exact match on viewer@v{version}
    const key = `${viewer}@v${version}`
    for (const reg of this.viewers.values()) {
      if (reg.id === key) return reg
    }

    // 2. Exact match on viewer name alone
    for (const reg of this.viewers.values()) {
      if (reg.id === viewer) return reg
    }

    // 3. Canonical alias match (e.g. fragment_spectrum → fragment_matching)
    const canonical = canonicalizeViewerType(viewer)
    if (canonical && canonical !== viewer) {
      return this.getByViewer(canonical, version)
    }

    // 4. Fallback: resolve via scoring — builds ViewerContext from viewer+version
    return this.resolve({
      kind: viewer,
      displayHint: { visualizationType: viewer },
    })
  }

  private scoreViewer(registration: ViewerRegistration, ctx: ViewerContext): number {
    if (registration.matchRules.length === 0) return 0

    let bestScore = 0
    for (const rule of registration.matchRules) {
      const ruleScore = this.scoreRule(rule, ctx)
      if (ruleScore > bestScore) {
        bestScore = ruleScore
      }
    }
    return bestScore
  }

  private scoreRule(rule: ViewerMatchRule, ctx: ViewerContext): number {
    let score = 0
    let conditions = 0
    let matched = 0

    if (rule.toolId) {
      conditions++
      const toolId = ctx.toolId ?? ''
      if (typeof rule.toolId === 'string') {
        if (toolId === rule.toolId) {
          matched++
          score += 100
        } else if (toolId.includes(rule.toolId)) {
          matched++
          score += 70
        }
      } else if (rule.toolId.test(toolId)) {
        matched++
        score += 70
      }
    }

    if (rule.executionMode) {
      conditions++
      if (ctx.executionMode === rule.executionMode) {
        matched++
        score += 80
      }
    }

    if (rule.dataType) {
      conditions++
      if (ctx.dataType === rule.dataType) {
        matched++
        score += 50
      }
    }

    if (rule.semanticType) {
      conditions++
      const semanticType = ctx.semanticType ?? ''
      if (semanticType === rule.semanticType || semanticType.includes(rule.semanticType)) {
        matched++
        score += 40
      }
    }

    if (rule.columnPattern && ctx.columnNames) {
      conditions++
      const columnNames = ctx.columnNames.map((name) => name.toLowerCase())
      const columnTypes = ctx.columnTypes ?? []
      let columnMatches = 0

      for (const pattern of rule.columnPattern) {
        const found = columnNames.find((name) =>
          typeof pattern.name === 'string'
            ? name === pattern.name || name.includes(pattern.name)
            : pattern.name.test(name),
        )

        if (!found) {
          continue
        }

        if (pattern.type && pattern.type !== 'any') {
          const columnType = columnTypes.find((entry) => entry.name.toLowerCase() === found)
          if (columnType?.type === 'number' && pattern.type === 'numeric') {
            columnMatches++
          } else if (columnType?.type !== 'number' && pattern.type === 'categorical') {
            columnMatches++
          }
        } else {
          columnMatches++
        }
      }

      if (columnMatches >= rule.columnPattern.length) {
        matched++
        score += 30 + columnMatches * 10
      }
    }

    if (rule.portOutputType) {
      conditions++
      if (ctx.portOutputType === rule.portOutputType) {
        matched++
        score += 25
      }
    }

    if (rule.fileExtension) {
      conditions++
      const extension = ctx.fileExtension ?? ''
      if (extension === rule.fileExtension || extension.endsWith(rule.fileExtension)) {
        matched++
        score += 30
      }
    }

    if (matched < conditions) {
      return 0
    }

    score += rule.priority ?? 50
    return score
  }
}

const _discoveryModules = import.meta.glob(
  '@/services/visualization/registrations/*.ts',
  { eager: true },
)

export const viewerRegistry = new ViewerRegistry()
