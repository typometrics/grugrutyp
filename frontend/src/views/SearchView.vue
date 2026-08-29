<template>
  <div>
    <!-- ============================================== controls, across the top -->
    <q-card square flat bordered class="controls">
      <q-card-section class="q-py-sm">
        <div class="row q-col-gutter-md items-start">
          <div class="col-12 col-md-3 column q-gutter-sm">
            <q-btn-toggle
              :model-value="scheme" no-caps unelevated dense
              toggle-color="primary" :options="schemeOptions" class="full-width"
              @update:model-value="(v) => $emit('update:scheme', v)"
            />
            <q-select
              v-model="selection" :options="treebankOptions" label="Treebanks"
              multiple use-chips use-input input-debounce="0" emit-value map-options
              outlined dense options-dense @filter="filterTreebanks"
            >
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label :class="{ 'text-weight-medium': scope.opt.whole }">
                      {{ scope.opt.label }}
                    </q-item-label>
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
            <!-- min-height for three lines up front: nearly every request is a pattern
                 plus a with/global clause, and an editor that opens at one cramped line
                 shows a query cut in half. autogrow still extends it further. -->
            <q-input
              v-model="request" type="textarea" outlined dense autogrow
              label="Grew request" input-class="grew-editor"
              input-style="min-height: 66px"
              :error="!!syntaxError" :error-message="syntaxError"
              @update:model-value="onRequestChange"
              @keydown.ctrl.enter="runSearch"
            />
          </div>

          <div class="col-12 col-md-3 column q-gutter-sm">
            <q-btn
              color="primary" no-caps icon="search" label="Search"
              :loading="searching" :disable="!selectedNames.length || !!syntaxError"
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
            clickable dense :color="chipColor"
            :outline="selectedExample !== example.label"
            :text-color="selectedExample === example.label ? 'white' : undefined"
            icon="play_arrow" @click="useExample(example)"
          >
            {{ example.label }}
            <q-tooltip class="grew-snippet">{{ example.request }}</q-tooltip>
          </q-chip>
          <q-chip
            dense outline clickable :color="chipColor" class="text-weight-medium"
            icon-right="open_in_new"
            @click="openSyntaxDoc"
          >
            {{ scheme }} syntax
            <q-tooltip>Grew request syntax reference (grew.fr)</q-tooltip>
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
            <span v-if="result.n_treebanks > 1" class="text-caption text-grey-7 q-ml-sm">
              in {{ result.n_treebanks }} treebanks
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
          No sentence matches this request in the selected
          treebank{{ result.n_treebanks === 1 ? '' : 's' }}.
        </q-card-section>

        <div v-else>
          <div v-for="hit in result.hits" :key="hit.sent_id" class="hit">
            <div class="row items-center q-px-md q-pt-sm">
              <span class="text-caption text-grey-7">{{ hit.sent_id }}</span>
              <q-badge
                v-if="result.n_treebanks > 1" outline color="secondary" class="q-ml-sm"
              >
                {{ hit.treebank.replace(/^S?UD_/, '') }}
              </q-badge>
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
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api } from '../api'
import DepTree from '../components/DepTree.vue'

const props = defineProps({
  treebanks: { type: Array, default: () => [] },
  scheme: { type: String, default: 'SUD' },
})
defineEmits(['update:scheme'])

const $q = useQuasar()

const schemeOptions = [
  { label: 'SUD', value: 'SUD' },
  { label: 'UD', value: 'UD' },
]
const chipColor = computed(() => (props.scheme === 'SUD' ? 'primary' : 'accent'))

const treebankFilter = ref('')
// Treebank names, plus `lang:<Language>` pseudo-entries meaning "every treebank of that
// language". Resolution to concrete names happens at search time, so a whole-language
// selection follows the scheme toggle for free.
const selection = ref([])

const request = ref('pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }')
const syntaxError = ref('')
const cypher = ref('')
const showCypher = ref(false)

const selectedExample = ref('')
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
  { label: 'Subject after governor', scheme: 'SUD',
    request: 'pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }' },
  { label: 'Subject after governor', scheme: 'UD',
    request: 'pattern { GOV -[1=nsubj]-> DEP }\nwith { GOV << DEP }' },
  { label: 'Adjective before noun', scheme: 'SUD',
    request: 'pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] }\nwith { A << N }' },
  { label: 'Adjective before noun', scheme: 'UD',
    request: 'pattern { N [upos=NOUN]; N -[amod]-> A [upos=ADJ] }\nwith { A << N }' },
  { label: 'Pronominal object', scheme: 'SUD',
    request: 'pattern { G -[1=comp, 2=obj]-> D }\nwith { D [upos=PRON] }' },
  { label: 'Pronominal object', scheme: 'UD',
    request: 'pattern { G -[obj]-> D }\nwith { D [upos=PRON] }' },
  { label: 'Non-projective', scheme: 'SUD',
    request: 'pattern { GOV -[1=subj]-> DEP }\nglobal { is_not_projective }' },
  { label: 'Non-projective', scheme: 'UD',
    request: 'pattern { GOV -[1=nsubj]-> DEP }\nglobal { is_not_projective }' },
]
const examples = computed(() => EXAMPLES.filter((e) => e.scheme === props.scheme))

const schemeTreebanks = computed(() =>
  props.treebanks
    .filter((tb) => tb.scheme === props.scheme)
    .map((tb) => ({
      label: `${tb.language.replace(/_/g, ' ')} — ${tb.corpus}`,
      value: tb.name,
      language: tb.language,
      family: tb.family,
      n_sents: tb.n_sents,
      n_tokens: tb.n_tokens,
    })),
)

// Each multi-treebank language gets a "whole language" entry ahead of its treebanks.
const groupedOptions = computed(() => {
  const byLanguage = new Map()
  for (const option of schemeTreebanks.value) {
    if (!byLanguage.has(option.language)) byLanguage.set(option.language, [])
    byLanguage.get(option.language).push(option)
  }
  const out = []
  for (const [language, members] of byLanguage) {
    if (members.length > 1) {
      out.push({
        label: `${language.replace(/_/g, ' ')} — whole language (${members.length} treebanks)`,
        value: `lang:${language}`,
        whole: true,
        family: members[0].family,
        n_tokens: members.reduce((sum, m) => sum + m.n_tokens, 0),
      })
    }
    out.push(...members)
  }
  return out
})

const treebankOptions = computed(() => {
  const needle = treebankFilter.value.toLowerCase()
  if (!needle) return groupedOptions.value
  return groupedOptions.value.filter((o) => o.label.toLowerCase().includes(needle))
})

/** The concrete treebank names the current selection stands for. */
const selectedNames = computed(() => {
  const names = new Set()
  for (const value of selection.value) {
    if (value.startsWith('lang:')) {
      const language = value.slice(5)
      for (const option of schemeTreebanks.value) {
        if (option.language === language) names.add(option.value)
      }
    } else {
      names.add(value)
    }
  }
  return [...names].sort()
})

const pageCount = computed(() =>
  result.value ? Math.ceil(Math.min(result.value.total, 500) / PAGE_SIZE) : 0,
)

function filterTreebanks(value, update) {
  update(() => {
    treebankFilter.value = value
  })
}

function openSyntaxDoc() {
  window.open('https://grew.fr/doc/request/', '_blank', 'noopener')
}

function useExample(example) {
  request.value = example.request
  onRequestChange()
  // After onRequestChange, which clears it: an example's name holds only until the query
  // stops being that example.
  selectedExample.value = example.label
}

async function copy(text) {
  await navigator.clipboard.writeText(text)
  $q.notify({ message: 'CoNLL-U copied', timeout: 1200, position: 'bottom-right' })
}

let validateTimer = null
function onRequestChange() {
  selectedExample.value = ''
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
  if (!selectedNames.value.length || syntaxError.value) return
  searching.value = true
  searchError.value = ''
  try {
    result.value = await api.search({
      treebanks: selectedNames.value,
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

/** Arriving from a point on the plot: show what that scope actually matched. */
function openQuery({ treebank: name, request: text }) {
  selection.value = [name]
  request.value = text
  selectedExample.value = ''
  page.value = 1
  validate().then(runSearch)
}
defineExpose({ openQuery })

function pickDefaultTreebank() {
  if (selectedNames.value.length) return
  // GUM specifically, not the first English alphabetically (which is Atis -- a small
  // domain corpus of flight queries, a strange first impression of the tool). GUM's size
  // costs little here: the tree search returns a page of hits and stops.
  const preferred =
    schemeTreebanks.value.find((o) => o.value.endsWith('English-GUM')) ||
    schemeTreebanks.value.find((o) => o.value.includes('English'))
  const fallback = (preferred || schemeTreebanks.value[0])?.value
  selection.value = fallback ? [fallback] : []
}

// Switching scheme keeps the same corpora: SUD_English-GUM <-> UD_English-GUM. Dropping
// the selection on every toggle made comparing the two annotations of one corpus tedious
// -- which is one of the main reasons to have both schemes side by side at all.
// Whole-language entries (`lang:X`) survive unchanged: they resolve against the new
// scheme's treebank list at search time.
watch(
  () => props.scheme,
  (next) => {
    selection.value = selection.value
      .map((value) => {
        if (value.startsWith('lang:')) return value
        const current = props.treebanks.find((tb) => tb.name === value)
        if (!current) return null
        const twin = props.treebanks.find(
          (tb) =>
            tb.scheme === next && tb.language === current.language && tb.corpus === current.corpus,
        )
        return twin ? twin.name : null
      })
      .filter(Boolean)
    if (!selection.value.length) pickDefaultTreebank()
    result.value = null
  },
)

watch(selection, () => {
  page.value = 1
  result.value = null
})

watch(() => props.treebanks, pickDefaultTreebank)

onMounted(() => {
  pickDefaultTreebank()
  validate()
})
</script>

<style scoped>
.controls {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #fff;
}
.hit {
  padding-bottom: 4px;
}
</style>
