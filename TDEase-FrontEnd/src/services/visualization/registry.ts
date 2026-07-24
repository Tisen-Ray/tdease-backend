import type { Component } from 'vue'

import {
  viewerRegistry,
  type ViewerRegistration,
} from '@/services/visualization/ViewerRegistry'

export interface VisualizationRegistration {
  id: string
  version: string
  kind: 'frontend-view'
  slot: 'visualization'
  type: string
  label: string
  component: Component
  category?: ViewerRegistration['category']
  icon?: string
  defaultConfig?: Record<string, unknown>
  semanticTypes?: string[]
}

export interface VisualizationValidationResult {
  valid: boolean
  errors: string[]
}

const BUILTIN_PREFIX = 'builtin.'
const builtinVisualizations = new Map<string, VisualizationRegistration>()
const overrideVisualizations = new Map<string, VisualizationRegistration>()

function isVisualizationRegistration(registration: ViewerRegistration): boolean {
  return !registration.id.startsWith('_node_')
}

function toVisualization(
  registration: ViewerRegistration,
  override?: Partial<Pick<VisualizationRegistration, 'id' | 'version'>>,
): VisualizationRegistration {
  return {
    id: override?.id ?? `${BUILTIN_PREFIX}${registration.id}`,
    version: override?.version ?? '1.0.0',
    kind: 'frontend-view',
    slot: 'visualization',
    type: registration.id,
    label: registration.label,
    component: registration.component,
    category: registration.category,
    icon: registration.icon,
    defaultConfig: registration.defaultConfig,
    semanticTypes: registration.semanticTypes,
  }
}

export function ensureVisualizationRegistryBootstrapped(): void {
  viewerRegistry.discover()

  builtinVisualizations.clear()

  for (const registration of viewerRegistry.list()) {
    if (!isVisualizationRegistration(registration)) {
      continue
    }
    builtinVisualizations.set(registration.id, toVisualization(registration))
  }
}

function getEffectiveVisualization(type: string): VisualizationRegistration | undefined {
  ensureVisualizationRegistryBootstrapped()
  return overrideVisualizations.get(type) ?? builtinVisualizations.get(type)
}

export function registerVisualization(registration: VisualizationRegistration): void {
  ensureVisualizationRegistryBootstrapped()
  overrideVisualizations.set(registration.type, registration)
}

export function unregisterVisualization(type: string): boolean {
  ensureVisualizationRegistryBootstrapped()
  return overrideVisualizations.delete(type)
}

export function getVisualization(type: string): VisualizationRegistration | undefined {
  return getEffectiveVisualization(type)
}

export function getVisualizationComponent(type: string): Component | undefined {
  return getVisualization(type)?.component
}

export function getVisualizationTypes(): string[] {
  return listVisualizations().map((registration) => registration.type)
}

export function hasVisualization(type: string): boolean {
  return Boolean(getEffectiveVisualization(type))
}

export function listVisualizations(): VisualizationRegistration[] {
  ensureVisualizationRegistryBootstrapped()
  const merged = new Map(builtinVisualizations)
  for (const [type, registration] of overrideVisualizations.entries()) {
    merged.set(type, registration)
  }
  return Array.from(merged.values())
}

export function listVisualizationsByCategory(
  category: NonNullable<VisualizationRegistration['category']>,
): VisualizationRegistration[] {
  return listVisualizations().filter((registration) => registration.category === category)
}

export function getDefaultConfig(type: string): Record<string, unknown> | undefined {
  return getVisualization(type)?.defaultConfig
}

export function validateConfig(
  type: string,
  _config: Record<string, unknown>,
): VisualizationValidationResult {
  if (!hasVisualization(type)) {
    return {
      valid: false,
      errors: [`Unknown visualization type: ${type}`],
    }
  }

  return {
    valid: true,
    errors: [],
  }
}
