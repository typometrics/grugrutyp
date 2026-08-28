<template>
  <q-card flat bordered class="axis-panel">
    <q-card-section class="q-py-xs row items-center bg-grey-2">
      <q-icon :name="axis === 'x' ? 'swap_horiz' : 'swap_vert'" size="18px" class="q-mr-xs" />
      <span class="text-weight-medium">{{ axis.toUpperCase() }} axis</span>
      <q-space />
      <q-select
        :model-value="null" :options="presetOptions" label="Preset" dense options-dense
        outlined emit-value map-options style="min-width: 230px"
        @update:model-value="applyPreset"
      >
        <template #option="scope">
          <q-item v-bind="scope.itemProps">
            <q-item-section>
              <q-item-label>{{ scope.opt.label }}</q-item-label>
              <q-item-label caption class="preset-caption">
                {{ scope.opt.description }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </template>
      </q-select>
      <q-btn
        v-if="collapsible" flat dense round size="sm" class="q-ml-xs"
        :icon="collapsed ? 'expand_more' : 'expand_less'"
        @click="$emit('update:collapsed', !collapsed)"
      >
        <q-tooltip>{{ collapsed ? 'Use this axis' : 'Collapse — plot one dimension' }}</q-tooltip>
      </q-btn>
    </q-card-section>

    <q-slide-transition>
      <div v-show="!collapsed">
        <q-card-section class="q-pt-sm q-pb-none">
          <q-input
            :model-value="scope" type="textarea" outlined dense autogrow
            label="Scope (S) — what we count" input-class="grew-editor"
            :error="!!scopeError" :error-message="scopeError"
            @update:model-value="(v) => emitUpdate('scope', v)"
          />
        </q-card-section>
        <q-card-section class="q-py-sm">
          <q-input
            :model-value="response" type="textarea" outlined dense autogrow
            label="Response (Q) — of those, how many also…" input-class="grew-editor"
            :error="!!responseError" :error-message="responseError"
            @update:model-value="(v) => emitUpdate('response', v)"
          />
        </q-card-section>

        <q-card-section class="q-pt-none q-pb-sm">
          <!-- The live preview is the thing that makes an editable query pair usable: it
               answers "is my scope what I think it is?" before committing to 705 treebanks. -->
          <div class="row items-center text-caption">
            <q-spinner v-if="previewing" size="14px" class="q-mr-sm" />
            <template v-else-if="preview && preview.n_scope">
              <span class="text-weight-medium">{{ preview.value.toFixed(2) }}%</span>
              <span class="text-grey-7 q-ml-xs">
                = {{ preview.n_hit.toLocaleString() }} / {{ preview.n_scope.toLocaleString() }}
                on {{ shortTreebank }}
              </span>
              <span class="text-grey-6 q-ml-xs">
                (95% {{ preview.ci_low.toFixed(2) }}–{{ preview.ci_high.toFixed(2) }})
              </span>
            </template>
            <span v-else-if="preview" class="text-orange-9">
              the scope matches nothing in {{ shortTreebank }}
            </span>
            <span v-else class="text-grey-6">preview on {{ shortTreebank }}</span>
            <q-space />
            <q-badge v-if="note" outline color="grey-7" class="cursor-pointer">
              note
              <q-tooltip class="note-tooltip">{{ note }}</q-tooltip>
            </q-badge>
          </div>
        </q-card-section>
      </div>
    </q-slide-transition>

    <q-card-section v-if="collapsed" class="q-py-sm text-caption text-grey-7">
      Collapsed — the plot shows {{ axis === 'y' ? 'X' : 'Y' }} alone, as a strip.
    </q-card-section>
  </q-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  axis: { type: String, required: true },
  scope: { type: String, default: '' },
  response: { type: String, default: '' },
  presets: { type: Array, default: () => [] },
  treebank: { type: String, default: '' },
  collapsed: { type: Boolean, default: false },
  collapsible: { type: Boolean, default: false },
})
const emit = defineEmits(['update:scope', 'update:response', 'update:collapsed', 'label'])

const scopeError = ref('')
const responseError = ref('')
const preview = ref(null)
const previewing = ref(false)
const note = ref('')

const presetOptions = computed(() =>
  props.presets
    .filter((p) => p.available)
    .map((p) => ({
      label: `${p.group} · ${p.name}`,
      value: p.key,
      description: p.description,
    })),
)

const shortTreebank = computed(() => (props.treebank || '').replace(/^S?UD_/, '') || '—')

function applyPreset(key) {
  const preset = props.presets.find((p) => p.key === key)
  if (!preset) return
  // A preset is a starting point, not a selection: it loads into the editors and the user
  // is expected to change the relation, the POS, the direction. Nothing keeps a reference
  // to which preset it came from, because after the first edit that would be a lie.
  emit('update:scope', preset.scope)
  emit('update:response', preset.response)
  emit('label', preset.name)
  note.value = preset.note || ''
}

function emitUpdate(field, value) {
  note.value = ''
  emit(field === 'scope' ? 'update:scope' : 'update:response', value)
}

let timer = null
watch(
  () => [props.scope, props.response, props.treebank, props.collapsed],
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
    })
  } catch (error) {
    preview.value = null
    // The API cannot say which of the two editors a combined error belongs to, but the
    // binding-rule message always names the response, so route on that.
    const message = error.message || 'invalid'
    if (/response pattern|subquery/.test(message)) responseError.value = message
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
.preset-caption {
  white-space: normal;
  max-width: 380px;
}
.note-tooltip {
  max-width: 420px;
  font-size: 12px;
}
</style>
