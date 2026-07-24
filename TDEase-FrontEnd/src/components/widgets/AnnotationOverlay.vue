<template>
  <div v-if="hasAnnotations" class="annotation-overlay">
    <div
      v-for="(label, idx) in positionedLabels"
      :key="`${label.type}-${idx}-${label.mz}`"
      class="annotation-label"
      :style="{ left: `${label.x}px`, top: `${label.y}px` }"
    >
      {{ label.type }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import type { AnnotationData } from '@/types/visualization'

interface PixelProjector {
  convertToPixel: (finder: Record<string, unknown>, value: unknown[]) => unknown
}

interface PositionedLabel {
  mz: number
  type: string
  x: number
  y: number
}

interface Props {
  annotationData: AnnotationData | null
  chartInstance: PixelProjector | null
  getYValue?: (mz: number) => number
}

const props = defineProps<Props>()
const positionedLabels = ref<PositionedLabel[]>([])

const hasAnnotations = computed(() => (props.annotationData?.annotations || []).length > 0)

function updatePositions() {
  if (!props.chartInstance || !props.annotationData?.annotations?.length) {
    positionedLabels.value = []
    return
  }
  const labels: PositionedLabel[] = []
  for (const ann of props.annotationData.annotations) {
    const yValue = props.getYValue ? props.getYValue(ann.mz) : 0
    const point = props.chartInstance.convertToPixel(
      { xAxisIndex: 0, yAxisIndex: 0 },
      [ann.mz, yValue]
    )
    if (!Array.isArray(point) || point.length < 2) continue
    labels.push({
      mz: ann.mz,
      type: ann.type,
      x: point[0],
      y: point[1] - 14
    })
  }
  positionedLabels.value = labels
}

watch(
  () => [props.annotationData, props.chartInstance],
  () => updatePositions(),
  { deep: true }
)
</script>

<style scoped>
.annotation-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.annotation-label {
  position: absolute;
  transform: translate(-50%, -100%);
  font-size: 11px;
  color: #d97706;
  background: rgba(255, 246, 230, 0.9);
  border: 1px solid #f59f00;
  border-radius: 3px;
  padding: 2px 4px;
  white-space: nowrap;
}
</style>
