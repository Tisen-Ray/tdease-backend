<template>
  <!--
    TemplatePreview — right-panel content shown when a Library item is
    focused. Read-only summary of the template; the primary verb is Open
    (instantiate as new run in the canvas).
  -->
  <div class="template-preview">
    <header class="template-preview__header">
      <CatppuccinIcon name="Book" :size="14" />
      <span class="template-preview__name">{{ displayName }}</span>
      <el-tag v-if="isSystem" size="small" type="info" effect="plain">
        {{ $t('workflow.library.systemTag') }}
      </el-tag>
    </header>

    <div class="template-preview__body">
      <section v-if="template.description" class="template-preview__section">
        <label class="template-preview__field-label">{{ $t('workflow.templatePreview.description') }}</label>
        <p class="template-preview__desc">{{ template.description }}</p>
      </section>

      <section class="template-preview__section">
        <label class="template-preview__field-label">{{ $t('workflow.templatePreview.meta') }}</label>
        <dl class="template-preview__meta">
          <div class="template-preview__meta-row">
            <dt>ID</dt>
            <dd>{{ template.id }}</dd>
          </div>
          <div v-if="template.updated_at" class="template-preview__meta-row">
            <dt>{{ $t('workflow.templatePreview.updated') }}</dt>
            <dd>{{ formatDate(template.updated_at) }}</dd>
          </div>
          <div class="template-preview__meta-row">
            <dt>{{ $t('workflow.templatePreview.scope') }}</dt>
            <dd>{{ isSystem ? $t('workflow.library.systemTag') : $t('workflow.library.workspaceTag') }}</dd>
          </div>
        </dl>
      </section>
    </div>

    <footer class="template-preview__footer">
      <el-button type="primary" size="small" @click="$emit('open', template)">
        <CatppuccinIcon name="ArrowRight" :size="12" />
        {{ $t('workflow.library.open') }}
      </el-button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CatppuccinIcon } from '@/components/icons'
import { formatDate } from '@/utils/dateFormat'
import type { WorkflowTemplate } from '@/services/api/run'

const props = defineProps<{ template: WorkflowTemplate }>()
defineEmits<{ open: [template: WorkflowTemplate] }>()

const isSystem = computed(() => Boolean(props.template.is_shared))
const displayName = computed(() => props.template.name?.trim() || props.template.id)
</script>

<style scoped>
.template-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: var(--lab-panel-bg);
  overflow: hidden;
}
.template-preview__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--lab-text-strong);
  background: var(--lab-shell-bg);
  border-bottom: 1px solid var(--lab-panel-border);
  flex-shrink: 0;
}
.template-preview__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.template-preview__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.template-preview__section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.template-preview__field-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--lab-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.template-preview__desc {
  margin: 0;
  font-size: 12px;
  color: var(--lab-text-muted);
  line-height: 1.5;
}
.template-preview__meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.template-preview__meta-row {
  display: flex;
  gap: 8px;
  font-size: 11px;
}
.template-preview__meta-row dt {
  color: var(--lab-text-muted);
  min-width: 60px;
}
.template-preview__meta-row dd {
  margin: 0;
  color: var(--lab-text-strong);
  font-family: var(--lab-font-mono);
  word-break: break-all;
}
.template-preview__footer {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--lab-panel-border);
  background: var(--lab-shell-bg);
  display: flex;
  justify-content: flex-end;
}
</style>
