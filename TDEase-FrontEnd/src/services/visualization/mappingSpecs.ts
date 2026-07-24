import type { AxisMapping, VisualizationType } from '@/types/visualization'

/**
 * 单个轴/视觉通道的列映射配置。
 *
 * 注意：axisKey 复用 AxisMapping 的键（x/y/z/color/size），
 * 这样可以继续用 AxisMapping 作为对上游的统一类型。
 */
export interface AxisFieldSpec {
  axisKey: keyof AxisMapping
  label: string
  /**
   * 是否只允许数值型列（用于下拉时附带提示，不做强校验）。
   */
  numericPreferred?: boolean
  /**
   * 是否可以不填。
   */
  optional?: boolean
}

export interface VisualizationMappingSpec {
  type: VisualizationType
  /**
   * 需要展示的字段（按 UI 顺序）。
   */
  fields: AxisFieldSpec[]
}

const SCATTER_SPEC: VisualizationMappingSpec = {
  type: 'scatter',
  fields: [
    { axisKey: 'x', label: 'X Axis', numericPreferred: true },
    { axisKey: 'y', label: 'Y Axis', numericPreferred: true },
    { axisKey: 'z', label: 'Z Axis (3D)', numericPreferred: true, optional: true },
    { axisKey: 'color', label: 'Color By', optional: true },
    { axisKey: 'size', label: 'Size By', numericPreferred: true, optional: true },
  ],
}

const FEATUREMAP_SPEC: VisualizationMappingSpec = {
  type: 'featuremap',
  fields: [
    // 这里用 x/z/y/color 这组键，在 UI 文案上展示为 Start/End/Mass/Intensity
    { axisKey: 'x', label: 'Start Time', numericPreferred: true },
    { axisKey: 'z', label: 'End Time', numericPreferred: true },
    { axisKey: 'y', label: 'Mass', numericPreferred: true },
    { axisKey: 'color', label: 'Intensity (Color)', numericPreferred: true, optional: true },
  ],
}

const SPECTRUM_SPEC: VisualizationMappingSpec = {
  type: 'spectrum',
  fields: [
    { axisKey: 'x', label: 'm/z', numericPreferred: true },
    { axisKey: 'y', label: 'Intensity', numericPreferred: true },
  ],
}

/**
 * 根据可视化类型获取列映射规格。
 *
 * 暂时只对 scatter / featuremap / spectrum 启用通用列映射抽屉，
 * 其他类型可以完全依赖各自 Viewer 内部配置。
 */
export function getMappingSpec(type: VisualizationType): VisualizationMappingSpec | null {
  switch (type) {
    case 'scatter':
      return SCATTER_SPEC
    case 'featuremap':
      return FEATUREMAP_SPEC
    case 'spectrum':
      return SPECTRUM_SPEC
    default:
      return null
  }
}

