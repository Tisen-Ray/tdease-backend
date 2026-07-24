<template>
  <div class="ag-grid-table">
    <div v-if="toolbar" class="table-toolbar">
      <div class="toolbar-left">
        <el-tag v-if="selectedCount > 0" type="info" size="small">
          {{ selectedCount }} rows selected
        </el-tag>
        <el-tag v-else-if="totalRows > 0" type="info" size="small">
          {{ totalRows }} total rows
        </el-tag>
      </div>

      <div class="toolbar-right">
        <el-input
          v-if="quickFilter"
          :model-value="quickFilterText"
          size="small"
          clearable
          placeholder="Search..."
          style="width: 220px"
          @update:model-value="onQuickFilterInput"
          @clear="clearQuickFilter"
        />

        <el-dropdown
          v-if="showExportButton && (exportOptions.csv || exportOptions.excel)"
          split-button
          type="primary"
          size="small"
          @click="exportCsv"
        >
          Export
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="exportOptions.csv" @click="exportCsv">Export as CSV</el-dropdown-item>
              <el-dropdown-item v-if="exportOptions.excel" @click="exportExcel">Export as Excel</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button v-if="showResetButton" size="small" :icon="Refresh" @click="resetTable">Reset</el-button>
      </div>
    </div>

    <div class="grid-container">
      <ag-grid-vue
        ref="gridRef"
        class="ag-theme-alpine"
        style="width: 100%; flex: 1; min-height: 0"
        theme="legacy"
        :column-defs="columnDefs"
        :row-data="rowData"
        :default-col-def="mergedDefaultColDef"
        :row-selection="agRowSelection"
        :pagination="pagination"
        :pagination-page-size="pageSize"
        :enable-cell-text-selection="true"
        :loading="loading"
        :quick-filter-text="quickFilterText"
        :get-row-id="props.getRowId"
        :grid-options="mergedGridOptions"
        :stop-editing-when-cells-lose-focus="stopEditingWhenCellsLoseFocus"
        @selection-changed="onSelectionChanged"
        @cell-clicked="onCellClicked"
        @cell-value-changed="onCellValueChanged"
        @grid-ready="onGridReady"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  CellValueChangedEvent,
  ColDef,
  GetRowIdFunc,
  GridApi,
  GridOptions,
  GridReadyEvent,
  RowClassRules,
} from 'ag-grid-community'
import { Refresh } from '@element-plus/icons-vue'
import type { SelectionState } from '@/types/visualization'
import { ensureAgGridModulesRegistered } from './ag-grid-modules'
import type { SelectionRef } from '@/services/visualization/runtime-types'

import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'

ensureAgGridModulesRegistered()

type ExportOptions = {
  csv?: boolean
  excel?: boolean
  fileBaseName?: string
}

interface Props {
  rowData: unknown[]
  columnDefs: ColDef[]
  defaultColDef?: ColDef
  loading?: boolean
  height?: string | number
  pagination?: boolean
  pageSize?: number
  quickFilter?: boolean
  quickFilterText?: string
  toolbar?: boolean
  export?: ExportOptions
  showExportButton?: boolean
  showResetButton?: boolean
  rowSelection?: 'single' | 'multiple' | false
  selection?: SelectionState | null
  selectionKeyField?: string | null
  selectedRowKeys?: Array<string | number>
  getRowId?: GetRowIdFunc
  stopEditingWhenCellsLoseFocus?: boolean
  rowClassRules?: RowClassRules
  gridOptions?: GridOptions
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  pagination: true,
  pageSize: 50,
  quickFilter: true,
  toolbar: true,
  quickFilterText: '',
  showExportButton: true,
  showResetButton: true,
  rowSelection: 'multiple',
  stopEditingWhenCellsLoseFocus: false,
})

const emit = defineEmits<{
  selectionChange: [SelectionState]
  selectedRowKeysChange: [Array<string | number>]
  gridReady: [GridApi]
  'update:quickFilterText': [string]
  cellValueChanged: [CellValueChangedEvent]
  cellClicked: [{ colId: string; value: unknown; data: Record<string, unknown> }]
}>()

type XLSXModule = typeof import('xlsx')

const gridRef = ref<any>(null)
const gridApi = ref<GridApi | null>(null)

const isApplyingExternalSelection = ref(false)
let applySelectionPendingTimer: ReturnType<typeof setTimeout> | null = null
const selectedValues = ref<Set<string | number>>(new Set())
const quickFilterText = ref(props.quickFilterText)

const exportOptions = computed<Required<ExportOptions>>(() => {
  const fileBaseName = props.export?.fileBaseName?.trim() || 'table_export'
  return {
    csv: props.export?.csv ?? true,
    excel: props.export?.excel ?? false,
    fileBaseName,
  }
})

const mergedDefaultColDef = computed<ColDef>(() => {
  return {
    sortable: true,
    filter: true,
    resizable: true,
    flex: 1,
    ...(props.defaultColDef || {}),
  }
})

const mergedGridOptions = computed<GridOptions>(() => {
  return {
    rowClassRules: props.rowClassRules,
    ...(props.gridOptions ?? {}),
  }
})

const agRowSelection = computed(() => {
  if (props.rowSelection === false) return undefined
  if (props.rowSelection === 'single') {
    return {
      mode: 'singleRow' as const,
      enableClickSelection: true,
      checkboxes: false,
      headerCheckbox: false,
    }
  }
  return {
    mode: 'multiRow' as const,
    enableClickSelection: true,
    checkboxes: false,
    headerCheckbox: false,
  }
})

const selectedCount = computed(() => selectedValues.value.size)
const totalRows = computed(() => Array.isArray(props.rowData) ? props.rowData.length : 0)

function toSelectionValue(value: unknown, fallback: string | number | null = null): string | number | null {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'string' || typeof value === 'number') return value
  return String(value)
}

function resolveRowSelectionValue(row: Record<string, unknown>, rowIndex: number | null): string | number | null {
  const key = props.selectionKeyField?.trim()
  if (key) {
    const raw = row[key]
    const numeric = Number(raw)
    if (Number.isFinite(numeric)) {
      return numeric
    }
    return toSelectionValue(raw, null)
  }
  return rowIndex === null ? null : rowIndex
}

function buildSelectionRefs(selection: Set<string | number>): SelectionRef[] {
  const key = props.selectionKeyField?.trim()
  if (!key) return []
  return Array.from(selection).map((value) => ({
    field: key,
    value,
  }))
}

function emitSelectionChange() {
  emit('selectedRowKeysChange', Array.from(selectedValues.value))
  emit('selectionChange', {
    selectedIndices: new Set(
      Array.from(selectedValues.value)
        .map((value) => {
          if (typeof value === 'number') return value
          const parsed = Number(value)
          return Number.isFinite(parsed) ? parsed : Number.NaN
        })
        .filter((value) => Number.isFinite(value))
    ),
    selectedRefs: buildSelectionRefs(selectedValues.value),
    filterCriteria: [],
    brushRegion: null,
  })
}

async function applySelectionToGrid(selection: Set<string | number>) {
  if (!gridApi.value) return

  if (applySelectionPendingTimer !== null) {
    clearTimeout(applySelectionPendingTimer)
    applySelectionPendingTimer = null
  }

  isApplyingExternalSelection.value = true
  gridApi.value.deselectAll()

  const nodes: any[] = []
  gridApi.value.forEachNode((node) => {
    const row = (node.data || {}) as Record<string, unknown>
    const selectionValue = resolveRowSelectionValue(row, node.rowIndex)
    if (selectionValue !== null && selection.has(selectionValue)) {
      nodes.push(node)
    }
  })

  if (nodes.length > 0) {
    gridApi.value.setNodesSelected({ nodes, newValue: true })
  }

  await nextTick()
  applySelectionPendingTimer = setTimeout(() => {
    isApplyingExternalSelection.value = false
    applySelectionPendingTimer = null
  }, 0)
}

function onSelectionChanged() {
  if (!gridApi.value) return
  if (isApplyingExternalSelection.value) return

  const selectedNodes = gridApi.value.getSelectedNodes()
  const next = new Set<string | number>()

  selectedNodes.forEach((node) => {
    const row = (node.data || {}) as Record<string, unknown>
    const selectionValue = resolveRowSelectionValue(row, node.rowIndex)
    if (selectionValue !== null) next.add(selectionValue)
  })

  selectedValues.value = next
  emitSelectionChange()
}

function onCellClicked(event: any) {
  if (!event?.colDef?.field || event?.colDef?.cellClass !== 'link-cell') return
  emit('cellClicked', {
    colId: event.colDef.field,
    value: event.value,
    data: (event.data || {}) as Record<string, unknown>,
  })
}

function onGridReady(event: GridReadyEvent) {
  gridApi.value = event.api
  emit('gridReady', event.api)
  applyQuickFilter()
}

function onQuickFilterInput(value: string | number) {
  quickFilterText.value = String(value ?? '')
  emit('update:quickFilterText', quickFilterText.value)
  applyQuickFilter()
}

function clearQuickFilter() {
  onQuickFilterInput('')
}

function applyQuickFilter() {
  if (!gridApi.value) return
  const text = quickFilterText.value || ''
  gridApi.value.setGridOption('quickFilterText', text)
}

function onCellValueChanged(event: CellValueChangedEvent) {
  emit('cellValueChanged', event)
}

function resetTable() {
  if (!gridApi.value) {
    selectedValues.value = new Set()
    quickFilterText.value = ''
    emitSelectionChange()
    return
  }

  quickFilterText.value = ''
  gridApi.value.setGridOption('quickFilterText', '')
  gridApi.value.setFilterModel(null)
  gridApi.value.resetColumnState()
  gridApi.value.deselectAll()
  selectedValues.value = new Set()
  emitSelectionChange()
}

function exportCsv() {
  if (!gridApi.value || !exportOptions.value.csv) return
  gridApi.value.exportDataAsCsv({
    fileName: `${exportOptions.value.fileBaseName}.csv`,
    onlySelected: selectedCount.value > 0,
  })
}

function exportExcel() {
  if (!exportOptions.value.excel) return
  void exportExcelAsync()
}

async function exportExcelAsync() {
  const baseName = exportOptions.value.fileBaseName
  const XLSX: XLSXModule = await import('xlsx')

  const columns = props.columnDefs
    .map((c) => ({ field: String(c.field || ''), headerName: String(c.headerName || c.field || '') }))
    .filter((c) => c.field)

  const isRowSelected = (row: Record<string, unknown>, idx: number): boolean => {
    const selectionValue = resolveRowSelectionValue(row, idx)
    return selectionValue !== null && selectedValues.value.has(selectionValue)
  }

  const allRows = (Array.isArray(props.rowData) ? props.rowData : []) as Record<string, unknown>[]
  const rowsToExport = selectedCount.value > 0
    ? allRows.filter((row, idx) => isRowSelected(row, idx))
    : allRows

  const normalized = rowsToExport.map((row) => {
    const out: Record<string, unknown> = {}
    columns.forEach((c) => {
      out[c.headerName] = row[c.field]
    })
    return out
  })

  const ws = XLSX.utils.json_to_sheet(normalized, { header: columns.map((c) => c.headerName) })
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
  XLSX.writeFile(wb, `${baseName}.xlsx`)
}

watch(
  () => props.quickFilterText,
  (value) => {
    const nextValue = value ?? ''
    if (nextValue === quickFilterText.value) return
    quickFilterText.value = nextValue
    applyQuickFilter()
  }
)

watch(
  () => props.selectedRowKeys,
  async (newSelectedRowKeys) => {
    if (!newSelectedRowKeys) return
    const incoming = new Set<string | number>()
    newSelectedRowKeys.forEach((value) => {
      const parsed = toSelectionValue(value, null)
      if (parsed !== null) incoming.add(parsed)
    })
    selectedValues.value = incoming
    await applySelectionToGrid(incoming)
  },
  { deep: true }
)

watch(
  () => props.selection,
  async (newSelection) => {
    if (!newSelection) return
    const incoming = new Set<string | number>()
    if (props.selectionKeyField?.trim() && Array.isArray(newSelection.selectedRefs) && newSelection.selectedRefs.length > 0) {
      newSelection.selectedRefs.forEach((ref) => {
        if (ref.field !== props.selectionKeyField) return
        const parsed = toSelectionValue(ref.value, null)
        if (parsed !== null) incoming.add(parsed)
      })
    }
    if (incoming.size === 0) {
      newSelection.selectedIndices.forEach((value) => {
        const parsed = toSelectionValue(value, null)
        if (parsed !== null) incoming.add(parsed)
      })
    }
    selectedValues.value = incoming
    await applySelectionToGrid(incoming)
  },
  { deep: true }
)

watch(
  () => props.rowData,
  () => {
    if (!gridApi.value) return
    // Ensure selection stays consistent when row data swaps.
    void applySelectionToGrid(selectedValues.value)
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (applySelectionPendingTimer !== null) {
    clearTimeout(applySelectionPendingTimer)
    applySelectionPendingTimer = null
  }
})
</script>

<style scoped>
.ag-grid-table {
  display: flex;
  flex-direction: column;
  height: 100%;
  /* Flex-item fallback: stretch inside flex-column hosts where height:100%
     cannot resolve (min-height-driven ancestor chains). */
  flex: 1;
  min-height: 0;
  gap: 8px;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm, 8px);
  background: var(--color-bg-secondary);
  border-radius: var(--lab-radius-sm, 5px);
  gap: var(--spacing-sm, 8px);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
}

.grid-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--lab-radius-sm, 5px);
  overflow: hidden;
}

/* Map AG Grid's legacy-theme variables onto the design tokens so the grid
   body follows the active Catppuccin flavor (light or dark) with no JS. */
.ag-theme-alpine {
  /* AG Grid's internals rely on a height:100% chain, which cannot resolve in
     the min-height-driven viewer tree — drive the outer links with flex. */
  display: flex;
  flex-direction: column;

  --ag-background-color: var(--color-bg);
  --ag-foreground-color: var(--ctp-text);
  --ag-data-color: var(--ctp-text);
  --ag-secondary-foreground-color: var(--ctp-subtext0);
  --ag-disabled-foreground-color: var(--ctp-overlay0);
  --ag-header-background-color: var(--lab-table-header-bg);
  --ag-header-foreground-color: var(--ctp-subtext1);
  --ag-odd-row-background-color: var(--color-bg);
  --ag-row-hover-color: var(--lab-table-row-hover);
  --ag-selected-row-background-color: var(--lab-table-row-selected);
  --ag-range-selection-background-color: var(--lab-table-row-selected);
  --ag-border-color: var(--lab-table-border);
  --ag-secondary-border-color: var(--lab-table-border);
  --ag-row-border-color: var(--lab-table-border);
  --ag-header-column-separator-color: var(--lab-table-border);
  --ag-header-column-resize-handle-color: var(--lab-table-border);
  --ag-input-border-color: var(--lab-control-border);
  --ag-input-focus-border-color: var(--color-primary);
  --ag-checkbox-checked-color: var(--color-primary);
  --ag-range-selection-border-color: var(--color-primary);
  --ag-invalid-color: var(--color-error);
}

:deep(.ag-theme-alpine) {
  font-size: 13px;
}

:deep(.ag-theme-alpine > div) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

:deep(.ag-root-wrapper.ag-layout-normal) {
  flex: 1;
  min-height: 0;
}

:deep(.ag-theme-alpine .ag-row-selected) {
  background-color: var(--lab-table-row-selected) !important;
}
</style>
