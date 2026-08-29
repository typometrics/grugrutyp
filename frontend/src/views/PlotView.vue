<template>
  <div class="column full-height">
    <!-- ================================== axis panels, across the top (Kim's layout) -->
    <div class="axes q-pa-sm">
      <div class="row q-col-gutter-sm items-stretch">
        <div :class="yCollapsed ? 'col-12' : 'col-12 col-md-6'">
          <AxisPanel
            axis="x" :presets="presets" :treebank="previewTreebank" :label="x.label"
            v-model:scope="x.scope" v-model:response="x.response"
            v-model:kind="x.kind" v-model:expression="x.expression"
            v-model:aggregation="x.aggregation" v-model:unit="x.unit"
            @label="(v) => (x.label = v)"
          />
        </div>
        <div :class="yCollapsed ? 'col-12' : 'col-12 col-md-6'">
          <AxisPanel
            axis="y" :presets="presets" :treebank="previewTreebank" collapsible :label="y.label"
            v-model:scope="y.scope" v-model:response="y.response"
            v-model:kind="y.kind" v-model:expression="y.expression"
            v-model:aggregation="y.aggregation" v-model:unit="y.unit"
            v-model:collapsed="yCollapsed" @label="(v) => (y.label = v)"
          />
        </div>
      </div>

      <div class="row items-center q-gutter-sm q-mt-sm">
        <q-btn-toggle
          v-model="scheme" no-caps unelevated dense toggle-color="primary"
          :options="[{ label: 'SUD', value: 'SUD' }, { label: 'UD', value: 'UD' }]"
        />
        <q-btn
          color="primary" no-caps icon="scatter_plot"
          :label="running ? 'Computing…' : 'Plot'" :loading="running" @click="runPlot"
        />
        <q-btn v-if="running" flat dense no-caps icon="stop" label="Stop" @click="stopPlot" />
        <!-- Everything a first-time user does not need lives behind this. The defaults
             are the ones worth defaulting; the interface should not make every visitor
             read six controls to plot one preset. -->
        <q-btn
          flat dense no-caps icon="tune"
          :label="optionsOpen ? 'hide options' : 'options'"
          @click="optionsOpen = !optionsOpen"
        />
        <q-space />
        <q-btn-dropdown flat dense no-caps icon="ios_share" label="share" auto-close>
          <q-list dense>
            <q-item clickable @click="copyLink">
              <q-item-section avatar><q-icon name="link" size="18px" /></q-item-section>
              <q-item-section>
                Copy link
                <q-item-label caption>a URL that reproduces this plot exactly</q-item-label>
              </q-item-section>
            </q-item>
            <q-item clickable :disable="!points.length" @click="exportSvg">
              <q-item-section avatar><q-icon name="polyline" size="18px" /></q-item-section>
              <q-item-section>
                SVG
                <q-item-label caption>vector, for papers</q-item-label>
              </q-item-section>
            </q-item>
            <q-item clickable :disable="!points.length" @click="exportPng">
              <q-item-section avatar><q-icon name="image" size="18px" /></q-item-section>
              <q-item-section>PNG</q-item-section>
            </q-item>
            <q-item clickable :disable="!points.length" @click="exportTsv">
              <q-item-section avatar><q-icon name="download" size="18px" /></q-item-section>
              <q-item-section>
                TSV
                <q-item-label caption>the numbers behind the plot</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>
      </div>

      <q-slide-transition>
        <div v-show="optionsOpen" class="row items-center q-gutter-sm q-mt-sm">
          <q-select
            v-model="colourBy" :options="viewOptions" label="Colour by" dense options-dense
            outlined emit-value map-options style="min-width: 150px"
          />
          <q-select
            v-model="budget" :options="budgetOptions" label="Corpus coverage" dense options-dense
            outlined emit-value map-options style="min-width: 210px"
          />
          <q-select
            v-model="labelMode" label="Language names" dense options-dense
            outlined emit-value map-options style="min-width: 160px"
            :options="[
              { label: 'readable (non-overlapping)', value: 'optimal' },
              { label: 'all', value: 'all' },
              { label: 'none', value: 'none' },
            ]"
          />
          <div style="width: 190px">
            <div class="text-caption text-grey-7">min. scope matchings: {{ minScope }}</div>
            <q-slider v-model="minScope" :min="0" :max="500" :step="10" dense />
          </div>
          <q-toggle v-model="showErrorBars" dense label="Error bars" />
          <q-toggle v-model="showDiagonal" dense label="Diagonal" :disable="yCollapsed">
            <q-tooltip>Draw the y = x line — which side a language falls on</q-tooltip>
          </q-toggle>
          <q-toggle v-model="squarePlot" dense label="Square" :disable="yCollapsed">
            <q-tooltip>Same length for both axes — fair when they share a scale</q-tooltip>
          </q-toggle>
        </div>
      </q-slide-transition>

      <div v-if="progress.total" class="q-mt-xs">
        <q-linear-progress
          :value="progress.done / progress.total" size="4px"
          :color="running ? 'primary' : 'green'"
        />
        <div class="text-caption text-grey-7 q-mt-xs">
          {{ progress.done }} / {{ progress.total }} treebanks ·
          {{ points.length }} languages ·
          {{ elapsed.toFixed(1) }}s
          <span v-if="cachedCount"> · {{ cachedCount }} from cache</span>
          <span v-if="escalatedCount"> · {{ escalatedCount }} refined on a larger sample</span>
          <span v-if="belowScopeCount" class="text-orange-9">
            · {{ belowScopeCount }} below the minimum scope
          </span>
          <span
            v-if="noDataCount" class="text-grey-6"
            title="the scope matched nothing on at least one axis for these languages"
          >
            · {{ noDataCount }} with no matches
          </span>
          <!-- The tail is the whole wait on this hardware: cache hits stream out in the
               first second, then the run grinds the big cold treebanks. Saying WHICH ones
               turns "hung?" into "ah, Czech". -->
          <span v-if="running && pendingGiants.length" class="text-grey-6">
            · computing {{ pendingGiants.join(', ') }}…
          </span>
        </div>
      </div>

      <q-banner v-if="error" dense class="bg-red-1 text-red-9 q-mt-sm">
        <template #avatar><q-icon name="error_outline" /></template>
        {{ error }}
      </q-banner>
    </div>

    <!-- ============================================ the plot, full width underneath -->
    <div class="col plot-area q-px-sm q-pb-sm">
      <ScatterPlot
        v-if="points.length" ref="plot" :points="points"
        :x-label="xLabel" :y-label="yLabel" :one-dimensional="yCollapsed"
        :x-percent="x.kind !== 'aggregate'" :y-percent="y.kind !== 'aggregate'"
        :label-mode="labelMode" :show-error-bars="showErrorBars" :show-diagonal="showDiagonal"
        :square="squarePlot"
        @pick="inspect"
      />
      <q-card v-else flat bordered class="bg-grey-1 full-height column flex-center">
        <q-card-section class="text-grey-7 text-center" style="max-width: 620px">
          <div class="text-subtitle1 q-mb-sm">A measure is a pair of Grew requests.</div>
          <div>
            The <b>scope (S)</b> says what to count — all subject relations, say. The
            <b>response (Q)</b> says which of those also do something — the dependent
            follows its governor. The value plotted for each language is
            <b>100 × #(S ∧ Q) / #(S)</b>.
          </div>
          <div class="q-mt-sm">
            Load a preset into either axis to see the shape, then edit it. Collapse the Y
            axis for a one-dimensional strip.
          </div>
          <div class="q-mt-sm">
            The request language is Grew —
            <a href="https://grew.fr/doc/request/" target="_blank" rel="noopener">
              syntax reference</a>.
          </div>
        </q-card-section>
      </q-card>
    </div>

    <!-- point -> the treebanks behind it -> the sentences, which the old site cannot do -->
    <q-dialog v-model="detailOpen">
      <q-card style="min-width: 460px; max-width: 720px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">{{ (detail?.language || '').replace(/_/g, ' ') }}</div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-card-section v-if="detail">
          <div class="row q-col-gutter-md">
            <div class="col">
              <div class="text-caption text-grey-7">{{ xLabel }}</div>
              <div class="text-h5">
                {{ detail.x.toFixed(2) }}{{ x.kind !== 'aggregate' ? '%' : '' }}
              </div>
              <div class="text-caption text-grey-7" v-if="detail.xCi">
                95% {{ detail.xCi[0].toFixed(2) }}–{{ detail.xCi[1].toFixed(2) }}
              </div>
            </div>
            <div class="col" v-if="!yCollapsed">
              <div class="text-caption text-grey-7">{{ yLabel }}</div>
              <div class="text-h5">
                {{ detail.y.toFixed(2) }}{{ y.kind !== 'aggregate' ? '%' : '' }}
              </div>
              <div class="text-caption text-grey-7" v-if="detail.yCi">
                95% {{ detail.yCi[0].toFixed(2) }}–{{ detail.yCi[1].toFixed(2) }}
              </div>
            </div>
          </div>
          <div class="text-caption text-grey-7 q-mt-sm">
            {{ detail.n_hit.toLocaleString() }} of {{ detail.n_scope.toLocaleString() }}
            matchings, summed over {{ detail.n_treebanks }}
            treebank{{ detail.n_treebanks === 1 ? '' : 's' }}.
            <span v-if="detail.escalated">Computed on the full corpus after a sample proved too imprecise.</span>
            <span v-else-if="detail.sampled">Computed on a sub-corpus.</span>
          </div>
          <q-list dense bordered class="q-mt-md rounded-borders">
            <q-item
              v-for="name in languageTreebanks(detail.language)" :key="name"
              clickable @click="openInSearch(name)"
            >
              <q-item-section>{{ name }}</q-item-section>
              <q-item-section side><q-icon name="open_in_new" size="16px" /></q-item-section>
            </q-item>
          </q-list>
          <div class="text-caption text-grey-6 q-mt-sm">
            Opens the scope in the search tab, where the matching sentences are drawn as trees.
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api } from '../api'
import AxisPanel from '../components/AxisPanel.vue'
import ScatterPlot from '../components/ScatterPlot.vue'

const props = defineProps({ treebanks: { type: Array, default: () => [] } })
const emit = defineEmits(['open-search'])

const $q = useQuasar()

const scheme = ref('SUD')
const presets = ref([])
const colourBy = ref('family')
const viewOptions = ref([{ label: 'family', value: 'family' }])
const languageStyles = ref({})

const AXIS_DEFAULTS = { scope: '', response: '', label: '', kind: 'ratio', expression: '', aggregation: 'avg', unit: '%' }
const x = reactive({ ...AXIS_DEFAULTS })
const y = reactive({ ...AXIS_DEFAULTS })
const yCollapsed = ref(false)

const budget = ref(100000)
const budgetOptions = [
  { label: 'Fast — 100k tokens/language', value: 100000 },
  { label: 'Closer — 500k tokens/language', value: 500000 },
  { label: 'Exact — no sampling', value: 0 },
]
const minScope = ref(30)
const showErrorBars = ref(false)
const labelMode = ref('optimal')
const showDiagonal = ref(false)
const squarePlot = ref(false)
const optionsOpen = ref(false)

const running = ref(false)
const error = ref('')
const progress = reactive({ done: 0, total: 0 })
const elapsed = ref(0)
const rawLanguages = ref([[], []])
const perTreebank = ref([])
const plot = ref(null)
let handle = null
let timer = null

const detailOpen = ref(false)
const detail = ref(null)

/**
 * An axis caption, derived from the query when no preset named it.
 *
 * `pattern { GOV -[1=comp,2=obj]-> DEP }` + `with { GOV << DEP }` reads as
 * "comp:obj — governor first". Crude, but it is derived from the query that produced the
 * numbers, so it cannot contradict them, which a stale preset name can.
 */
function describe(axis, fallback) {
  if (axis.label) return axis.label
  if (!axis.scope.trim()) return fallback
  if (axis.kind === 'aggregate') {
    return axis.expression ? `${axis.aggregation} ${axis.expression}` : fallback
  }

  const edge = /-\[([^\]]+)\]->/.exec(axis.scope)
  let subject = fallback
  if (edge) {
    // `1=comp, 2=obj` -> `comp:obj`; a plain `subj` stays `subj`.
    const parts = [...edge[1].matchAll(/\d+\s*=\s*([A-Za-z_:@]+)/g)].map((m) => m[1])
    subject = parts.length ? parts.join(':') : edge[1]
  } else if (/\[\s*upos\s*=/.test(axis.scope)) {
    subject = 'POS'
  }

  const response = axis.response
  let sense = ''
  if (/<</.test(response) || /(?<![<>])<(?!<)/.test(response)) sense = ' — governor first'
  else if (/upos\s*=\s*(\w+)/.test(response)) sense = ` — ${/upos\s*=\s*(\w+)/.exec(response)[1]}`
  else if (/-\[/.test(response)) sense = ' — share'
  if (/^\s*without/.test(response)) sense += ' (negated)'

  return subject + sense
}

const xLabel = computed(() => describe(x, 'X'))
const yLabel = computed(() => describe(y, 'Y'))
const cachedCount = computed(() => perTreebank.value.filter((r) => r.axes[0].cached).length)

/** The largest treebanks not yet returned -- what the run is actually waiting on. */
const pendingGiants = computed(() => {
  if (!progress.total) return []
  const arrived = new Set(perTreebank.value.map((r) => r.treebank))
  return props.treebanks
    .filter((tb) => tb.scheme === scheme.value && !arrived.has(tb.name))
    .sort((a, b) => b.n_tokens - a.n_tokens)
    .slice(0, 3)
    .map((tb) => `${tb.name.replace(/^S?UD_/, '')} (${(tb.n_tokens / 1e6).toFixed(1)}M)`)
})
const escalatedCount = computed(() => perTreebank.value.filter((r) => r.axes[0].escalated).length)

/**
 * The plotted points.
 *
 * The minimum-scope filter is applied *here*, not in the backend, so that moving the
 * slider is instant and does not re-query 705 treebanks. It replaces the old site's
 * `axminocc`, with the difference that the threshold is visible and the count of what it
 * removed is shown rather than silently dropped.
 */
const plotState = computed(() => {
  const [xs, ys] = rawLanguages.value
  if (!xs.length) return { points: [], belowScope: 0, noData: 0 }
  const yByLanguage = new Map(ys.map((entry) => [entry.language, entry]))

  const out = []
  // Two different reasons keep a language off the plot, and they must not share a label:
  // "below the minimum scope" is the slider's doing and moves with it, while a language
  // whose scope matched nothing (on either axis) is absent at any threshold -- reporting
  // it as "below the minimum scope" at slider 0 reads as a bug, and was reported as one.
  let belowScope = 0
  let noData = 0
  for (const entry of xs) {
    const other = yByLanguage.get(entry.language)
    if (entry.value == null || (!yCollapsed.value && (!other || other.value == null))) {
      noData += 1
      continue
    }
    if (entry.n_scope < minScope.value || (!yCollapsed.value && other.n_scope < minScope.value)) {
      belowScope += 1
      continue
    }
    const style = languageStyles.value[entry.language] || {}
    out.push({
      language: entry.language,
      x: entry.value,
      y: yCollapsed.value ? 0 : other.value,
      n_scope: entry.n_scope,
      n_hit: entry.n_hit,
      n_treebanks: entry.n_treebanks,
      sampled: entry.sampled,
      escalated: entry.escalated,
      provisional: !!entry.provisional,
      // Not [null, null]: provisional merges and aggregates carry no interval, and a
      // truthy-but-empty pair made the detail dialog throw on `xCi[0].toFixed` -- the
      // dialog then rendered its title and nothing else.
      xCi: entry.ci_low != null ? [entry.ci_low, entry.ci_high] : null,
      yCi:
        !yCollapsed.value && other.ci_low != null ? [other.ci_low, other.ci_high] : null,
      label: style.label || 'unknown',
      color: (style.color || 'darkgrey').toLowerCase(),
      marker: style.marker || 'circle',
    })
  }
  return { points: out, belowScope, noData }
})

const points = computed(() => plotState.value.points)
const belowScopeCount = computed(() => plotState.value.belowScope)
const noDataCount = computed(() => plotState.value.noData)

const previewTreebank = computed(() => {
  const candidates = props.treebanks.filter((tb) => tb.scheme === scheme.value)
  const english = candidates.find((tb) => tb.language === 'English')
  return (english || candidates[0])?.name || ''
})

function languageTreebanks(language) {
  return props.treebanks
    .filter((tb) => tb.scheme === scheme.value && tb.language === language)
    .map((tb) => tb.name)
}

function inspect(point) {
  detail.value = point
  detailOpen.value = true
}

function openInSearch(treebank) {
  detailOpen.value = false
  // The scope alone, not the combined request: the point of looking is usually to see
  // what the scope actually matched.
  emit('open-search', { treebank, request: x.scope, scheme: scheme.value })
}

async function loadPresets() {
  const response = await api.presets(scheme.value)
  presets.value = response.presets
  // Load the classic axes on first arrival so the page is not an empty form: subject
  // position against object position is the plot the current site opens on.
  if (!x.scope) {
    const head = presets.value.find((p) => p.key === 'head-initiality')
    if (head) {
      x.scope = head.scope
      x.response = head.response
      x.label = head.name // the preset's own name, so the picker shows the selection
    }
    const order = presets.value.find((p) => p.key === 'subj-obj-order')
    if (order) {
      y.scope = order.scope
      y.response = order.response
      y.label = order.name
    }
  }
}

async function loadStyles() {
  const response = await api.languages(colourBy.value)
  viewOptions.value = response.views.map((v) => ({ label: v.replace(/_/g, ' '), value: v }))
  const styles = {}
  for (const item of response.languages) styles[item.language] = item
  languageStyles.value = styles
}

function axisBody(axis) {
  return {
    scope: axis.scope,
    response: axis.kind === 'aggregate' ? '' : axis.response,
    kind: axis.kind,
    expression: axis.expression,
    aggregation: axis.aggregation,
    label: axis.label,
  }
}

function stopPlot() {
  if (handle) handle.abort()
  running.value = false
  clearInterval(timer)
}

async function runPlot() {
  stopPlot()
  error.value = ''
  running.value = true
  progress.done = 0
  progress.total = 0
  perTreebank.value = []
  rawLanguages.value = [[], []]
  elapsed.value = 0
  const started = performance.now()
  timer = setInterval(() => (elapsed.value = (performance.now() - started) / 1000), 100)

  const body = {
    x: axisBody(x),
    y: yCollapsed.value ? null : axisBody(y),
    scheme: scheme.value,
    token_budget: budget.value || null,
    min_scope: minScope.value,
  }

  handle = api.measure(body, (name, data) => {
    if (name === 'start') {
      progress.total = data.n_treebanks
    } else if (name === 'point') {
      progress.done = data.done
      perTreebank.value.push(data)
      // The per-language merge arrives with the `done` event, because summing counts
      // across a language's treebanks cannot be done incrementally. Until then, show the
      // treebanks that have landed as provisional language points -- the plot fills in,
      // which is the entire reason the endpoint streams.
      mergeProvisional()
    } else if (name === 'done') {
      rawLanguages.value = [data.languages[0] || [], data.languages[1] || []]
      if (data.errors.length) {
        error.value = `${data.errors.length} treebank(s) failed: ${data.errors
          .slice(0, 3)
          .map((e) => e.treebank)
          .join(', ')}${data.errors.length > 3 ? '…' : ''}`
      }
    } else if (name === 'error') {
      error.value = data.message
    }
  })

  try {
    await handle.done
  } catch (exception) {
    if (exception.name !== 'AbortError') error.value = exception.message
  } finally {
    running.value = false
    clearInterval(timer)
  }
}

const expectedCounts = computed(() => {
  const counts = {}
  for (const tb of props.treebanks) {
    if (tb.scheme === scheme.value) counts[tb.language] = (counts[tb.language] || 0) + 1
  }
  return counts
})

/** Sum the arrived treebanks per language -- the same rule the backend applies at the end. */
function mergeProvisional() {
  const axes = [new Map(), new Map()]
  for (const row of perTreebank.value) {
    row.axes.forEach((axis, i) => {
      if (axis.error || !axis.n_scope) return
      const entry = axes[i].get(row.language) || {
        language: row.language, n_scope: 0, n_hit: 0, n_treebanks: 0,
        sampled: false, escalated: false,
      }
      entry.n_scope += axis.n_scope
      entry.n_hit += axis.n_hit
      entry.kind = axis.kind
      if (axis.total != null) entry.total = (entry.total || 0) + axis.total
      entry.n_treebanks += 1
      entry.sampled = entry.sampled || axis.sample_pct < 100
      entry.escalated = entry.escalated || axis.escalated
      // A language point is the weighted sum over its treebanks. The backend evaluates a
      // language as one unit, so normally they all arrive in one burst and the point lands
      // once, complete -- but if a treebank inside the burst errored out, the point is
      // genuinely partial, and that has to LOOK deliberate rather than like drift.
      entry.provisional = entry.n_treebanks < (expectedCounts.value[row.language] || 1)
      axes[i].set(row.language, entry)
    })
  }
  // Provisional merging only works for the ratio kind, where the numerator is a count.
  // An aggregate's provisional value would need its accumulator, which the point event
  // does carry -- `total` -- so both use the same weighted-quotient rule.
  rawLanguages.value = axes.map((map) =>
    [...map.values()].map((entry) => ({
      ...entry,
      value:
        entry.kind === 'aggregate'
          ? (entry.total || 0) / entry.n_scope
          : (100 * entry.n_hit) / entry.n_scope,
      // Provisional points carry no interval: it would narrow as treebanks arrive and
      // reading a moving confidence interval is worse than reading none.
      ci_low: null,
      ci_high: null,
    })),
  )
}

/**
 * The plot as a URL.
 *
 * A measure defined by two free-text Grew requests has no name, so there is nothing to
 * cite in a paper unless the definition itself travels. Everything the plot depends on
 * goes in the fragment -- both query pairs, the scheme, the sampling budget, the
 * threshold, the colouring -- so the link reproduces the figure rather than approximating
 * it. The fragment rather than the query string keeps the requests out of server logs.
 *
 * Base64 of the UTF-8 JSON: Grew requests contain `{`, `}`, `[`, `"` and newlines, and
 * every one of those survives a round trip through some URL handlers and not others.
 */
function encodeState() {
  const state = {
    v: 1,
    x: { s: x.scope, q: x.response, l: x.label, k: x.kind, e: x.expression, a: x.aggregation, u: x.unit },
    y: yCollapsed.value
      ? null
      : { s: y.scope, q: y.response, l: y.label, k: y.kind, e: y.expression, a: y.aggregation, u: y.unit },
    scheme: scheme.value,
    budget: budget.value,
    minScope: minScope.value,
    colourBy: colourBy.value,
    bars: showErrorBars.value,
    labels: labelMode.value,
    diag: showDiagonal.value,
    sq: squarePlot.value,
  }
  const bytes = new TextEncoder().encode(JSON.stringify(state))
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function applyState(encoded) {
  const padded = encoded.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4))
  const state = JSON.parse(
    new TextDecoder().decode(Uint8Array.from(binary, (ch) => ch.charCodeAt(0))),
  )
  if (state.v !== 1) throw new Error(`unknown link version ${state.v}`)

  scheme.value = state.scheme || 'SUD'
  const restore = (axis, saved) => {
    axis.scope = saved.s
    axis.response = saved.q
    axis.label = saved.l || ''
    axis.kind = saved.k || 'ratio'
    axis.expression = saved.e || ''
    axis.aggregation = saved.a || 'avg'
    axis.unit = saved.u || '%'
  }
  restore(x, state.x)
  yCollapsed.value = !state.y
  if (state.y) restore(y, state.y)
  budget.value = state.budget ?? 100000
  minScope.value = state.minScope ?? 30
  colourBy.value = state.colourBy || 'family'
  showErrorBars.value = !!state.bars
  // Older links stored a boolean; map it onto the modes.
  labelMode.value =
    typeof state.labels === 'string' ? state.labels : state.labels === false ? 'none' : 'optimal'
  showDiagonal.value = !!state.diag
  squarePlot.value = !!state.sq
}

async function copyLink() {
  const url = `${location.origin}${location.pathname}#plot=${encodeState()}`
  await navigator.clipboard.writeText(url)
  // Only the clipboard gets the fragment. Writing it into the address bar too left a
  // long #plot=... (or a stray #) on the URL for the rest of the session.
  $q.notify({ message: 'link copied', timeout: 1400, position: 'bottom-right' })
}

function exportTsv() {
  const header = ['language', 'family', xLabel.value, 'n_scope_x', 'n_hit_x']
  if (!yCollapsed.value) header.push(yLabel.value)
  const lines = [header.join('\t')]
  for (const point of points.value) {
    const row = [
      point.language, point.label, point.x.toFixed(4),
      point.n_scope, point.n_hit,
    ]
    if (!yCollapsed.value) row.push(point.y.toFixed(4))
    lines.push(row.join('\t'))
  }
  download(new Blob([lines.join('\n')], { type: 'text/tab-separated-values' }), 'grugrutyp.tsv')
}

function exportPng() {
  const data = plot.value?.toPng()
  if (!data) return
  const link = document.createElement('a')
  link.href = data
  link.download = 'grugrutyp.png'
  link.click()
}

function exportSvg() {
  const svg = plot.value?.toSvg()
  if (!svg) return
  download(new Blob([svg], { type: 'image/svg+xml' }), 'grugrutyp.svg')
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
  $q.notify({ message: `${filename} saved`, timeout: 1200, position: 'bottom-right' })
}

// A plot only means something inside one scheme -- `1=subj` and `nsubj` are different
// relations -- so switching scheme reloads the presets and clears the results rather than
// leaving SUD numbers on screen under a UD heading.
watch(scheme, async () => {
  const wasPresetX = presets.value.find((p) => p.scope === x.scope && p.response === x.response)
  const wasPresetY = presets.value.find((p) => p.scope === y.scope && p.response === y.response)
  await loadPresets()
  // Carry a preset over to its twin in the other scheme; a hand-written query is left
  // alone, because rewriting somebody's query is worse than letting it fail visibly.
  if (wasPresetX) {
    const twin = presets.value.find((p) => p.key === wasPresetX.key)
    if (twin) { x.scope = twin.scope; x.response = twin.response }
  }
  if (wasPresetY) {
    const twin = presets.value.find((p) => p.key === wasPresetY.key)
    if (twin) { y.scope = twin.scope; y.response = twin.response }
  }
  rawLanguages.value = [[], []]
  perTreebank.value = []
  progress.total = 0
})

watch(colourBy, loadStyles)

onMounted(async () => {
  await Promise.all([loadPresets(), loadStyles()])

  // After the presets, so a shared link overrides the defaults they installed rather than
  // racing them. A malformed fragment is reported and ignored -- silently falling back to
  // the default plot would be worse, because the user would read the wrong figure.
  const match = /[#&]plot=([^&]+)/.exec(location.hash)
  if (match) {
    try {
      applyState(match[1])
      // The fragment has served its purpose; leaving it makes every subsequent copy of
      // the address bar a stale deep link.
      history.replaceState(null, '', location.pathname + location.search)
    } catch (exception) {
      error.value = `this link could not be read (${exception.message})`
      return
    }
  }
  // With or without a link: open on a plot, not on an empty form. The default presets
  // are precomputed by scripts/warm_cache.py, so this serves from cache in about a
  // second rather than making the first visit pay a cold full pass.
  await nextTick()
  runPlot()
})
</script>

<style scoped>
.axes {
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
}
.plot-area {
  min-height: 460px;
}
</style>
