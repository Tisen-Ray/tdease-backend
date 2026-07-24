<template>
  <div class="media-viewer">
    <img
      v-if="isImage"
      class="media-image"
      :src="sourceUrl"
      :alt="label"
    />
    <iframe
      v-else-if="isHtml"
      class="media-frame"
      :src="sourceUrl"
      sandbox="allow-scripts allow-same-origin"
      :title="label"
    />
    <a v-else-if="sourceUrl" class="media-link" :href="sourceUrl" target="_blank" rel="noreferrer">
      {{ label || sourceUrl }}
    </a>
    <div v-else class="media-empty">No media source.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Dataset, SelectionState } from '@/types/visualization'

interface Props {
  datasets?: Dataset[]
  viewSpec?: Record<string, unknown>
  data?: unknown
  config?: Record<string, unknown>
  selection?: SelectionState | null
}

const props = defineProps<Props>()

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

const media = computed(() => {
  const specMedia = asRecord(props.viewSpec?.media)
  if (Object.keys(specMedia).length > 0) return specMedia
  return asRecord(props.viewSpec)
})

const sourceUrl = computed(() => String(media.value.url || media.value.path || ''))
const mediaKind = computed(() => String(media.value.type || media.value.mediaType || '').toLowerCase())
const label = computed(() => String(media.value.label || media.value.alt || 'Visualization media'))

const isImage = computed(() => (
  mediaKind.value.includes('image')
  || ['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'].includes(mediaKind.value)
  || /\.(png|jpe?g|svg|gif|webp)(\?.*)?$/i.test(sourceUrl.value)
))
const isHtml = computed(() => (
  mediaKind.value.includes('html')
  || /\.html?(\?.*)?$/i.test(sourceUrl.value)
))
</script>

<style scoped>
.media-viewer {
  width: 100%;
  height: 100%;
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary, #f8fafc);
  overflow: hidden;
}

.media-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.media-frame {
  width: 100%;
  height: 100%;
  min-height: 360px;
  border: 0;
  background: white;
}

.media-link,
.media-empty {
  color: var(--el-text-color-regular, #606266);
  font-size: 13px;
}
</style>
