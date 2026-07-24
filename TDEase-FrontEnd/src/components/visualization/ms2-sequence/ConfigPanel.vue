<template>
  <div class="config-panel">
    <div class="panel-header">
      <span class="panel-title">Configuration</span>
      <el-button size="small" text @click="emit('reset')">Reset</el-button>
    </div>

    <div class="config-section">
      <div class="section-title">Ion Types</div>
      <el-checkbox-group v-model="localConfig.ionTypes" size="small">
        <el-checkbox-button label="a">a</el-checkbox-button>
        <el-checkbox-button label="b">b</el-checkbox-button>
        <el-checkbox-button label="c">c</el-checkbox-button>
        <el-checkbox-button label="x">x</el-checkbox-button>
        <el-checkbox-button label="y">y</el-checkbox-button>
        <el-checkbox-button label="z">z</el-checkbox-button>
      </el-checkbox-group>
    </div>

    <div class="config-section">
      <div class="section-title">Max Charge</div>
      <el-slider v-model="localConfig.maxFragmentCharge" :min="1" :max="5" show-stops />
    </div>

    <div class="config-section">
      <div class="section-title">Tolerance (ppm)</div>
      <el-slider v-model="localConfig.tolerancePpm" :min="1" :max="100" :step="1" />
      <div class="slider-value">{{ localConfig.tolerancePpm }} ppm</div>
    </div>

    <div class="config-section">
      <div class="section-title">Display Options</div>
      <el-checkbox v-model="localConfig.showMatchedPeaks" size="small">
        Show matched peaks
      </el-checkbox>
      <el-checkbox v-model="localConfig.showUnmatchedPeaks" size="small">
        Show unmatched peaks
      </el-checkbox>
      <el-checkbox v-model="localConfig.showNeutralLosses" size="small">
        Show neutral losses
      </el-checkbox>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { ViewerConfig } from '@/composables/ms2-sequence'

interface Props {
  config: ViewerConfig
}

const props = defineProps<Props>()

const emit = defineEmits<{
  change: [config: ViewerConfig]
  reset: []
}>()

const localConfig = reactive<ViewerConfig>({ ...props.config })

watch(
  () => props.config,
  (newConfig) => {
    Object.assign(localConfig, newConfig)
  },
  { deep: true }
)

watch(
  localConfig,
  () => {
    emit('change', { ...localConfig })
  },
  { deep: true }
)
</script>

<style scoped>
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-title {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

.slider-value {
  font-size: 11px;
  color: #909399;
  text-align: right;
}
</style>
