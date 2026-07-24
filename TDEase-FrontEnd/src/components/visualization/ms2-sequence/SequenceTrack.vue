<template>
  <div class="sequence-track">
    <div class="track-header">
      <span class="track-title">Sequence</span>
      <div class="track-controls">
        <el-checkbox v-model="showPrefixIons" size="small" label="N-term ions (a/b/c)" />
        <el-checkbox v-model="showSuffixIons" size="small" label="C-term ions (x/y/z)" />
        <span v-if="sequence.length > 0" class="track-info">{{ sequence.length }} AA</span>
      </div>
    </div>

    <div ref="containerRef" class="sequence-container">
      <!-- Position Ruler -->
      <div class="ruler-row">
        <span class="row-label"></span>
        <div class="ruler-markers" :style="trackStyle">
          <span
            v-for="pos in visiblePositions"
            :key="`ruler-${pos}`"
            class="ruler-marker"
            :class="{ tens: pos % 10 === 0 }"
            :style="cellStyle"
          >
            {{ pos % 10 === 0 ? pos : '' }}
          </span>
        </div>
      </div>

      <!-- Sequence -->
      <div class="sequence-row">
        <span class="row-label">Seq</span>
        <div class="sequence-residues" :style="trackStyle">
          <span
            v-for="residue in visibleResidues"
            :key="residue.position"
            class="residue"
            :class="{
              modified: residue.hasModification,
              highlighted: highlightedResidues.includes(residue.position),
              breakpoint: residue.hasBreakpoint,
            }"
            :style="cellStyle"
            :title="getResidueTooltip(residue)"
            @mouseenter="handleResidueHover(residue.position)"
            @mouseleave="handleResidueLeave"
          >
            {{ residue.char }}
          </span>
        </div>
      </div>

      <!-- N-term ions (a/b/c) as polylines -->
      <template v-if="showPrefixIons">
        <div v-for="ionType in ['c', 'b', 'a']" :key="`prefix-${ionType}`" class="ion-row prefix-ions">
          <span class="row-label ion-label" :class="ionType">{{ ionType }}</span>
          <div class="ion-track" :style="trackStyle">
            <svg :width="trackWidth" :height="24" class="ion-svg">
              <g v-for="pos in visiblePositions" :key="`${ionType}-pos-${pos}`">
                <polyline
                  :points="getFragmentLinePoints(ionType, pos)"
                  :stroke="getFragmentLineColor(ionType, pos)"
                  :stroke-width="getFragmentLineWidth(ionType, pos)"
                  :opacity="getFragmentLineOpacity(ionType, pos)"
                  fill="none"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="fragment-line"
                  :class="{ highlighted: isPositionHighlighted(ionType, pos) }"
                  @mouseenter="handleFragmentLineHover(ionType, pos)"
                  @mouseleave="handleFragmentLeave"
                >
                  <title>{{ getFragmentLineTooltip(ionType, pos) }}</title>
                </polyline>
                <text
                  v-if="hasMultiChargeFragment(ionType, pos)"
                  :x="getFragmentLineLabelX(ionType, pos)"
                  :y="8"
                  text-anchor="middle"
                  font-size="9"
                  :fill="getFragmentLineColor(ionType, pos)"
                  class="charge-label"
                >
                  {{ `${getMaxCharge(ionType, pos)}+` }}
                </text>
              </g>
            </svg>
          </div>
        </div>
      </template>

      <!-- C-term ions (x/y/z) as polylines -->
      <template v-if="showSuffixIons">
        <div v-for="ionType in ['x', 'y', 'z']" :key="`suffix-${ionType}`" class="ion-row suffix-ions">
          <span class="row-label ion-label" :class="ionType">{{ ionType }}</span>
          <div class="ion-track" :style="trackStyle">
            <svg :width="trackWidth" :height="24" class="ion-svg">
              <g v-for="pos in visiblePositions" :key="`${ionType}-pos-${pos}`">
                <polyline
                  :points="getFragmentLinePoints(ionType, pos)"
                  :stroke="getFragmentLineColor(ionType, pos)"
                  :stroke-width="getFragmentLineWidth(ionType, pos)"
                  :opacity="getFragmentLineOpacity(ionType, pos)"
                  fill="none"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="fragment-line"
                  :class="{ highlighted: isPositionHighlighted(ionType, pos) }"
                  @mouseenter="handleFragmentLineHover(ionType, pos)"
                  @mouseleave="handleFragmentLeave"
                >
                  <title>{{ getFragmentLineTooltip(ionType, pos) }}</title>
                </polyline>
                <text
                  v-if="hasMultiChargeFragment(ionType, pos)"
                  :x="getFragmentLineLabelX(ionType, pos)"
                  :y="18"
                  text-anchor="middle"
                  font-size="9"
                  :fill="getFragmentLineColor(ionType, pos)"
                  class="charge-label"
                >
                  {{ `${getMaxCharge(ionType, pos)}+` }}
                </text>
              </g>
            </svg>
          </div>
        </div>
      </template>

      <!-- Modifications -->
      <div v-if="modifications.length > 0" class="mod-row">
        <span class="row-label">Mod</span>
        <div class="mod-markers" :style="trackStyle">
          <span
            v-for="mod in visibleModifications"
            :key="mod.id"
            class="mod-marker"
            :style="cellStyle"
            :title="getModTooltip(mod)"
            @click="handleModClick(mod)"
          >
            {{ getModSymbol(mod) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="track-legend">
      <div class="legend-item">
        <span class="legend-symbol matched">●</span>
        <span class="legend-text">Matched</span>
      </div>
      <div class="legend-item">
        <span class="legend-symbol unmatched">○</span>
        <span class="legend-text">Theoretical</span>
      </div>
      <div class="legend-item">
        <span class="legend-symbol modified">★</span>
        <span class="legend-text">Modified</span>
      </div>
      <div class="legend-item">
        <span class="legend-colors">
          <span class="color-dot a"></span>
          <span class="color-dot b"></span>
          <span class="color-dot c"></span>
          <span class="color-dot x"></span>
          <span class="color-dot y"></span>
          <span class="color-dot z"></span>
        </span>
        <span class="legend-text">Ion Colors</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MatchedFragment, Modification } from '@/composables/ms2-sequence/fragmentation'
import { getCleavageLineX, pickFragmentForInteraction, SEQUENCE_CELL_WIDTH } from './layout'

interface Props {
  sequence: string
  modifications?: Modification[]
  breakpoints?: number[]
  matchedFragments: MatchedFragment[]
  highlightedResidues?: number[]
  highlightedFragments?: MatchedFragment[]
  maxVisibleLength?: number
}

const props = withDefaults(defineProps<Props>(), {
  modifications: () => [],
  breakpoints: () => [],
  highlightedResidues: () => [],
  highlightedFragments: () => [],
  maxVisibleLength: 200,
})

const emit = defineEmits<{
  'residue-hover': [position: number]
  'residue-leave': []
  'fragment-hover': [fragment: MatchedFragment]
  'fragment-leave': []
  'mod-click': [mod: Modification]
}>()

const containerRef = ref<HTMLDivElement>()
const showPrefixIons = ref(true)
const showSuffixIons = ref(true)

const cellWidth = SEQUENCE_CELL_WIDTH
const cellStyle = {
  width: `${cellWidth}px`,
  minWidth: `${cellWidth}px`,
  padding: '0',
  boxSizing: 'border-box' as const,
}

const visibleRange = computed(() => {
  const length = props.sequence.length
  if (length <= props.maxVisibleLength) return { start: 0, end: length }
  return { start: 0, end: props.maxVisibleLength }
})

const visiblePositions = computed(() => {
  const { start, end } = visibleRange.value
  return Array.from({ length: end - start }, (_, i) => start + i + 1)
})

const trackWidth = computed(() => visiblePositions.value.length * cellWidth)
const trackStyle = computed(() => ({
  width: `${trackWidth.value}px`,
  minWidth: `${trackWidth.value}px`,
}))

interface ResidueView {
  position: number
  char: string
  hasModification: boolean
  hasBreakpoint: boolean
  modifications: Modification[]
}

const residues = computed<ResidueView[]>(() => {
  const seq = props.sequence
  if (!seq) return []

  const breakpointSet = new Set(props.breakpoints)

  return Array.from(seq).map((char, idx) => {
    const position = idx + 1
    const mods = props.modifications.filter(mod => {
      const start = mod.position
      const end = mod.positionEnd ?? start
      return position >= start && position <= end
    })

    return {
      position,
      char,
      hasModification: mods.length > 0,
      hasBreakpoint: breakpointSet.has(position),
      modifications: mods,
    }
  })
})

const visibleResidues = computed(() => {
  const { start, end } = visibleRange.value
  return residues.value.slice(start, end)
})

const visibleModifications = computed(() => {
  const { start, end } = visibleRange.value
  return props.modifications.filter(mod => {
    const modStart = mod.position
    const modEnd = mod.positionEnd ?? modStart
    return modEnd >= start + 1 && modStart <= end
  })
})

const prefixIonsByType = computed(() => {
  const ions: Record<string, MatchedFragment[]> = { a: [], b: [], c: [] }
  props.matchedFragments
    .filter(f => ['a', 'b', 'c'].includes(f.ionType))
    .forEach(f => {
      if (!ions[f.ionType]) ions[f.ionType] = []
      ions[f.ionType].push(f)
    })

  Object.keys(ions).forEach(type => {
    ions[type].sort((a, b) => a.position - b.position)
  })

  return ions
})

const suffixIonsByType = computed(() => {
  const ions: Record<string, MatchedFragment[]> = { x: [], y: [], z: [] }
  props.matchedFragments
    .filter(f => ['x', 'y', 'z'].includes(f.ionType))
    .forEach(f => {
      if (!ions[f.ionType]) ions[f.ionType] = []
      ions[f.ionType].push(f)
    })

  Object.keys(ions).forEach(type => {
    ions[type].sort((a, b) => a.position - b.position)
  })

  return ions
})

// 120° elbow: diagonal + vertical. Use 30° vs horizontal for the diagonal.
const elbowDx = computed(() => cellWidth * 0.6)
const diagDx = computed(() => elbowDx.value * 0.5)
const diagDy = computed(() => elbowDx.value * 0.866)

function getFragmentLineX(position: number): number {
  const { start } = visibleRange.value
  return getCleavageLineX(position, start, cellWidth)
}

function getFragmentLinePoints(ionType: string, position: number): string {
  const isUp = ['a', 'b', 'c'].includes(ionType)
  // b/c: up-left, a: up-right; y/z: down-right, x: down-left
  const isLeft = ionType === 'b' || ionType === 'c' || ionType === 'x'

  const x0 = getFragmentLineX(position)
  const y0 = isUp ? 22 : 2

  const y2 = isUp ? 4 : 20
  const x2 = isLeft ? x0 - elbowDx.value : x0 + elbowDx.value

  const x1 = isLeft ? x0 - diagDx.value : x0 + diagDx.value
  const y1 = isUp ? 12 - diagDy.value : 12 + diagDy.value

  return `${x0},${y0} ${x1},${y1} ${x2},${y2}`
}

function getFragmentsAtPosition(ionType: string, position: number): MatchedFragment[] {
  const isPrefix = ['a', 'b', 'c'].includes(ionType)
  const ions = isPrefix ? prefixIonsByType.value : suffixIonsByType.value
  return (ions[ionType] || []).filter(f => f.position === position)
}

function getFragmentLineColor(ionType: string, position: number): string {
  const fragments = getFragmentsAtPosition(ionType, position)
  if (fragments.length === 0) return '#e0e0e0'
  const hasMatched = fragments.some(f => f.isMatched)
  return getIonColor(ionType, hasMatched)
}

function getFragmentLineWidth(ionType: string, position: number): number {
  if (isPositionHighlighted(ionType, position)) return 3
  const fragments = getFragmentsAtPosition(ionType, position)
  const hasMatched = fragments.some(f => f.isMatched)
  return hasMatched ? 2 : 1
}

function getFragmentLineOpacity(ionType: string, position: number): number {
  const fragments = getFragmentsAtPosition(ionType, position)
  if (fragments.length === 0) return 0.2
  const hasMatched = fragments.some(f => f.isMatched)
  return hasMatched ? 1 : 0.3
}

function isPositionHighlighted(ionType: string, position: number): boolean {
  const fragments = getFragmentsAtPosition(ionType, position)
  return fragments.some(f => isFragmentHighlighted(f))
}

function hasMultiChargeFragment(ionType: string, position: number): boolean {
  const fragments = getFragmentsAtPosition(ionType, position)
  return fragments.some(f => f.charge > 1 && f.isMatched)
}

function getMaxCharge(ionType: string, position: number): number {
  const fragments = getFragmentsAtPosition(ionType, position)
  const charges = fragments.filter(f => f.isMatched).map(f => f.charge)
  return charges.length > 0 ? Math.max(...charges) : 1
}

function getFragmentLineLabelX(ionType: string, position: number): number {
  const isLeft = ionType === 'b' || ionType === 'c' || ionType === 'x'
  const x0 = getFragmentLineX(position)
  return isLeft ? x0 - elbowDx.value * 0.65 : x0 + elbowDx.value * 0.65
}

function getFragmentLineTooltip(ionType: string, position: number): string {
  const fragments = getFragmentsAtPosition(ionType, position)
  if (fragments.length === 0) return `${ionType}${position} - No fragments`

  const parts: string[] = []
  fragments.forEach(f => {
    const label = `${f.ionType}${f.position}^${f.charge}+${f.neutralLoss ? `-${f.neutralLoss}` : ''}`
    parts.push(label)
    parts.push(`  Theoretical: ${f.theoreticalMz.toFixed(4)}`)
    if (f.isMatched && f.matchedPeak) {
      parts.push(`  Observed: ${f.matchedPeak.mz.toFixed(4)}`)
      parts.push(`  Error: ${f.matchErrorPpm?.toFixed(2)} ppm`)
    }
  })
  return parts.join('\n')
}

function handleFragmentLineHover(ionType: string, position: number) {
  const fragments = getFragmentsAtPosition(ionType, position)
  const fragment = pickFragmentForInteraction(fragments)
  if (!fragment) return
  emit('fragment-hover', fragment)
}

function getIonColor(ionType: string, isMatched: boolean): string {
  if (!isMatched) return '#dcdfe6'
  const colors: Record<string, string> = {
    a: '#9c27b0',
    b: '#2196f3',
    c: '#00bcd4',
    x: '#ff9800',
    y: '#4caf50',
    z: '#e91e63',
  }
  return colors[ionType] || '#606266'
}

function getModSymbol(mod: Modification): string {
  const symbols: Record<string, string> = {
    ptm: '★',
    massShift: '◆',
    label: '■',
  }
  return symbols[mod.type] || '■'
}

function getResidueTooltip(residue: ResidueView): string {
  const parts = [`Position ${residue.position}: ${residue.char}`]
  if (residue.modifications.length > 0) {
    parts.push('Modifications:')
    residue.modifications.forEach(m => {
      const sign = m.massShift >= 0 ? '+' : ''
      parts.push(`  ${m.name} (${sign}${m.massShift.toFixed(4)} Da)`)
    })
  }
  return parts.join('\n')
}

function getModTooltip(mod: Modification): string {
  const parts = [`${mod.name}`]
  parts.push(`Position: ${mod.position}${mod.positionEnd ? `-${mod.positionEnd}` : ''}`)
  const sign = mod.massShift >= 0 ? '+' : ''
  parts.push(`Mass shift: ${sign}${mod.massShift.toFixed(4)} Da`)
  if (mod.composition) parts.push(`Composition: ${mod.composition}`)
  return parts.join('\n')
}

function isFragmentHighlighted(fragment: MatchedFragment): boolean {
  return props.highlightedFragments.some(
    f => f.ionType === fragment.ionType && f.position === fragment.position && f.charge === fragment.charge
  )
}

function handleResidueHover(position: number) {
  emit('residue-hover', position)
}

function handleResidueLeave() {
  emit('residue-leave')
}

function handleFragmentLeave() {
  emit('fragment-leave')
}

function handleModClick(mod: Modification) {
  emit('mod-click', mod)
}
</script>

<style scoped>
.sequence-track {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

.track-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.track-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.track-controls {
  display: flex;
  gap: 16px;
  align-items: center;
}

.track-info {
  font-size: 12px;
  color: #909399;
}

.sequence-container {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  overflow-x: auto;
  overflow-y: hidden;
}

.ruler-row,
.sequence-row,
.ion-row,
.mod-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 24px;
}

.row-label {
  min-width: 40px;
  font-size: 11px;
  font-weight: 600;
  color: #606266;
  text-align: right;
  flex-shrink: 0;
}

.row-label.ion-label {
  font-size: 12px;
  font-weight: 700;
}

.row-label.ion-label.a { color: #9c27b0; }
.row-label.ion-label.b { color: #2196f3; }
.row-label.ion-label.c { color: #00bcd4; }
.row-label.ion-label.x { color: #ff9800; }
.row-label.ion-label.y { color: #4caf50; }
.row-label.ion-label.z { color: #e91e63; }

.ruler-markers,
.sequence-residues,
.mod-markers {
  display: flex;
  gap: 0;
  flex: 0 0 auto;
}

.ion-track {
  flex: 0 0 auto;
  overflow: hidden;
}

.ion-svg {
  display: block;
}

.fragment-line {
  cursor: pointer;
  transition: all 0.15s;
}

.fragment-line:hover {
  stroke-width: 3;
  filter: brightness(1.2);
}

.fragment-line.highlighted {
  filter: drop-shadow(0 0 3px #fbbf24);
}

.charge-label {
  font-weight: 600;
  pointer-events: none;
}

.ruler-marker {
  text-align: center;
  font-size: 10px;
  color: #c0c4cc;
}

.ruler-marker.tens {
  color: #606266;
  font-weight: 600;
}

.residue {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  border-radius: 3px;
  font-size: 13px;
}

.residue:hover {
  background: #f0f9ff;
}

.residue.modified {
  background: #fdf6ec;
  color: #e6a23c;
  font-weight: 600;
}

.residue.highlighted {
  background: #fef0c7 !important;
  color: #d97706 !important;
  font-weight: 700;
  box-shadow: 0 0 0 2px #fbbf24;
}

.residue.breakpoint {
  border-right: 2px solid #67c23a;
  margin-right: 4px;
}

.mod-row {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid #ebeef5;
}

.mod-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #e6a23c;
  font-size: 12px;
  transition: all 0.15s;
}

.mod-marker:hover {
  transform: scale(1.3);
  color: #d97706;
}

.track-legend {
  display: flex;
  gap: 16px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
  font-size: 11px;
}

.legend-item {
  display: flex;
  gap: 4px;
  align-items: center;
}

.legend-symbol {
  font-size: 12px;
}

.legend-symbol.matched { color: #4caf50; }
.legend-symbol.unmatched { color: #dcdfe6; }
.legend-symbol.modified { color: #e6a23c; }

.legend-text {
  color: #606266;
}

.legend-colors {
  display: flex;
  gap: 2px;
}

.color-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.color-dot.a { background: #9c27b0; }
.color-dot.b { background: #2196f3; }
.color-dot.c { background: #00bcd4; }
.color-dot.x { background: #ff9800; }
.color-dot.y { background: #4caf50; }
.color-dot.z { background: #e91e63; }
</style>
