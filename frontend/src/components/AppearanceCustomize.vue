<template>
  <q-dialog :model-value="modelValue" @update:model-value="(v) => emit('update:modelValue', v)">
    <q-card style="min-width: 700px; max-width: 860px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">Customise the plot — {{ view.replace(/_/g, ' ') }} view</div>
        <q-space />
        <q-btn flat round dense icon="close" v-close-popup />
      </q-card-section>
      <q-card-section class="q-pt-sm q-pb-none">
        <div class="text-caption text-grey-7">
          Your changes live in this browser only: share links and other visitors keep the
          site configuration. Export to carry them to another machine.
        </div>
        <div class="row items-center q-gutter-sm q-mt-xs">
          <q-input v-model="filter" dense outlined clearable placeholder="filter languages"
                   style="width: 190px" />
          <q-badge v-if="overriddenCount" color="accent">
            {{ overriddenCount }} customised
          </q-badge>
          <q-space />
          <q-btn flat dense no-caps icon="download" label="export" :disable="!anyOverrides"
                 @click="exportTsv" />
          <q-btn flat dense no-caps icon="upload" label="import" @click="fileInput.click()" />
          <input ref="fileInput" type="file" accept=".tsv,.txt" hidden @change="importTsv" />
          <q-btn flat dense no-caps icon="restart_alt" label="reset view"
                 :disable="!overriddenCount" @click="resetView" />
        </div>
      </q-card-section>
      <q-card-section class="row-list q-pt-sm">
        <div
          v-for="item in filteredLanguages" :key="item.language"
          class="row items-center q-gutter-x-sm custom-row"
        >
          <div class="lang-name" :class="{ 'text-weight-medium': !!draft[item.language] }">
            {{ item.language.replace(/_/g, ' ') }}
          </div>
          <q-input
            :model-value="effective(item).label" dense outlined class="field-label"
            @update:model-value="(v) => setField(item, 'label', v)"
          />
          <q-input
            :model-value="effective(item).color" dense outlined class="field-color"
            @update:model-value="(v) => setField(item, 'color', v)"
          >
            <template #prepend>
              <span class="swatch" :style="{ background: effective(item).color }" />
            </template>
            <template #append>
              <q-icon name="colorize" size="16px" class="cursor-pointer">
                <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                  <q-color
                    :model-value="effective(item).color" no-header-tabs format-model="hex"
                    @update:model-value="(v) => setField(item, 'color', v)"
                  />
                </q-popup-proxy>
              </q-icon>
            </template>
          </q-input>
          <q-select
            :model-value="effective(item).marker" dense outlined class="field-marker"
            emit-value map-options options-dense
            :options="MARKERS.map((m) => ({ label: `${MARKER_GLYPHS[m]} ${m}`, value: m }))"
            @update:model-value="(v) => setField(item, 'marker', v)"
          />
          <q-btn
            flat dense round size="sm" icon="restart_alt" :class="{ invisible: !draft[item.language] }"
            @click="resetRow(item.language)"
          >
            <q-tooltip>back to the site configuration</q-tooltip>
          </q-btn>
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat no-caps label="cancel" v-close-popup />
        <q-btn unelevated no-caps color="primary" label="apply" @click="apply" v-close-popup />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const MARKERS = ['circle', 'triangle', 'rect', 'rectRot', 'cross', 'crossRot', 'star', 'line', 'dash']
const MARKER_GLYPHS = {
  circle: '●', triangle: '▲', rect: '■', rectRot: '◆',
  cross: '✚', crossRot: '✖', star: '✳', line: '▬', dash: '╌',
}

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  view: { type: String, required: true },
  // The site configuration for this view: [{ language, label, color, marker }]
  serverLanguages: { type: Array, default: () => [] },
  // All views' overrides: { [view]: { [language]: { label?, color?, marker? } } }
  overrides: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'update:overrides'])

const filter = ref('')
const fileInput = ref(null)

// The dialog edits a copy; nothing applies until "apply". Re-copied every time it opens,
// so cancel really cancels.
const draft = ref({})
watch(
  () => props.modelValue,
  (open) => {
    if (open) draft.value = JSON.parse(JSON.stringify(props.overrides[props.view] || {}))
  },
)

const filteredLanguages = computed(() => {
  const query = (filter.value || '').toLowerCase()
  const rows = [...props.serverLanguages].sort((a, b) => a.language.localeCompare(b.language))
  if (!query) return rows
  return rows.filter((item) => item.language.toLowerCase().includes(query))
})

const overriddenCount = computed(() => Object.keys(draft.value).length)
const anyOverrides = computed(() =>
  Object.values(props.overrides).some((view) => Object.keys(view).length),
)

function effective(item) {
  return { ...item, ...(draft.value[item.language] || {}) }
}

/** Store only the diff against the site configuration: a field set back to the server's
 *  value is removed, and a language with no differing field drops out entirely, so
 *  "customised" always means visibly different. */
function setField(item, field, value) {
  const entry = { ...(draft.value[item.language] || {}) }
  if (!value || value === item[field]) delete entry[field]
  else entry[field] = value
  if (Object.keys(entry).length) draft.value = { ...draft.value, [item.language]: entry }
  else {
    const next = { ...draft.value }
    delete next[item.language]
    draft.value = next
  }
}

function resetRow(language) {
  const next = { ...draft.value }
  delete next[language]
  draft.value = next
}

function resetView() {
  draft.value = {}
}

function apply() {
  const next = { ...props.overrides }
  if (Object.keys(draft.value).length) next[props.view] = draft.value
  else delete next[props.view]
  emit('update:overrides', next)
}

// ------------------------------------------------------------------- export / import
//
// A flat TSV over all views -- the same vocabulary as the server's own config files, so
// the file is readable next to appearance.tsv and can one day attach to an account.

function exportTsv() {
  const lines = ['view\tlanguage\tlabel\tcolor\tmarker']
  const merged = { ...props.overrides, [props.view]: draft.value }
  for (const [view, languages] of Object.entries(merged)) {
    for (const [language, entry] of Object.entries(languages)) {
      lines.push(
        [view, language, entry.label || '', entry.color || '', entry.marker || ''].join('\t'),
      )
    }
  }
  const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/tab-separated-values' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'grugrutyp-customisation.tsv'
  link.click()
  URL.revokeObjectURL(url)
}

function importTsv(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const next = {}
    const lines = String(reader.result).trim().split('\n')
    for (const line of lines.slice(1)) {
      const [view, language, label, color, marker] = line.split('\t').map((v) => (v || '').trim())
      if (!view || !language) continue
      const entry = {}
      if (label) entry.label = label
      if (color) entry.color = color
      if (marker) entry.marker = marker
      if (!Object.keys(entry).length) continue
      if (!next[view]) next[view] = {}
      next[view][language] = entry
    }
    emit('update:overrides', next)
    draft.value = JSON.parse(JSON.stringify(next[props.view] || {}))
  }
  reader.readAsText(file)
}
</script>

<style scoped>
.row-list {
  max-height: 55vh;
  overflow-y: auto;
}
.custom-row {
  padding: 1px 0;
}
.lang-name {
  width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}
.field-label {
  width: 150px;
}
.field-color {
  width: 165px;
}
.field-marker {
  width: 135px;
}
.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.25);
}
.invisible {
  visibility: hidden;
}
</style>
