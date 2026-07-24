/**
 * 交互管理模块
 * 处理序列、谱图、碎片之间的交互高亮逻辑
 */

import type { MatchedFragment, SpectrumPeak } from './fragmentation'

export interface InteractionState {
  // 悬停状态
  hoveredFragment?: MatchedFragment
  hoveredPeak?: SpectrumPeak
  hoveredResidue?: number // 悬停的残基位置 (1-based)

  // 选择状态
  selectedFragment?: MatchedFragment
  selectedPeakIndex?: number
  selectedResidue?: number

  // 高亮状态（计算得出）
  highlightedFragments: MatchedFragment[]
  highlightedPeaks: number[] // 峰索引列表
  highlightedResidues: number[] // 残基位置列表 (1-based)
}

/**
 * 交互管理器
 */
export class InteractionManager {
  /**
   * 悬停残基时，高亮包含该残基的所有碎片
   */
  highlightByResidue(
    residuePosition: number,
    fragments: MatchedFragment[]
  ): InteractionState {
    const highlightedFragments = fragments.filter((f) => {
      const [start, end] = f.sequenceRange
      return residuePosition >= start && residuePosition <= end
    })

    const highlightedPeaks = highlightedFragments
      .filter((f) => f.isMatched && f.matchedPeak)
      .map((f) => f.matchedPeak!.index)

    return {
      hoveredResidue: residuePosition,
      highlightedFragments,
      highlightedPeaks,
      highlightedResidues: [residuePosition],
    }
  }

  /**
   * 悬停谱峰时，高亮对应的碎片和序列位置
   */
  highlightByPeak(
    peak: SpectrumPeak,
    fragments: MatchedFragment[]
  ): InteractionState {
    const matchedFragments = fragments.filter(
      (f) => f.isMatched && f.matchedPeak?.index === peak.index
    )

    if (matchedFragments.length === 0) {
      return {
        hoveredPeak: peak,
        highlightedFragments: [],
        highlightedPeaks: [peak.index],
        highlightedResidues: [],
      }
    }

    // 获取所有匹配碎片覆盖的序列位置
    const highlightedResidues: number[] = []
    for (const fragment of matchedFragments) {
      const [start, end] = fragment.sequenceRange
      for (let i = start; i <= end; i++) {
        if (!highlightedResidues.includes(i)) {
          highlightedResidues.push(i)
        }
      }
    }

    return {
      hoveredPeak: peak,
      highlightedFragments: matchedFragments,
      highlightedPeaks: [peak.index],
      highlightedResidues,
    }
  }

  /**
   * 悬停碎片时，同时高亮序列和谱图
   */
  highlightByFragment(fragment: MatchedFragment): InteractionState {
    const [start, end] = fragment.sequenceRange
    const highlightedResidues: number[] = []
    for (let i = start; i <= end; i++) {
      highlightedResidues.push(i)
    }

    const highlightedPeaks =
      fragment.isMatched && fragment.matchedPeak ? [fragment.matchedPeak.index] : []

    return {
      hoveredFragment: fragment,
      highlightedFragments: [fragment],
      highlightedPeaks,
      highlightedResidues,
    }
  }

  /**
   * 清除所有高亮
   */
  clearHighlight(): InteractionState {
    return {
      highlightedFragments: [],
      highlightedPeaks: [],
      highlightedResidues: [],
    }
  }
}
