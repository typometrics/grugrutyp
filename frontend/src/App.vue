<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title class="text-weight-bold">
          grugrutyp
          <span class="text-caption q-ml-sm opacity-70">
            Grew queries over UD &amp; SUD treebanks
          </span>
        </q-toolbar-title>
        <q-btn
          flat dense no-caps icon="help_outline" label="Grew syntax"
          href="https://grew.fr/doc/request/" target="_blank"
        />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <q-page class="q-pa-md">
        <div class="row q-col-gutter-md">
          <!-- ------------------------------------------------------- query panel -->
          <div class="col-12 col-md-5">
            <q-card flat bordered>
              <q-card-section class="q-gutter-md">
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
                          {{ scope.opt.n_sents.toLocaleString() }} sentences ·
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

                <div>
                  <div class="text-caption text-grey-8 q-mb-xs">Grew request</div>
                  <q-input
                    v-model="request" type="textarea" outlined dense autogrow
                    input-class="grew-editor" :error="!!syntaxError"
                    :error-message="syntaxError" @update:model-value="onRequestChange"
                  />
                </div>

                <div class="row items-center q-gutter-sm">
                  <q-btn
                    color="primary" no-caps icon="search" label="Search"
                    :loading="searching" :disable="!treebank || !!syntaxError"
                    @click="runSearch"
                  />
                  <q-space />
                  <q-btn
                    flat dense no-caps size="sm" icon="code"
                    :label="showCypher ? 'Hide Cypher' : 'Show Cypher'"
                    @click="showCypher = !showCypher"
                  />
                </div>

                <q-slide-transition>
                  <pre v-if="showCypher && cypher" class="cypher">{{ cypher }}</pre>
                </q-slide-transition>
              </q-card-section>
            </q-card>

            <q-card flat bordered class="q-mt-md">
              <q-card-section>
                <div class="text-subtitle2 q-mb-sm">Examples</div>
                <q-list dense separator>
                  <q-item
                    v-for="example in examples" :key="example.label"
                    clickable v-ripple @click="useExample(example)"
                  >
                    <q-item-section>
                      <q-item-label>{{ example.label }}</q-item-label>
                      <q-item-label caption class="grew-snippet">
                        {{ example.request }}
                      </q-item-label>
                    </q-item-section>
                  </q-item>
                </q-list>
              </q-card-section>
            </q-card>
          </div>

          <!-- ------------------------------------------------------ results panel -->
          <div class="col-12 col-md-7">
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
                  :max-pages="6" boundary-numbers dense @update:model-value="runSearch"
                />
              </q-card-section>
              <q-separator />

              <q-card-section v-if="!result.hits.length" class="text-grey-7">
                No sentence matches this request in {{ treebank }}.
              </q-card-section>

              <q-list v-else separator>
                <q-item v-for="hit in result.hits" :key="hit.sent_id" class="column">
                  <div class="row items-center full-width q-mb-xs">
                    <span class="text-caption text-grey-7">{{ hit.sent_id }}</span>
                    <q-space />
                    <q-btn
                      flat dense size="sm" icon="content_copy" no-caps label="CoNLL-U"
                      @click="copy(hit.conllu)"
                    />
                  </div>
                  <DepTree :conllu="hit.conllu" :matched="hit.matched_nodes" />
                </q-item>
              </q-list>
            </q-card>

            <q-card v-else flat bordered class="bg-grey-1">
              <q-card-section class="text-grey-7">
                Pick a treebank, write a Grew request, and the matching trees appear here
                with the matched words highlighted.
              </q-card-section>
            </q-card>
          </div>
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

// SUD relation names (comp, mod, subj) differ from UD's (obj, amod, nsubj), so the
// examples follow the selected scheme rather than pretending one set works for both.
const examples = computed(() =>
  scheme.value === 'SUD'
    ? [
        {
          label: 'Subject after its governor',
          request: 'pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }',
        },
        {
          label: 'Adjective before its noun',
          request:
            'pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] }\nwith { A << N }',
        },
        {
          label: 'Pronominal object',
          request: 'pattern { G -[1=comp, 2=obj]-> D }\nwith { D [upos=PRON] }',
        },
        {
          label: 'Non-projective subject',
          request: 'pattern { GOV -[1=subj]-> DEP }\nglobal { is_not_projective }',
        },
      ]
    : [
        {
          label: 'Subject after its governor',
          request: 'pattern { GOV -[1=nsubj]-> DEP }\nwith { GOV << DEP }',
        },
        {
          label: 'Adjective before its noun',
          request:
            'pattern { N [upos=NOUN]; N -[amod]-> A [upos=ADJ] }\nwith { A << N }',
        },
        {
          label: 'Pronominal object',
          request: 'pattern { G -[obj]-> D }\nwith { D [upos=PRON] }',
        },
        {
          label: 'Non-projective subject',
          request: 'pattern { GOV -[nsubj]-> DEP }\nglobal { is_not_projective }',
        },
      ],
)

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
  if (!treebank.value) return
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

watch(scheme, () => {
  treebank.value = null
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
.grew-editor {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  line-height: 1.5;
}
.grew-snippet {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  font-size: 11px;
}
.cypher {
  background: #f4f4f5;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 11px;
  overflow-x: auto;
  margin: 0;
}
.opacity-70 {
  opacity: 0.7;
}
</style>
