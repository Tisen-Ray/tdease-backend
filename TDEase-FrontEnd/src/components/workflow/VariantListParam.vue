<template>
  <div class="variant-list-param">
    <div class="toolbar">
      <el-button size="small" @click="openAddDialog">{{ $t('workflow.variantList.add') }}</el-button>
      <el-text v-if="hint" type="info" size="small">{{ hint }}</el-text>
    </div>

    <div v-if="entries.length === 0" class="empty">
      <el-text type="info">{{ $t('workflow.variantList.empty') }}</el-text>
    </div>

    <div v-for="(entry, idx) in entries" :key="entry.__key || idx" class="entry">
      <div class="entry-header">
        <el-select v-model="entry.kind" size="small" @change="onKindChange(idx)">
          <el-option
            v-for="v in variants"
            :key="v.kind"
            :label="v.label || v.kind"
            :value="v.kind"
          />
        </el-select>
        <el-button size="small" type="danger" plain @click="remove(idx)">{{ $t('common.button.delete') }}</el-button>
      </div>

      <div class="entry-body">
        <div v-if="variantDescription(entry.kind)" class="variant-help">
          <el-text type="info">{{ variantDescription(entry.kind) }}</el-text>
        </div>
        <div v-if="Object.keys(argDefs(entry.kind)).length === 0" class="no-args">
          <el-text type="info">{{ $t('workflow.variantList.noArgs') }}</el-text>
        </div>

        <div v-for="(def, argKey) in argDefs(entry.kind)" :key="argKey" class="arg-row">
          <div class="arg-label">
            <span>{{ def.label || argKey }}</span>
            <span v-if="def.required" class="req">*</span>
          </div>
          <div class="arg-input">
            <VariantListParam
              v-if="def.render?.kind === 'variant_list'"
              v-model="entry.params[argKey]"
              :param-def="def"
            />
            <el-select v-else-if="def.type === 'choice'" v-model="entry.params[argKey]" size="small">
              <el-option
                v-for="opt in getChoiceOptions(def.choices)"
                :key="String(opt.value)"
                :label="String(opt.label)"
                :value="opt.value"
              />
            </el-select>
            <el-switch v-else-if="def.type === 'boolean'" v-model="entry.params[argKey]" />
            <el-input
              v-else-if="def.ui?.multiline"
              v-model="entry.params[argKey]"
              type="textarea"
              :rows="3"
              :placeholder="def.ui?.placeholder || ''"
            />
            <el-input v-else v-model="entry.params[argKey]" :type="inputType(def)" />
            <div v-if="def.description" class="arg-help">{{ def.description }}</div>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="addDialogOpen" :title="$t('workflow.variantList.addItem')" width="520px">
      <el-input v-model="search" :placeholder="$t('common.button.search')" clearable />
      <div class="variant-grid">
        <el-button
          v-for="v in filteredVariants"
          :key="v.kind"
          class="variant-btn"
          @click="add(v.kind)"
        >
          {{ v.label || v.kind }}
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getChoiceOptions } from '@/composables/workflow/useParamUtils'

type VariantDef = {
  kind: string
  label?: string
  template?: string
  parameters?: Record<string, any>
  args?: Record<string, any>
}

const props = defineProps<{
  modelValue: unknown
  paramDef: any
  hint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const addDialogOpen = ref(false)
const search = ref('')

const variants = computed<VariantDef[]>(() => {
  const list = props.paramDef?.render?.variants
  if (!Array.isArray(list)) return []
  return list
    .filter((v: any) => v && typeof v === 'object' && typeof v.kind === 'string' && v.kind.trim())
    .map((v: any) => ({ ...v, kind: String(v.kind).trim() }))
})

const variantMap = computed(() => {
  const m: Record<string, VariantDef> = {}
  for (const v of variants.value) m[v.kind] = v
  return m
})

const rawVariantKind = computed(() => (variantMap.value.raw ? 'raw' : (variants.value[0]?.kind || 'raw')))

type Entry = { __key?: string; kind: string; params: Record<string, any> }

const isStructuredList = (value: unknown): boolean => {
  if (!Array.isArray(value)) return false
  for (const item of value) {
    if (!item || typeof item !== 'object') return false
    const rec = item as Record<string, unknown>
    if (typeof rec['kind'] !== 'string') return false
    if (!rec['params'] || typeof rec['params'] !== 'object') return false
  }
  return true
}

const normalize = (value: unknown): Entry[] => {
  const arr = Array.isArray(value) ? value : (value != null ? [value] : [])
  const out: Entry[] = []
  for (const item of arr) {
    if (typeof item === 'string') {
      out.push({ __key: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`, kind: rawVariantKind.value, params: { raw: item } })
      continue
    }
    if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>
      const rawKind = String(record['kind'] || record['type'] || record['id'] || rawVariantKind.value)
      const kind = rawKind
      const rawParams = (record['params'] && typeof record['params'] === 'object') ? record['params'] : {}
      const params = mergeMissingDefaults(kind, rawParams as Record<string, any>)
      out.push({
        ...record,
        __key: typeof record['__key'] === 'string' && (record['__key'] as string).trim()
          ? record['__key'] as string
          : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        kind,
        params,
      })
    }
  }
  return out
}

const entries = ref<Entry[]>(normalize(props.modelValue))

const lastEmitted = ref<string>('')

watch(() => props.modelValue, (next) => {
  const normalized = normalize(next)
  const payload = normalized.map((e) => ({ kind: e.kind, params: e.params }))
  const signature = JSON.stringify(payload)
  const currentSignature = JSON.stringify(entries.value.map((e) => ({ kind: e.kind, params: e.params })))
  if (signature === currentSignature) {
    return
  }

  // Upgrade legacy string/string[] to structured objects once, but don't churn
  // when the update originated from our own emit.
  if (!isStructuredList(next) && signature && signature !== lastEmitted.value) {
    lastEmitted.value = signature
    emit('update:modelValue', payload)
  }
  entries.value = normalized
}, { deep: true })

watch(entries, () => {
  const payload = entries.value.map((e) => ({ kind: e.kind, params: e.params }))
  const signature = JSON.stringify(payload)
  if (signature !== lastEmitted.value) {
    lastEmitted.value = signature
    emit('update:modelValue', payload)
  }
}, { deep: true })

const openAddDialog = () => {
  if (variants.value.length === 0) return
  search.value = ''
  addDialogOpen.value = true
}

const filteredVariants = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return variants.value
  return variants.value.filter((v) => (v.label || v.kind).toLowerCase().includes(q))
})

const argDefs = (kind: string): Record<string, any> => {
  const v = variantMap.value[kind]
  const defs = (v?.parameters && typeof v.parameters === 'object') ? v.parameters : (v?.args || {})
  return (defs && typeof defs === 'object') ? defs : {}
}

const buildDefaults = (kind: string): Record<string, any> => {
  const defs = argDefs(kind)
  const out: Record<string, any> = {}
  for (const [key, def] of Object.entries(defs)) {
    if (def.default !== undefined) out[key] = def.default
    else if (def.render?.kind === 'variant_list') out[key] = []
    else if (def.type === 'boolean') out[key] = false
    else out[key] = null
  }
  return out
}

function mergeMissingDefaults(kind: string, params: Record<string, any>): Record<string, any> {
  const defaults = buildDefaults(kind)
  const merged: Record<string, any> = { ...params }
  for (const [key, value] of Object.entries(defaults)) {
    if (merged[key] === undefined || merged[key] === null || merged[key] === '') {
      merged[key] = value
    }
  }
  return merged
}

const add = (kind: string) => {
  entries.value.push({ kind, params: buildDefaults(kind) })
  addDialogOpen.value = false
}

const remove = (idx: number) => {
  entries.value.splice(idx, 1)
}

const onKindChange = (idx: number) => {
  const entry = entries.value[idx]
  if (!entry) return
  entry.params = buildDefaults(entry.kind)
}

const variantDescription = (kind: string): string => {
  const v = variantMap.value[kind] as any
  const desc = typeof v?.description === 'string' ? v.description.trim() : ''
  return desc
}

const inputType = (def: any) => def.type === 'number' ? 'number' : 'text'
</script>

<style scoped>
.variant-list-param {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.empty {
  padding: 8px 0;
}

.entry {
  border: 1px solid var(--ctp-surface0);
  border-radius: 8px;
  padding: 10px;
  background: color-mix(in srgb, var(--ctp-base) 70%, transparent);
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.entry-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.arg-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 10px;
  align-items: start;
}

.arg-label {
  font-size: 12px;
  color: var(--ctp-subtext0);
  padding-top: 6px;
}

.req {
  color: var(--ctp-red);
  margin-left: 4px;
}

.arg-help {
  font-size: 11px;
  margin-top: 4px;
  color: var(--ctp-overlay0);
}

.variant-grid {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.variant-btn {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.no-args {
  padding: 4px 0;
}
</style>
