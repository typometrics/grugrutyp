<template>
  <div>
    <!-- ============================================== controls, across the top -->
    <q-card square flat bordered class="controls">
      <q-card-section class="q-py-sm">
        <!-- items-stretch + column layouts: the editor's bottom lines up with the two
             selects' bottoms, instead of every column ending at its own height. -->
        <div class="row q-col-gutter-md items-stretch">
          <div class="col-12 col-md-3 column">
            <q-btn-toggle
              :model-value="scheme" no-caps unelevated dense
              toggle-color="primary" :options="schemeOptions" class="full-width q-mb-sm"
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

          <div class="col-12 col-md-6 column">
            <!-- Opens three lines tall and is *draggable*: the native resize handle
                 replaces autogrow, so a long request can be pulled open by hand. -->
            <q-input
              v-model="request" type="textarea" outlined dense class="col"
              label="Grew request" input-class="grew-editor request-editor"
              :error="!!syntaxError" :error-message="syntaxError"
              @update:model-value="onRequestChange"
              @keydown.ctrl.enter="runSearch"
            />
          </div>

          <div class="col-12 col-md-3 column">
            <q-btn
              color="primary" no-caps icon="search" label="Search" class="q-mb-sm"
              :loading="searching" :disable="!selectedNames.length || !!syntaxError"
              @click="runSearch"
            />
            <q-select
              v-model="featureSet" :options="featureSetOptions" label="Show on trees"
              outlined dense options-dense emit-value map-options
            />
          </div>
        </div>

        <!-- every fold-out control on one line: examples and clustering open panels
             below; Show Cypher and the syntax reference sit right-aligned. -->
        <div class="row items-center q-mt-sm">
          <q-btn
            flat dense no-caps size="sm" icon="auto_stories" class="q-mr-xs"
            :label="examplesOpen ? 'hide examples' : 'examples'"
            @click="examplesOpen = !examplesOpen"
          />
          <span v-if="selectedExample" class="text-caption text-grey-7 q-mr-sm">
            {{ selectedExample }}
          </span>
          <q-btn
            flat dense no-caps size="sm" icon="pivot_table_chart" class="q-mr-xs"
            :color="clusterCount ? 'accent' : undefined"
            :label="clusterOpen ? 'hide clustering' : 'clustering'"
            @click="clusterOpen = !clusterOpen"
          />
          <span v-if="clusterCount && !clusterOpen" class="text-caption text-grey-7">
            {{ clusterSummary }}
          </span>
          <q-space />
          <q-btn
            flat dense no-caps size="sm" icon="code" class="q-mr-sm"
            :label="showCypher ? 'hide Cypher' : 'show Cypher'"
            @click="showCypher = !showCypher"
          />
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
          <div v-show="clusterOpen">
            <div
              v-for="slot in clusterings" :key="slot.n"
              class="row items-center q-gutter-sm q-mt-xs"
            >
              <span class="text-caption text-grey-7">Clustering {{ slot.n }}</span>
              <q-btn-toggle
                v-model="slot.state.mode" dense no-caps unelevated
                toggle-color="primary"
                :options="[
                  { label: 'no', value: 'no' },
                  { label: 'key', value: 'key' },
                  { label: 'whether', value: 'whether' },
                ]"
              />
              <q-input
                v-if="slot.state.mode !== 'no'" v-model="slot.state.value"
                dense outlined class="col" input-class="grew-editor"
                :placeholder="slot.state.mode === 'key'
                  ? 'X.upos · X.lemma · X.Number · e.label'
                  : 'GOV << DEP — a condition; with { … } is implied'"
                @keydown.ctrl.enter="runSearch"
              />
            </div>
          </div>
        </q-slide-transition>
        <q-slide-transition>
          <div v-show="examplesOpen" class="row q-col-gutter-md q-mt-none">
            <div
              v-for="group in exampleSections" :key="group.section"
              class="col-12 col-sm-6 col-md-3"
            >
              <div class="example-section">{{ group.section }}</div>
              <q-list dense>
                <q-item
                  v-for="item in group.items" :key="item.label"
                  clickable dense class="example-item"
                  :active="selectedExample === item.label" active-class="text-accent"
                  @click="useExample(item)"
                >
                  <q-item-section>{{ item.label }}</q-item-section>
                  <q-tooltip class="grew-snippet">{{ item.request }}</q-tooltip>
                </q-item>
              </q-list>
            </div>
          </div>
        </q-slide-transition>

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
        <!-- Sticky: the count, order and pagination stay visible however deep the tree
             list scrolls (the scroller is App.vue's .view-scroll). -->
        <q-card-section class="row items-center q-py-sm results-head">
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
          <!-- next to the count it re-orders, not next to the query it configures -->
          <q-select
            v-if="!result.clusters && !result.grid"
            v-model="sentenceOrder" :options="orderOptions" label="Order"
            outlined dense options-dense emit-value map-options
            class="q-ml-md" style="min-width: 190px"
          />
          <q-space />
          <q-pagination
            v-if="pageCount > 1 && !result.clusters && !result.grid" v-model="page" :max="pageCount"
            :max-pages="8" boundary-numbers dense @update:model-value="runSearch"
          />
        </q-card-section>
        <q-separator />

        <!-- one clustering: a table of counts per value, no trees -->
        <q-card-section v-if="result.clusters" class="q-pt-sm">
          <q-markup-table dense flat bordered class="cluster-table">
            <thead>
              <tr>
                <th class="text-left">{{ result.cluster_labels[0] }}</th>
                <th class="text-right">count</th>
                <th class="text-right">share</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in result.clusters" :key="entry.value">
                <td class="text-left">{{ entry.value }}</td>
                <td class="text-right">{{ entry.count.toLocaleString() }}</td>
                <td class="text-right">
                  {{ result.total ? ((100 * entry.count) / result.total).toFixed(1) : '—' }}%
                </td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>

        <!-- two clusterings: a pivot grid, dominant combinations top-left -->
        <q-card-section v-else-if="result.grid" class="q-pt-sm">
          <div class="text-caption text-grey-7 q-mb-xs">
            rows: {{ result.cluster_labels[0] }} · columns: {{ result.cluster_labels[1] }}
          </div>
          <q-markup-table dense flat bordered class="cluster-grid">
            <thead>
              <tr>
                <th class="text-left"></th>
                <th v-for="col in result.grid.cols" :key="col" class="text-right">{{ col }}</th>
                <th class="text-right text-weight-bold">total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in result.grid.rows" :key="row">
                <td class="text-left text-weight-medium">{{ row }}</td>
                <td v-for="(cell, j) in result.grid.cells[i]" :key="j" class="text-right">
                  {{ cell ? cell.toLocaleString() : '·' }}
                </td>
                <td class="text-right text-weight-bold">
                  {{ result.grid.row_totals[i].toLocaleString() }}
                </td>
              </tr>
              <tr>
                <td class="text-left text-weight-bold">total</td>
                <td v-for="(t, j) in result.grid.col_totals" :key="j" class="text-right text-weight-bold">
                  {{ t.toLocaleString() }}
                </td>
                <td class="text-right text-weight-bold">{{ result.total.toLocaleString() }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>

        <q-card-section v-else-if="!result.hits.length" class="text-grey-7">
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

      <q-card v-else flat bordered :class="$q.dark.isActive ? 'bg-grey-10' : 'bg-grey-1'">
        <q-card-section :class="$q.dark.isActive ? 'text-grey-5' : 'text-grey-7'">
          Pick a treebank, write a Grew request, and the matching trees appear here
          with the matched words highlighted. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> searches.
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
// The primary green is unreadable on a dark background; lighten it there. The orange
// accent reads on both.
const chipColor = computed(() =>
  props.scheme === 'SUD' ? ($q.dark.isActive ? 'green-4' : 'primary') : 'accent',
)

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
const examplesOpen = ref(false)
const clusterOpen = ref(false)
const cluster1 = reactive({ mode: 'no', value: '' })
const cluster2 = reactive({ mode: 'no', value: '' })
const clusterings = [
  { n: 1, state: cluster1 },
  { n: 2, state: cluster2 },
]

function clusterSpecs() {
  return [cluster1, cluster2]
    .filter((c) => c.mode !== 'no' && c.value.trim())
    .map((c) => ({ kind: c.mode, value: c.value.trim() }))
}
const clusterCount = computed(() => clusterSpecs().length)
const clusterSummary = computed(() =>
  clusterSpecs()
    .map((s) => (s.kind === 'key' ? s.value : `whether ${s.value}`))
    .join(' × '),
)

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

// grew.fr's "sentences order". Shuffle is a deterministic hash order, so page 2
// continues page 1 and a shared search reproduces.
const sentenceOrder = ref('initial')
const orderOptions = [
  { label: 'initial — corpus order', value: 'initial' },
  { label: 'by length — shortest first', value: 'length' },
  { label: 'shuffle — mixed, reproducible', value: 'shuffle' },
]
watch(sentenceOrder, () => {
  page.value = 1
  if (result.value) runSearch()
})

// A structured library, grew.fr-style. SUD relation names (comp, mod, subj) differ from
// UD's (obj, amod, nsubj), so every item carries both spellings -- `sud`/`ud`, or one
// `request` when the query names no relation. `clusters` preloads the clustering panel.
const EXAMPLE_SECTIONS = [
  {
    section: 'Basic',
    items: [
      { label: 'A word form', request: 'pattern { X [form="of"] }' },
      { label: 'A lemma', request: 'pattern { X [lemma="be"] }' },
      { label: 'A part of speech', request: 'pattern { X [upos=ADV] }' },
      { label: 'A dependency relation',
        sud: 'pattern { GOV -[comp:obj]-> DEP }',
        ud: 'pattern { GOV -[obj]-> DEP }' },
      { label: 'Relation and POS together',
        sud: 'pattern { V [upos=VERB]; V -[1=subj]-> P [upos=PRON] }',
        ud: 'pattern { V [upos=VERB]; V -[nsubj]-> P [upos=PRON] }' },
      { label: 'Verbs without a subject',
        sud: 'pattern { V [upos=VERB] }\nwithout { V -[1=subj]-> S }',
        ud: 'pattern { V [upos=VERB] }\nwithout { V -[nsubj]-> S }' },
    ],
  },
  {
    section: 'Word order & n-grams',
    items: [
      { label: 'Subject after governor',
        sud: 'pattern { GOV -[1=subj]-> DEP }\nwith { GOV << DEP }',
        ud: 'pattern { GOV -[1=nsubj]-> DEP }\nwith { GOV << DEP }' },
      { label: 'Adjective before noun',
        sud: 'pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] }\nwith { A << N }',
        ud: 'pattern { N [upos=NOUN]; N -[amod]-> A [upos=ADJ] }\nwith { A << N }' },
      { label: 'Determiner–noun bigram',
        request: 'pattern { D [upos=DET]; N [upos=NOUN]; D < N }' },
      { label: 'ADP–DET–NOUN trigram',
        request: 'pattern { A [upos=ADP]; B [upos=DET]; C [upos=NOUN]; A < B; B < C }' },
      { label: 'Bigram of lemmas',
        request: 'pattern { X [lemma="more"]; Y [lemma="than"]; X < Y }' },
    ],
  },
  {
    section: 'Clustering',
    items: [
      { label: 'Governors of nouns, by POS',
        request: 'pattern { X -> Y; Y [upos=NOUN] }',
        clusters: [{ kind: 'key', value: 'X.upos' }] },
      { label: 'Subjects, by their POS',
        sud: 'pattern { V -[1=subj]-> S }', ud: 'pattern { V -[1=nsubj]-> S }',
        clusters: [{ kind: 'key', value: 'S.upos' }] },
      { label: 'Relations out of verbs',
        request: 'pattern { e: V -> D; V [upos=VERB] }',
        clusters: [{ kind: 'key', value: 'e.label' }] },
      { label: 'Subject position (whether)',
        sud: 'pattern { V -[1=subj]-> S }', ud: 'pattern { V -[1=nsubj]-> S }',
        clusters: [{ kind: 'whether', value: 'V << S' }] },
      { label: 'Subject POS × position',
        sud: 'pattern { V -[1=subj]-> S }', ud: 'pattern { V -[1=nsubj]-> S }',
        clusters: [
          { kind: 'key', value: 'S.upos' },
          { kind: 'whether', value: 'V << S' },
        ] },
      { label: 'Dependents per verb (Menzerath)',
        request: 'pattern { V [upos=VERB] }',
        clusters: [{ kind: 'key', value: 'V.n_children' }] },
      { label: 'Constituent size × side (Menzerath)',
        request: 'pattern { V [upos=VERB]; V -> DEP }',
        clusters: [
          { kind: 'key', value: 'DEP.subtree_size' },
          { kind: 'whether', value: 'DEP << V' },
        ] },
    ],
  },
  {
    section: 'Misc',
    items: [
      { label: 'Pronominal object',
        sud: 'pattern { G -[1=comp, 2=obj]-> D }\nwith { D [upos=PRON] }',
        ud: 'pattern { G -[obj]-> D }\nwith { D [upos=PRON] }' },
      { label: 'Non-projective subjects',
        sud: 'pattern { GOV -[1=subj]-> DEP }\nglobal { is_not_projective }',
        ud: 'pattern { GOV -[1=nsubj]-> DEP }\nglobal { is_not_projective }' },
      { label: 'Two objects on one verb',
        sud: 'pattern { V -[1=comp, 2=obj]-> O1; V -[1=comp, 2=obj]-> O2; O1 << O2 }',
        ud: 'pattern { V -[obj]-> O1; V -[obj]-> O2; O1 << O2 }' },
      { label: 'Coordination of unlikes',
        sud: 'pattern { X -[1=conj]-> Y; X [upos=NOUN]; Y [upos=VERB] }',
        ud: 'pattern { X -[conj]-> Y; X [upos=NOUN]; Y [upos=VERB] }' },
    ],
  },
]

const exampleSections = computed(() =>
  EXAMPLE_SECTIONS.map(({ section, items }) => ({
    section,
    items: items
      .map((item) => ({
        ...item,
        request: item.request || (props.scheme === 'SUD' ? item.sud : item.ud),
      }))
      .filter((item) => item.request),
  })),
)

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
  // An example defines its whole setup: loading one without clusters must also clear a
  // leftover clustering, or the panel silently reinterprets the new query.
  const specs = example.clusters || []
  for (const [i, state] of [cluster1, cluster2].entries()) {
    state.mode = specs[i]?.kind || 'no'
    state.value = specs[i]?.value || ''
  }
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
      order: sentenceOrder.value,
      clusters: clusterSpecs(),
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
.body--dark .controls {
  background: #1d1d1d;
}
.hit {
  padding-bottom: 4px;
}
.cluster-table {
  max-width: 520px;
}
.cluster-grid {
  max-width: 100%;
  overflow-x: auto;
}
.example-section {
  font-variant: small-caps;
  letter-spacing: 0.04em;
  font-weight: 600;
  color: var(--q-primary);
  padding: 2px 0 2px 8px;
}
.body--dark .example-section {
  color: #9fbf9a;
}
.example-item {
  min-height: 26px;
  font-size: 13px;
}
/* Draggable height: the native handle, since autogrow and manual resize fight. */
:deep(.request-editor) {
  resize: vertical;
  min-height: 96px;
}
.results-head {
  position: sticky;
  top: 0;
  z-index: 3;
  background: #fff;
}
.body--dark .results-head {
  background: #1d1d1d;
}
</style>
