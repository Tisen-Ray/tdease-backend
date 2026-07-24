/**
 * Buffer 编辑模式管理
 * 用于序列和修饰的临时编辑，支持应用/放弃操作
 */

import type { Modification, SpectrumPeak } from './fragmentation'

export interface SequenceData {
  value: string
  length: number
  firstPosition?: number
  lastPosition?: number
}

export interface MS2SpectrumData {
  peaks: SpectrumPeak[]
  precursorMz: number
  precursorCharge: number
  retentionTime?: number
  collisionEnergy?: number
  activationMethod?: string
}

export interface MS2SequenceViewerInput {
  sequence: SequenceData
  spectrum: MS2SpectrumData
  modifications: Modification[]
  breakpoints?: number[]
  metadata?: {
    prsmId?: number
    spectrumId?: number
    proteinAccession?: string
    precursorMz?: number
    precursorCharge?: number
    retentionTime?: number
    source?: string
  }
}

export interface ViewerConfig {
  ionTypes: ('a' | 'b' | 'c' | 'x' | 'y' | 'z')[]
  maxFragmentCharge: number
  tolerancePpm: number
  toleranceDa?: number
  matchType: 'best' | 'all' // IPSA 最佳匹配 vs 传统全匹配
  minIntensity?: number
  minRelativeIntensity?: number
  showMatchedPeaks: boolean
  showUnmatchedPeaks: boolean
  showNeutralLosses: boolean
  enableBuffer: boolean
}

export const DEFAULT_CONFIG: ViewerConfig = {
  ionTypes: ['b', 'y'],
  maxFragmentCharge: 2,
  tolerancePpm: 20,
  matchType: 'best', // 默认使用 IPSA 最佳匹配策略
  showMatchedPeaks: true,
  showUnmatchedPeaks: true,
  showNeutralLosses: true,
  enableBuffer: true,
}

export interface BufferState {
  isEditing: boolean
  hasUnsavedChanges: boolean
  originalInput: MS2SequenceViewerInput | null
  bufferInput: MS2SequenceViewerInput | null
}

/**
 * Buffer 编辑管理器
 */
export class EditBuffer {
  private originalInput: MS2SequenceViewerInput | null = null
  private bufferInput: MS2SequenceViewerInput | null = null
  private isDirty = false

  /**
   * 开始编辑（保存原始状态）
   */
  startEdit(input: MS2SequenceViewerInput): void {
    this.originalInput = JSON.parse(JSON.stringify(input))
    this.bufferInput = JSON.parse(JSON.stringify(input))
    this.isDirty = false
  }

  /**
   * 修改序列
   */
  editSequence(newSequence: string): void {
    if (!this.bufferInput) return
    this.bufferInput.sequence.value = newSequence
    this.bufferInput.sequence.length = newSequence.length
    this.isDirty = true
  }

  /**
   * 添加修饰
   */
  addModification(mod: Modification): void {
    if (!this.bufferInput) return
    this.bufferInput.modifications.push({ ...mod })
    this.isDirty = true
  }

  /**
   * 移除修饰
   */
  removeModification(modId: string): void {
    if (!this.bufferInput) return
    this.bufferInput.modifications = this.bufferInput.modifications.filter(m => m.id !== modId)
    this.isDirty = true
  }

  /**
   * 更新修饰
   */
  updateModification(modId: string, updates: Partial<Modification>): void {
    if (!this.bufferInput) return
    const index = this.bufferInput.modifications.findIndex(m => m.id === modId)
    if (index >= 0) {
      this.bufferInput.modifications[index] = { ...this.bufferInput.modifications[index], ...updates }
      this.isDirty = true
    }
  }

  /**
   * 应用编辑
   */
  apply(): MS2SequenceViewerInput | null {
    if (!this.bufferInput) return null
    this.originalInput = JSON.parse(JSON.stringify(this.bufferInput))
    const result = this.bufferInput
    this.bufferInput = null
    this.isDirty = false
    return result
  }

  /**
   * 放弃编辑
   */
  discard(): MS2SequenceViewerInput | null {
    this.bufferInput = null
    this.isDirty = false
    return this.originalInput
  }

  /**
   * 获取当前状态
   */
  getCurrent(): MS2SequenceViewerInput | null {
    return this.bufferInput || this.originalInput
  }

  /**
   * 是否有未应用的修改
   */
  hasUnsavedChanges(): boolean {
    return this.isDirty
  }

  /**
   * 是否在编辑模式
   */
  isEditing(): boolean {
    return this.bufferInput !== null
  }

  /**
   * 重置为原始状态
   */
  reset(): void {
    this.bufferInput = null
    this.isDirty = false
  }
}

/**
 * 创建 Buffer 状态
 */
export function createBufferState(): BufferState {
  return {
    isEditing: false,
    hasUnsavedChanges: false,
    originalInput: null,
    bufferInput: null,
  }
}
