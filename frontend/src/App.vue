<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar class="q-py-xs">
        <q-toolbar-title class="col-auto text-weight-bold">
          grugrutyp
          <span class="text-caption q-ml-sm opacity-70">Grew queries over UD &amp; SUD</span>
        </q-toolbar-title>
        <q-space />
        <q-btn
          flat dense no-caps icon="help_outline" label="Grew syntax"
          href="https://grew.fr/doc/request/" target="_blank"
        />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <q-page>
        <!-- ============================================ controls, across the top -->
        <q-card square flat bordered class="controls">
          <q-card-section class="q-py-sm">
            <div class="row q-col-gutter-md items-start">
              <div class="col-12 col-md-3 column q-gutter-sm">
                <q-btn-toggle
                  v-model="scheme" no-caps unelevated dense
                  toggle-color="primary" :options="schemeOptions" class="full-width"
                />
                <q-select
                  v-model="treebank" :options="treebankOptions" label="Treebank"
                  use-input input-debounce="0" fill-input hide-selected emit-value map-options
                  outlined dense options-dense @filter="filterTreebanks"
                  :loading="loadingTreebanks"
                >
                  <template #option="scope">
                    <q-item v-bind="scope.itemProps">
                      <q-item-section>
                        <q-item-label>{{ scope.opt.label }}</q-item-label>
                        <q-item-label caption>
                          {{ scope.opt.family }} ·
                          {{ scope.opt.n_tokens.toLocaleString() }} tokens
                        </q-item-label>
                      </q-item-section>
                    </q-item>
                  </template>
                  <template #no-option>
                    <q-item><q-item-section class="text-grey">
                      No treebank matches
                    </q-item-section></q-item>
                  </template>
                </q-select>
              </div>

              <div class="col-12 col-md-6">
                <q-input
                  v-model="request" type="textarea" outlined dense autogrow
                  label="Grew request" input-class="grew-editor"
                  :error="!!syntaxError" :error-message="syntaxError"
                  @update:model-value="onRequestChange"
                  @keydown.ctrl.enter="runSearch"
                />
              </div>

              <div class="col-12 col-md-3 column q-gutter-sm">
                <q-btn
                  color="primary" no-caps icon="search" label="Search"
                  :loading="searching" :disable="!treebank || !!syntaxError"
                  @click="runSearch"
                />
                <q-select
                  v-model="featureSet" :options="featureSetOptions" label="Show on trees"
                  outlined dense options-dense emit-value map-options
                />
                <q-btn
                  flat dense no-caps size="sm" icon="code"
                  :label="showCypher ? 'Hide Cypher' : 'Show Cypher'"
                  @click="showCypher = !showCypher"
                />
              </div>
            </div>

            <!-- examples: each carries the scheme it is written for -->
            <div class="row items-center q-gutter-xs q-mt-sm">
              <span class="text-caption text-grey-7 q-mr-xs">Examples</span>
              <q-chip
                v-for="example in examples" :key="example.label"
                clickable dense :color="chipColor" text-color="white"
                icon="play_arrow" @click="useExample(example)"
              >
                {{ example.label }}
                <q-tooltip class="grew-snippet">{{ example.request }}</q-tooltip>
              </q-chip>
              <q-chip dense outline :color="chipColor" class="text-weight-medium">
                {{ scheme }} syntax
              </q-chip>
            </div>

            <q-slide-transition>
              <pre v-if="showCypher && cypher" class="cypher q-mt-sm">{{ cypher }}</pre>
            </q-slide-transition>
          </q-card-section>
        </q-card>

        <!-- ================================================= results, full width -->
        <div class="q-pa-md">
          <q-banner v-if="searchError" dense class="bg-red-1 text-red-9 q-mb-md">
            <template #avatar><q-icon name="error_outline" /></template>
            {{ searchError }}
          </q-banner>

          <q-card v-if="result" flat bordered>
            <q-card-section class="row items-center q-py-sm">
              <div>
                <span class="text-h6">{{ result.total.toLocaleString() }}</span>
                <span class="text-grey-7 q-ml-xs">
                  matching{{ result.total === 1 ? '' : 's' }}
                </span>
                <span v-if="result.nodes.length" class="text-caption text-grey-7 q-ml-sm">
                  over {{ result.nodes.join(', ') }}
                </span>
              </div>
              <q-space />
              <q-pagination
                v-if="pageCount > 1" v-model="page" :max="pageCount"
                :max-pages="8" boundary-numbers dense @update:model-value="runSearch"
              />
            </q-card-section>
            <q-separator />

            <q-card-section v-if="!result.hits.length" class="text-grey-7">
              No sentence matches this request in {{ treebank }}.
            </q-card-section>

            <div v-else>
              <div v-for="hit in result.hits" :key="hit.sent_id" class="hit">
                <div class="row items-center q-px-md q-pt-sm">
                  <span class="text-caption text-grey-7">{{ hit.sent_id }}</span>
                  <q-space />
                  <q-btn
                    flat dense size="sm" icon="content_copy" no-caps label="CoNLL-U"
                    @click="copy(hit.conllu)"
                  />
                </div>
                <DepTree
                  :conllu="hit.conllu" :matched="hit.matched_nodes"
                  :shown-features="shownFeatures"
                />
                <q-separator />
              </div>
            </div>
          </q-card>

          <q-card v-else flat bordered class="bg-grey-1">
            <q-card-section class="text-grey-7">
              Pick a treebank, write a Grew request, and the matching trees appear here
              with the matched words highlighted. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> searches.
            </q-card-section>
          </q-card>
        </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api } from './api'
import DepTree from './components/DepTree.vue'

const $q = useQuasar()

const scheme = ref('SUD')
const schemeOptions = [
  { label: 'SUD', value: 'SUD' },
  { label: 'UD', value: 'UD' },
]
const chipColor = computed(() => (scheme.value === 'SUD' ? 'primary' : 'accent'))

const allTreebanks = ref([])
const treebankFilter = ref('')
const loadingTreebanks = ref(false)
const treebank = ref(null)

const request = ref('pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }')
const syntaxError = ref('')
const cypher = ref('')
const showCypher = ref(false)

const searching = ref(false)
const searchError = ref('')
const result = ref(null)
const page = ref(1)
const PAGE_SIZE = 10

// Which CoNLL-U columns the tree renderer draws under each word. Treebanks like GUM carry
// very long MISC values (Entity=..., Discourse=..., PDTB=...) that push a tree to several
// screens tall, so the default is deliberately narrow.
const featureSet = ref('standard')
const featureSetOptions = [
  { label: 'Minimal — form, POS, relation', value: 'minimal' },
  { label: 'Standard — + lemma', value: 'standard' },
  { label: 'Morphology — + FEATS', value: 'morph' },
  { label: 'Everything (can be very tall)', value: 'all' },
]
const FEATURE_SETS = {
  minimal: 'FORM,UPOS,DEPREL',
  standard: 'FORM,LEMMA,UPOS,DEPREL',
  morph: 'FORM,LEMMA,UPOS,XPOS,DEPREL,FEATS',
  all: '',
}
const shownFeatures = computed(() => FEATURE_SETS[featureSet.value])

// SUD relation names (comp, mod, subj) differ from UD's (obj, amod, nsubj). Each example
// carries the scheme it is written for, and only the matching ones are offered, so the
// query in the editor is never silently invalid for the selected scheme.
const EXAMPLES = [
  {
    label: 'Subject after governor',
    scheme: 'SUD',
    request: 'pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }',
  },
  {
    label: 'Subject after governor',
    scheme: 'UD',
    request: 'pattern { GOV -[1=nsubj]-> DEP }\nwith { GOV << DEP }',
  },
  {
    label: 'Adjective before noun',
    scheme: 'SUD',
    request: 'pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] }\nwith { A << N }',
  },
  {
    label: 'Adjective before noun',
    scheme: 'UD',
    request: 'pattern { N [upos=NOUN]; N -[amod]-> A [upos=ADJ] }\nwith { A << N }',
  },
  {
    label: 'Pronominal object',
    scheme: 'SUD',
    request: 'pattern { G -[1=comp, 2=obj]-> D }\nwith { D [upos=PRON] }',
  },
  {
    label: 'Pronominal object',
    scheme: 'UD',
    request: 'pattern { G -[obj]-> D }\nwith { D [upos=PRON] }',
  },
  {
    label: 'Non-projective',
    scheme: 'SUD',
    request: 'pattern { GOV -[1=subj]-> DEP }\nglobal { is_not_projective }',
  },
  {
    label: 'Non-projective',
    scheme: 'UD',
    request: 'pattern { GOV -[1=nsubj]-> DEP }\nglobal { is_not_projective }',
  },
]
const examples = computed(() => EXAMPLES.filter((e) => e.scheme === scheme.value))

const schemeTreebanks = computed(() =>
  allTreebanks.value
    .filter((tb) => tb.scheme === scheme.value)
    .map((tb) => ({
      label: `${tb.language.replace(/_/g, ' ')} — ${tb.corpus}`,
      value: tb.name,
      family: tb.family,
      n_sents: tb.n_sents,
      n_tokens: tb.n_tokens,
    })),
)

const treebankOptions = computed(() => {
  const needle = treebankFilter.value.toLowerCase()
  if (!needle) return schemeTreebanks.value
  return schemeTreebanks.value.filter((o) => o.label.toLowerCase().includes(needle))
})

const pageCount = computed(() =>
  result.value ? Math.ceil(Math.min(result.value.total, 500) / PAGE_SIZE) : 0,
)

function filterTreebanks(value, update) {
  update(() => {
    treebankFilter.value = value
  })
}

function useExample(example) {
  request.value = example.request
  onRequestChange()
}

async function copy(text) {
  await navigator.clipboard.writeText(text)
  $q.notify({ message: 'CoNLL-U copied', timeout: 1200, position: 'bottom-right' })
}

let validateTimer = null
function onRequestChange() {
  clearTimeout(validateTimer)
  validateTimer = setTimeout(validate, 300)
}

async function validate() {
  if (!request.value.trim()) {
    syntaxError.value = ''
    cypher.value = ''
    return
  }
  try {
    const response = await api.validate(request.value)
    if (response.valid) {
      syntaxError.value = ''
      cypher.value = response.cypher
    } else {
      const error = response.error || {}
      syntaxError.value =
        error.line != null
          ? `line ${error.line}, column ${error.column}: ${error.message}`
          : error.message
      cypher.value = ''
    }
  } catch (error) {
    syntaxError.value = error.message
  }
}

async function runSearch() {
  if (!treebank.value || syntaxError.value) return
  searching.value = true
  searchError.value = ''
  try {
    result.value = await api.search({
      treebank: treebank.value,
      request: request.value,
      limit: PAGE_SIZE,
      skip: (page.value - 1) * PAGE_SIZE,
    })
  } catch (error) {
    searchError.value = error.message
    result.value = null
  } finally {
    searching.value = false
  }
}

// Switching scheme keeps the same corpus: SUD_English-GUM <-> UD_English-GUM. Dropping the
// selection on every toggle made comparing the two annotations of one corpus tedious --
// which is one of the main reasons to have both schemes side by side at all.
watch(scheme, (next) => {
  const current = allTreebanks.value.find((tb) => tb.name === treebank.value)
  if (current) {
    const twin = allTreebanks.value.find(
      (tb) =>
        tb.scheme === next && tb.language === current.language && tb.corpus === current.corpus,
    )
    treebank.value = twin ? twin.name : (schemeTreebanks.value[0]?.value ?? null)
  }
  result.value = null
})

watch(treebank, () => {
  page.value = 1
  result.value = null
})

onMounted(async () => {
  loadingTreebanks.value = true
  try {
    const response = await api.treebanks()
    allTreebanks.value = response.treebanks
    const preferred = schemeTreebanks.value.find((o) => o.value.includes('English'))
    treebank.value = (preferred || schemeTreebanks.value[0])?.value ?? null
  } catch (error) {
    searchError.value = `could not load treebanks: ${error.message}`
  } finally {
    loadingTreebanks.value = false
  }
  validate()
})
</script>

<style>
.controls {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #fff;
}
.grew-editor {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  line-height: 1.45;
}
.grew-snippet {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre;
  font-size: 11px;
}
.cypher {
  background: #f4f4f5;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 11px;
  overflow-x: auto;
  margin: 0;
  max-height: 220px;
}
.opacity-70 {
  opacity: 0.7;
}
.hit {
  padding-bottom: 4px;
}
</style>
