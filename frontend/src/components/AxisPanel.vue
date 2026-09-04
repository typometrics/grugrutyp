<template>
  <q-card flat bordered class="axis-panel">
    <q-card-section
      class="q-py-xs row items-center"
      :class="$q.dark.isActive ? 'bg-grey-9' : 'bg-grey-2'"
    >
      <q-icon :name="axis === 'x' ? 'swap_horiz' : 'swap_vert'" size="18px" class="q-mr-xs" />
      <span class="text-weight-medium">{{ axis.toUpperCase() }} axis</span>
      <q-space />
      <!-- The select's value is derived from the axis label, which the parent clears the
           moment either editor is touched -- so the picker reads "Subject after verb"
           exactly as long as that is true, and empties when the query stops being the
           preset. -->
      <q-select
        :model-value="selectedPresetKey" :options="presetOptions" label="Preset"
        dense options-dense outlined emit-value map-options style="min-width: 230px"
        @update:model-value="applyPreset"
      >
        <template #option="scope">
          <q-item-label v-if="scope.opt.header" header class="preset-group">
            {{ scope.opt.header }}
          </q-item-label>
          <q-item v-else v-bind="scope.itemProps">
            <q-item-section>
              <q-item-label class="preset-name">{{ scope.opt.label }}</q-item-label>
              <q-item-label caption class="preset-caption">
                {{ scope.opt.description }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </template>
      </q-select>
      <!-- Phase 6.5: allowlisted accounts can draft the queries from a description.
           The button exists only for them -- everyone else keeps a clean panel. -->
      <q-btn
        v-if="user?.llm_allowed" flat dense round size="sm" icon="auto_awesome"
        class="q-ml-xs" @click="wordsOpen = true"
      >
        <q-tooltip>Describe the measure in words — an LLM drafts the queries</q-tooltip>
      </q-btn>
      <!-- Points right: the panel folds into the handle at the right edge, so the
           arrow shows where it goes. -->
      <q-btn
        v-if="collapsible" flat dense round size="sm" class="q-ml-xs"
        icon="chevron_right"
        @click="$emit('update:collapsed', !collapsed)"
      >
        <q-tooltip>Collapse — plot one dimension</q-tooltip>
      </q-btn>
    </q-card-section>

    <!-- ------------------------------------------------- words -> query pair (6.5) -->
    <q-dialog v-model="wordsOpen">
      <q-card style="min-width: 480px; max-width: 660px">
        <q-card-section class="q-pb-none">
          <div class="text-h6">Describe the {{ axis.toUpperCase() }} measure in words</div>
          <div class="text-caption text-grey-7">
            Any language. The draft lands in the editors — validated, previewed on one
            treebank, and yours to edit. Nothing runs on the corpus until you press Plot.
          </div>
        </q-card-section>
        <q-card-section class="q-pb-none">
          <q-input
            v-model="wordsText" type="textarea" outlined autogrow autofocus
            placeholder="e.g. how often does the subject come after its verb?"
            @keydown.ctrl.enter.prevent="translateWords"
          />
          <q-banner v-if="wordsError" dense class="bg-red-1 text-red-9 q-mt-sm">
            {{ wordsError }}
          </q-banner>
          <div v-if="translation" class="q-mt-sm">
            <div class="text-caption">{{ translation.explanation }}</div>
            <pre class="grew-snippet nl-draft q-mt-xs">{{ translation.scope }}</pre>
            <pre v-if="translation.response" class="grew-snippet nl-draft">{{ translation.response }}</pre>
            <pre v-if="translation.expression" class="grew-snippet nl-draft">{{ translation.aggregation }} of {{ translation.expression }}</pre>
            <div class="text-caption text-grey-6 q-mt-xs">
              {{ translation.model }}, attempt {{ translation.attempts }} ·
              {{ translation.quota.used }}/{{ translation.quota.limit }} drafts today ·
              check the numbers before citing anything
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="close" v-close-popup />
          <q-btn
            v-if="!translation" unelevated no-caps color="accent"
            label="draft the queries" :loading="translating"
            :disable="!wordsText.trim()" @click="translateWords"
          />
          <template v-else>
            <q-btn flat no-caps label="redraft" :loading="translating" @click="translateWords" />
            <q-btn
              unelevated no-caps color="primary" label="into the editors"
              v-close-popup @click="applyTranslation"
            />
          </template>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-slide-transition>
      <div v-show="!collapsed">
        <!-- hide-bottom-space: without it each editor reserves a full line for a
             potential error message, which is most of the S/Q gap Kim flagged. The
             error text still appears when there is one. -->
        <q-card-section class="q-pt-sm q-pb-none">
          <q-input
            :model-value="scope" type="textarea" outlined dense autogrow hide-bottom-space
            label="Scope (S) — what we count" input-class="grew-editor"
            :error="!!scopeError" :error-message="scopeError"
            @update:model-value="(v) => emitUpdate('scope', v)"
          />
        </q-card-section>
        <!-- A flexibility measure has no editable response either: its response is
             fixed (`with { GOV << DEP }`) and the scope is what varies. -->
        <q-card-section v-if="kind === 'ratio'" class="q-pt-xs q-pb-none">
          <q-input
            :model-value="response" type="textarea" outlined dense autogrow hide-bottom-space
            label="Response (Q) — of those, how many also…" input-class="grew-editor"
            :error="!!responseError" :error-message="responseError"
            @update:model-value="(v) => emitUpdate('response', v)"
          />
        </q-card-section>
        <!-- An aggregate measure has no response: it averages a number over the scope's
             matchings instead of counting a subset of them. -->
        <q-card-section v-else class="q-py-sm row q-col-gutter-sm">
          <div class="col">
            <q-input
              :model-value="expression" outlined dense input-class="grew-editor"
              label="Value — averaged over the scope"
              :error="!!responseError" :error-message="responseError"
              @update:model-value="(v) => emitUpdate('expression', v)"
            >
              <template #append>
                <q-icon name="help_outline" size="18px" class="cursor-pointer">
                  <q-tooltip class="note-tooltip">
                    delta(GOV, DEP) — signed distance, dependent minus governor<br>
                    abs(delta(GOV, DEP)) — distance without direction<br>
                    X.Feature — a numeric feature of a bound node<br>
                    sentence.height, sentence.length — precomputed per sentence
                  </q-tooltip>
                </q-icon>
              </template>
            </q-input>
          </div>
          <div class="col-auto" style="min-width: 120px">
            <q-select
              :model-value="aggregation" :options="['avg', 'sum', 'min', 'max']"
              label="How" outlined dense options-dense
              @update:model-value="(v) => emitUpdate('aggregation', v)"
            />
          </div>
        </q-card-section>

        <!-- The live preview is the thing that makes an editable query pair usable: it
             answers "is my scope what I think it is?" before committing to 705
             treebanks. One thin line, never wrapping -- it was three lines tall and cost
             more vertical space than an editor. The tooltip carries the long form. -->
        <q-card-section class="q-px-md q-py-xs preview-line row items-center no-wrap text-caption">
          <q-spinner v-if="previewing" size="12px" class="q-mr-sm" />
          <template v-else-if="preview && preview.n_scope">
            <span class="text-weight-medium">
              {{ preview.value == null ? '—' : preview.value.toFixed(2) }}{{ unitSuffix }}
            </span>
            <span class="text-grey-7 q-ml-xs ellipsis">
              <template v-if="kind === 'ratio'">
                = {{ preview.n_hit.toLocaleString() }}/{{ preview.n_scope.toLocaleString() }}
              </template>
              <template v-else>
                over {{ preview.n_scope.toLocaleString() }} matchings
              </template>
              on {{ shortTreebank }}
              <template v-if="preview.ci_low != null">
                · 95% {{ preview.ci_low.toFixed(1) }}–{{ preview.ci_high.toFixed(1) }}
              </template>
            </span>
            <q-tooltip v-if="preview.ci_low != null" class="note-tooltip">
              {{ preview.n_hit.toLocaleString() }} of {{ preview.n_scope.toLocaleString() }}
              matchings on {{ treebank }} — 95% interval
              {{ preview.ci_low.toFixed(2) }}–{{ preview.ci_high.toFixed(2) }}
            </q-tooltip>
          </template>
          <span v-else-if="preview" class="text-orange-9 ellipsis">
            the scope matches nothing in {{ shortTreebank }}
          </span>
          <span v-else class="text-grey-6">preview on {{ shortTreebank }}</span>
          <q-space />
          <q-badge v-if="note" outline color="grey-7" class="cursor-pointer q-ml-xs">
            note
            <q-tooltip class="note-tooltip">{{ note }}</q-tooltip>
          </q-badge>
        </q-card-section>
      </div>
    </q-slide-transition>

  </q-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api, llm } from '../api'
import { user } from '../user'

const $q = useQuasar()

const props = defineProps({
  axis: { type: String, required: true },
  label: { type: String, default: '' },
  scope: { type: String, default: '' },
  response: { type: String, default: '' },
  presets: { type: Array, default: () => [] },
  treebank: { type: String, default: '' },
  scheme: { type: String, default: 'SUD' },
  collapsed: { type: Boolean, default: false },
  collapsible: { type: Boolean, default: false },
  kind: { type: String, default: 'ratio' },
  expression: { type: String, default: '' },
  aggregation: { type: String, default: 'avg' },
  unit: { type: String, default: '%' },
})
const emit = defineEmits([
  'update:scope', 'update:response', 'update:collapsed',
  'update:kind', 'update:expression', 'update:aggregation', 'update:unit', 'label',
])

const unitSuffix = computed(() => (props.unit === '%' ? '%' : ` ${props.unit}`))

const scopeError = ref('')
const responseError = ref('')
const preview = ref(null)
const previewing = ref(false)
const note = ref('')

// Grouped by type, with a header row before each group -- a flat "group · name" list
// buries the structure in repeated prefixes.
const presetOptions = computed(() => {
  const out = []
  let lastGroup = null
  for (const p of props.presets.filter((p) => p.available)) {
    if (p.group !== lastGroup) {
      out.push({ header: p.group, disable: true })
      lastGroup = p.group
    }
    out.push({ label: p.name, value: p.key, description: p.description })
  }
  return out
})

const selectedPresetKey = computed(
  () => props.presets.find((p) => p.name === props.label)?.key ?? null,
)

// Corpus name alone ("GUM", not "English-GUM"): the preview line has one line to live in.
const shortTreebank = computed(() => (props.treebank || '').replace(/^S?UD_.*?-/, '') || '—')

function applyPreset(key) {
  const preset = props.presets.find((p) => p.key === key)
  if (!preset) return
  // A preset is a starting point, not a selection: it loads into the editors and the user
  // is expected to change the relation, the POS, the direction. The only reference kept
  // is the axis label, which the first edit clears -- so the picker can display the name
  // while it is true and never after.
  emit('update:scope', preset.scope)
  emit('update:response', preset.response)
  emit('update:kind', preset.kind || 'ratio')
  emit('update:expression', preset.expression || '')
  emit('update:aggregation', preset.aggregation || 'avg')
  emit('update:unit', preset.unit || '%')
  emit('label', preset.name)
  note.value = preset.note || ''
}

// ------------------------------------------------------------ words -> query (6.5)

const wordsOpen = ref(false)
const wordsText = ref('')
const translating = ref(false)
const translation = ref(null)
const wordsError = ref('')

async function translateWords() {
  if (!wordsText.value.trim()) return
  translating.value = true
  wordsError.value = ''
  translation.value = null
  try {
    const result = await llm.translate(wordsText.value.trim(), props.scheme)
    if (result.ok) translation.value = result
    else wordsError.value = result.refusal || result.error || 'the model produced no valid query'
  } catch (exception) {
    wordsError.value = exception.message
  } finally {
    translating.value = false
  }
}

/** Into the editors through the same emits a preset uses -- from here on it is an
 *  ordinary editable query: previewed live, run only when the user plots. */
function applyTranslation() {
  const draft = translation.value
  if (!draft) return
  emit('update:scope', draft.scope)
  emit('update:response', draft.response)
  emit('update:kind', draft.kind)
  emit('update:expression', draft.expression || '')
  emit('update:aggregation', draft.aggregation || 'avg')
  emit('update:unit', draft.kind === 'aggregate' ? '' : '%')  // flexibility is 0-100 too
  emit('label', draft.label || '')
  note.value = ''
}

function emitUpdate(field, value) {
  note.value = ''
  emit(`update:${field}`, value)
  // A preset's name describes the preset's query. Once the query is edited it describes
  // nothing, and an axis labelled "Head-initiality of subj" over a comp:obj measure is a
  // caption that lies -- worse than no caption, because a reader has no way to notice.
  // Dropping it lets the parent fall back to a label derived from the query itself.
  emit('label', '')
}

let timer = null
watch(
  () => [
    props.scope, props.response, props.treebank, props.collapsed,
    props.kind, props.expression, props.aggregation,
  ],
  () => {
    clearTimeout(timer)
    timer = setTimeout(runPreview, 450)
  },
  { immediate: true },
)

async function runPreview() {
  scopeError.value = ''
  responseError.value = ''
  if (props.collapsed || !props.treebank || !props.scope.trim()) {
    preview.value = null
    return
  }
  previewing.value = true
  try {
    preview.value = await api.preview({
      treebank: props.treebank,
      scope: props.scope,
      response: props.response,
      kind: props.kind,
      expression: props.expression,
      aggregation: props.aggregation,
    })
  } catch (error) {
    preview.value = null
    // The API cannot say which of the two editors a combined error belongs to, but the
    // binding-rule message always names the response, so route on that.
    const message = error.message || 'invalid'
    if (/response pattern|subquery|expression|bound by the scope|aggregation/.test(message))
      responseError.value = message
    else scopeError.value = message
  } finally {
    previewing.value = false
  }
}
</script>

<style scoped>
.axis-panel {
  height: 100%;
}
/* The site's antiqua is right for titles and wrong for 11px explanatory text -- at
   caption size with Quasar's washed-out caption grey it was genuinely hard to read
   (Kim). Standard UI sans, darker ink; the two-class selector outbids Quasar's own
   .q-item__label--caption colour. */
.q-item__label.preset-caption {
  white-space: normal;
  max-width: 380px;
  font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 12px;
  line-height: 1.4;
  color: #3c3c3c;
}
.body--dark .q-item__label.preset-caption {
  color: #c4c4c4;
}
.preset-group {
  padding: 6px 12px 2px;
  font-variant: small-caps;
  letter-spacing: 0.04em;
  color: var(--q-primary);
  font-weight: 600;
}
.preset-name {
  color: #1d1d1d;
}
.body--dark .preset-name {
  color: #e8e8e8;
}
.note-tooltip {
  max-width: 420px;
  font-size: 12px;
}
.preview-line {
  min-height: 26px;
}
.nl-draft {
  background: rgba(0, 0, 0, 0.05);
  padding: 6px 9px;
  border-radius: 4px;
  margin: 2px 0;
  overflow-x: auto;
}
.body--dark .nl-draft {
  background: rgba(255, 255, 255, 0.07);
}
</style>
