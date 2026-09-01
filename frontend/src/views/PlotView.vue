<template>
  <div class="column full-height">
    <!-- ================================== axis panels, across the top (Kim's layout) -->
    <div class="axes q-px-sm q-pt-sm q-pb-xs">
      <div class="row q-col-gutter-sm items-stretch">
        <div :class="yCollapsed ? 'col' : 'col-12 col-md-6'">
          <AxisPanel
            axis="x" :presets="presets" :treebank="previewTreebank" :label="x.label"
            v-model:scope="x.scope" v-model:response="x.response"
            v-model:kind="x.kind" v-model:expression="x.expression"
            v-model:aggregation="x.aggregation" v-model:unit="x.unit"
            @label="(v) => (x.label = v)"
          />
        </div>
        <div v-if="!yCollapsed" class="col-12 col-md-6">
          <AxisPanel
            axis="y" :presets="presets" :treebank="previewTreebank" collapsible :label="y.label"
            v-model:scope="y.scope" v-model:response="y.response"
            v-model:kind="y.kind" v-model:expression="y.expression"
            v-model:aggregation="y.aggregation" v-model:unit="y.unit"
            v-model:collapsed="yCollapsed" @label="(v) => (y.label = v)"
          />
        </div>
        <!-- Collapsed, the Y axis costs no vertical space: it folds into a slim handle
             at the right edge, where the panel sat, and "<" unfolds it. -->
        <div v-else class="col-auto">
          <div
            class="y-handle column items-center justify-center"
            role="button" tabindex="0"
            @click="yCollapsed = false" @keyup.enter="yCollapsed = false"
          >
            <q-icon name="chevron_left" size="20px" />
            <div class="y-handle-label">Y axis</div>
            <q-tooltip anchor="center left" self="center right">
              Add a Y axis — plot two measures against each other
            </q-tooltip>
          </div>
        </div>
      </div>

      <div class="row items-center q-gutter-sm q-mt-sm">
        <q-btn-toggle
          v-model="scheme" no-caps unelevated dense toggle-color="primary"
          :options="[{ label: 'SUD', value: 'SUD' }, { label: 'UD', value: 'UD' }]"
        />
        <q-btn
          :color="plotStale ? 'accent' : 'primary'" no-caps icon="scatter_plot"
          :label="running ? 'Computing…' : 'Plot'" :loading="running" @click="runPlot"
        >
          <q-tooltip v-if="plotStale">
            The settings changed since this plot was computed — press to recompute
          </q-tooltip>
        </q-btn>
        <q-btn v-if="running" flat dense no-caps icon="stop" label="Stop" @click="stopPlot" />
        <!-- Everything a first-time user does not need lives behind this. The defaults
             are the ones worth defaulting; the interface should not make every visitor
             read six controls to plot one preset. -->
        <q-btn
          flat dense no-caps icon="tune"
          :label="optionsOpen ? 'hide options' : 'options'"
          @click="optionsOpen = !optionsOpen"
        />
        <!-- Type to ring matching languages on the plot; Enter opens the first match's
             data (the same dialog a click on its dot opens). -->
        <q-input
          v-if="points.length" v-model="findLanguage" dense outlined clearable
          debounce="80" placeholder="find language" style="width: 160px"
          @keyup.enter="openFoundLanguage"
        >
          <template #prepend><q-icon name="travel_explore" size="16px" /></template>
          <template v-if="findLanguage && !foundCount" #append>
            <q-icon name="warning_amber" color="orange-8" size="16px">
              <q-tooltip>no plotted language matches</q-tooltip>
            </q-icon>
          </template>
        </q-input>
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
            <template v-if="user">
              <q-separator />
              <q-item clickable @click="saveOpen = true">
                <q-item-section avatar><q-icon name="bookmark_add" size="18px" /></q-item-section>
                <q-item-section>
                  Save query
                  <q-item-label caption>to your account, findable on any machine</q-item-label>
                </q-item-section>
              </q-item>
              <q-item clickable @click="openSavedQueries">
                <q-item-section avatar><q-icon name="bookmarks" size="18px" /></q-item-section>
                <q-item-section>My queries</q-item-section>
              </q-item>
            </template>
          </q-list>
        </q-btn-dropdown>
      </div>

      <q-slide-transition>
        <div v-show="optionsOpen" class="row items-center q-gutter-sm q-mt-sm">
          <q-select
            v-model="colourBy" :options="viewOptions" label="Colour by" dense options-dense
            outlined emit-value map-options style="min-width: 150px"
          />
          <q-btn flat dense no-caps icon="palette" label="customise" @click="customizeOpen = true">
            <q-badge v-if="overriddenCount" color="accent" floating>{{ overriddenCount }}</q-badge>
            <q-tooltip>
              Your own colours, markers and group names for this browser — the site
              configuration is untouched
            </q-tooltip>
          </q-btn>
          <q-select
            v-model="budget" :options="budgetOptions" label="Corpus coverage" dense options-dense
            outlined emit-value map-options style="min-width: 210px"
          />
          <q-select
            v-model="labelMode" label="Language names" dense options-dense
            outlined emit-value map-options style="min-width: 160px"
            :options="[
              { label: 'readable', value: 'optimal' },
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
          <q-toggle v-model="fitAxes" dense label="Fit axes">
            <q-tooltip>
              Zoom a percentage axis to the distribution instead of the full 0–100 —
              a measure that tops out at 30% gets an axis to 30
            </q-tooltip>
          </q-toggle>
          <q-toggle v-model="splitBands" dense label="Rows by group" :disable="!yCollapsed">
            <q-tooltip>
              1-D only: one row per colour group, or everything on a single line
            </q-tooltip>
          </q-toggle>
          <q-toggle v-model="showDensity" dense label="Density" :disable="!yCollapsed">
            <q-tooltip>1-D only: a kernel density curve over the strip</q-tooltip>
          </q-toggle>
        </div>
      </q-slide-transition>

      <div v-if="progress.total" class="q-mt-xs">
        <q-linear-progress
          :value="arrivedLanguages / (totalLanguages || 1)" size="4px"
          :color="running ? 'primary' : 'green'"
        />
        <!-- Counted in languages, not treebanks: since the language became the unit of
             sampling and merging, treebank counts were plumbing the user never asked
             about. -->
        <div class="text-caption text-grey-7 progress-caption">
          {{ arrivedLanguages }} / {{ totalLanguages }} languages ·
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
          <!-- The giants whose escalation was deferred: one unobtrusive button, the
               explanation in its tooltip (docs/sampling.md section 5). While refining it
               shows progress and a click stops it. -->
          <q-btn
            v-if="(refineTargets.length || refining) && !running && !plotStale"
            dense flat no-caps size="sm" color="accent" class="refine-btn"
            :icon="refining ? 'stop' : 'zoom_in'"
            :label="refining
              ? `refining ${refineProgress.done}/${refineProgress.total}…`
              : `refine ${refineTargets.length} language${refineTargets.length === 1 ? '' : 's'}`"
            @click="refining ? stopRefine() : refinePlot()"
          >
            <q-tooltip class="refine-tooltip" :delay="150" anchor="bottom middle" self="top middle">
              <div v-if="refining">
                <div class="tip-title">Refining on a tenfold sample…</div>
                <p>
                  {{ refineProgress.done }} of {{ refineProgress.total }} treebanks done.
                  Clicking the button stops it; a stopped refinement keeps the current
                  sampled values.
                </p>
              </div>
              <div v-else>
                <div class="tip-title">
                  {{ refineDetails.length === 1 ? 'One point is' : 'These points are' }}
                  computed on a thin sample
                </div>
                <div class="tip-langs">
                  <span v-for="entry in refineDetails" :key="entry.name" class="tip-lang">
                    {{ entry.name }}&nbsp;<span class="tip-size">{{ entry.size }}</span>
                  </span>
                </div>
                <div class="tip-heading">Why</div>
                <p>
                  Every language is measured on a bounded sample. When that proves too
                  thin — this measure left too few matchings, or too wide an interval —
                  the sample normally grows tenfold by itself. But these languages are
                  millions of words: that pass takes minutes, so it waits for you instead
                  of slowing every plot.
                </p>
                <div class="tip-heading">Worth clicking when</div>
                <p>
                  Their exact values matter to you — close comparison, an export, a number
                  for a paper. Only these languages are recomputed; a cold run can take a
                  few minutes and the result is cached. For a quick look, ignore it: the
                  points are plotted, just less certain.
                </p>
                <div class="tip-heading">Error bars</div>
                <p>
                  Related, but not the same. The bar is the point's 95% interval, and one
                  trigger for this button is a bar wider than 2 points — refining shrinks
                  those about threefold. The other triggers don't show in the bar: a
                  phenomenon with only a handful of hits draws a deceptively narrow
                  interval while its relative error is huge, and only a bigger sample
                  separates "rare" from "never".
                </p>
              </div>
            </q-tooltip>
          </q-btn>
        </div>
      </div>

      <q-banner v-if="error" dense class="bg-red-1 text-red-9 q-mt-sm">
        <template #avatar><q-icon name="error_outline" /></template>
        {{ error }}
      </q-banner>
    </div>

    <!-- ============================================ the plot, full width underneath -->
    <div class="col plot-area q-px-sm q-pb-sm relative-position">
      <!-- A stale plot is shown, not shown off: grayed under a banner until the user
           decides the recompute is worth it. Better than the old behaviour (clear and
           silently recompute on every scheme flip), which threw away a figure the user
           may have wanted and started a run nobody asked for. -->
      <div v-if="plotStale && points.length && !running" class="stale-banner">
        The settings changed — this plot shows the previous ones. Press
        <b>Plot</b> to recompute.
      </div>
      <ScatterPlot
        v-if="points.length" ref="plot" :points="points"
        :class="{ 'plot-stale': plotStale && !running }"
        :x-label="xLabel" :y-label="yLabel" :one-dimensional="yCollapsed"
        :x-percent="x.kind !== 'aggregate'" :y-percent="y.kind !== 'aggregate'"
        :label-mode="labelMode" :show-error-bars="showErrorBars" :show-diagonal="showDiagonal"
        :square="squarePlot" :highlight="findLanguage || ''"
        :bands="splitBands" :show-density="showDensity" :fit-axes="fitAxes"
        @pick="inspect"
      />
      <q-card
        v-else flat bordered class="full-height column flex-center"
        :class="$q.dark.isActive ? 'bg-grey-10' : 'bg-grey-1'"
      >
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

    <!-- saved queries: a name over the share-link payload, stored on the account -->
    <q-dialog v-model="saveOpen">
      <q-card style="min-width: 380px">
        <q-card-section>
          <div class="text-h6">Save this query</div>
          <div class="text-caption text-grey-7">
            Everything the plot depends on is saved — both axes, scheme, coverage,
            colours — exactly what a share link carries.
          </div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-input
            v-model="saveName" dense outlined autofocus label="name"
            @keyup.enter="doSaveQuery"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="save" :loading="saving"
            :disable="!saveName.trim()" @click="doSaveQuery"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="queriesOpen">
      <q-card style="min-width: 440px; max-width: 640px">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">My queries</div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-card-section>
          <q-list dense bordered separator class="rounded-borders">
            <q-item v-for="entry in savedList" :key="entry.id">
              <q-item-section clickable class="cursor-pointer" @click="applySaved(entry)">
                <q-item-label>{{ entry.name }}</q-item-label>
                <q-item-label caption>{{ entry.created_at.slice(0, 10) }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <div class="row no-wrap q-gutter-xs">
                  <q-btn dense flat size="sm" icon="play_arrow" @click="applySaved(entry)">
                    <q-tooltip>load and compute</q-tooltip>
                  </q-btn>
                  <q-btn dense flat size="sm" icon="delete_outline" @click="deleteSaved(entry)" />
                </div>
              </q-item-section>
            </q-item>
          </q-list>
          <div v-if="!savedList.length" class="text-caption text-grey-7">
            nothing saved yet — run a plot, then <b>share → Save query</b>
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- browser-local colours/markers/groups over the site configuration (Phase 6.1) -->
    <AppearanceCustomize
      v-model="customizeOpen" :view="colourBy" :server-languages="serverLanguages"
      :overrides="overrides" @update:overrides="applyOverrides"
    />

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
            <!-- The whole language first: it resolves to a lang:<Language> selection in
                 the search tab, which searches all its treebanks as one corpus. -->
            <q-item class="text-weight-medium">
              <q-item-section>
                {{ detail.language.replace(/_/g, ' ') }} — whole language
                ({{ languageTreebanks(detail.language).length }}
                treebank{{ languageTreebanks(detail.language).length === 1 ? '' : 's' }})
              </q-item-section>
              <q-item-section side>
                <div class="row q-gutter-xs no-wrap">
                  <q-btn
                    dense unelevated size="sm" no-caps text-color="white"
                    :color="$q.dark.isActive ? 'green-8' : 'primary'"
                    label="S" class="q-px-sm"
                    @click="openInSearch(`lang:${detail.language}`, false)"
                  >
                    <q-tooltip>the scope, across every treebank of the language</q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="x.response.trim()" dense unelevated size="sm" no-caps
                    color="accent" text-color="white" label="S ∧ Q" class="q-px-sm"
                    @click="openInSearch(`lang:${detail.language}`, true)"
                  >
                    <q-tooltip>scope and response, across every treebank</q-tooltip>
                  </q-btn>
                </div>
              </q-item-section>
            </q-item>
            <q-separator />
            <q-item v-for="name in languageTreebanks(detail.language)" :key="name">
              <q-item-section>{{ name }}</q-item-section>
              <q-item-section side>
                <!-- unelevated, not outline: a dark-green outline on a dark dialog was
                     unreadable. Filled chips with white text read in both themes. -->
                <div class="row q-gutter-xs no-wrap">
                  <q-btn
                    dense unelevated size="sm" no-caps text-color="white"
                    :color="$q.dark.isActive ? 'green-8' : 'primary'"
                    label="S" class="q-px-sm"
                    @click="openInSearch(name, false)"
                  >
                    <q-tooltip>the scope — everything that was counted</q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="x.response.trim()" dense unelevated size="sm" no-caps
                    color="accent" text-color="white" label="S ∧ Q" class="q-px-sm"
                    @click="openInSearch(name, true)"
                  >
                    <q-tooltip>scope and response together — the numerator</q-tooltip>
                  </q-btn>
                </div>
              </q-item-section>
            </q-item>
          </q-list>
          <div class="text-caption text-grey-6 q-mt-sm">
            Opens the query in the search tab, where the matching sentences are drawn as
            trees — <b>S</b> shows everything the scope counted, <b>S ∧ Q</b> only the
            matchings that also satisfy the response.
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api, myQueries } from '../api'
import { user } from '../user'
import AppearanceCustomize from '../components/AppearanceCustomize.vue'
import AxisPanel from '../components/AxisPanel.vue'
import ScatterPlot from '../components/ScatterPlot.vue'

const props = defineProps({ treebanks: { type: Array, default: () => [] } })
const emit = defineEmits(['open-search'])

const $q = useQuasar()

const scheme = ref('SUD')
const presets = ref([])
const colourBy = ref('family')
const viewOptions = ref([{ label: 'family', value: 'family' }])

// ------------------------------------------------- personal appearance (Phase 6.1)
//
// The site configuration comes from the server; a visitor's own colours live in this
// browser only, as a diff over it, keyed by view. Share links and other visitors keep
// the site configuration -- a link that looked different for its recipient would be a
// figure nobody can cite.
const OVERRIDES_KEY = 'grugrutyp-appearance-overrides'
function readOverrides() {
  try {
    return JSON.parse(localStorage.getItem(OVERRIDES_KEY) || '{}')
  } catch {
    return {}
  }
}
const overrides = ref(readOverrides())
const customizeOpen = ref(false)
const serverLanguages = ref([])

function applyOverrides(next) {
  overrides.value = next
  localStorage.setItem(OVERRIDES_KEY, JSON.stringify(next))
}

const overriddenCount = computed(
  () => Object.keys(overrides.value[colourBy.value] || {}).length,
)

const languageStyles = computed(() => {
  const viewOverrides = overrides.value[colourBy.value] || {}
  const styles = {}
  for (const item of serverLanguages.value) {
    styles[item.language] = { ...item, ...(viewOverrides[item.language] || {}) }
  }
  return styles
})

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
const fitAxes = ref(false)
const splitBands = ref(true)
const showDensity = ref(false)
const optionsOpen = ref(false)

// What the current points were computed FROM. Only inputs that change the numbers
// belong here -- minScope, colours and labels restyle the same data and must not mark
// the plot stale.
const ranSignature = ref('')
function computeSignature() {
  const axisPart = (axis) => [axis.scope, axis.response, axis.kind, axis.expression, axis.aggregation]
  return JSON.stringify([
    scheme.value, budget.value, axisPart(x), yCollapsed.value ? null : axisPart(y),
  ])
}
const plotStale = computed(
  () => progress.total > 0 && ranSignature.value !== computeSignature(),
)

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
// Everything below counts LANGUAGES: since the language became the unit of sampling and
// merging, per-treebank numbers were internals leaking into the progress line.
const totalLanguages = computed(
  () =>
    new Set(
      props.treebanks.filter((tb) => tb.scheme === scheme.value).map((tb) => tb.language),
    ).size,
)
const arrivedLanguages = computed(
  () => new Set(perTreebank.value.map((r) => r.language)).size,
)
const cachedCount = computed(() => {
  const uncached = new Set(
    perTreebank.value.filter((r) => !r.axes[0].cached).map((r) => r.language),
  )
  return arrivedLanguages.value - uncached.size
})
const escalatedCount = computed(
  () =>
    new Set(
      perTreebank.value.filter((r) => r.axes[0].escalated).map((r) => r.language),
    ).size,
)

// The languages whose escalation was deferred (their points carry `refinable` from the
// language-level merge): the proposal banner names them, and the refine run re-queries
// exactly their treebanks. Only the `done` event carries the flag, so the banner appears
// once the plot is complete rather than flickering while it fills in.
const refineTargets = computed(() => {
  const flagged = new Set()
  for (const axis of rawLanguages.value) {
    for (const entry of axis) if (entry.refinable) flagged.add(entry.language)
  }
  return [...flagged].sort()
})
/** The tooltip's language tags: name + corpus size, biggest first — the size is the
 *  reason the language is in this list at all, so it belongs next to the name. */
const refineDetails = computed(() => {
  const targets = new Set(refineTargets.value)
  const totals = new Map()
  for (const tb of props.treebanks) {
    if (tb.scheme !== scheme.value || !targets.has(tb.language)) continue
    totals.set(tb.language, (totals.get(tb.language) || 0) + tb.n_tokens)
  }
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([language, tokens]) => ({
      name: language.replace(/_/g, ' '),
      size: `${(tokens / 1e6).toFixed(1)}M words`,
    }))
})

/** The largest languages not yet complete -- what the run is actually waiting on. */
const pendingGiants = computed(() => {
  if (!progress.total) return []
  const arrived = new Set(perTreebank.value.map((r) => r.treebank))
  const remaining = new Map()
  for (const tb of props.treebanks) {
    if (tb.scheme !== scheme.value || arrived.has(tb.name)) continue
    remaining.set(tb.language, (remaining.get(tb.language) || 0) + tb.n_tokens)
  }
  return [...remaining.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([language, tokens]) => `${language.replace(/_/g, ' ')} (${(tokens / 1e6).toFixed(1)}M)`)
})

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
  // GUM, not the first English alphabetically (Atis, a flight-query corpus whose 97%
  // subject rates say little about English at large).
  const english =
    candidates.find((tb) => tb.name.endsWith('English-GUM')) ||
    candidates.find((tb) => tb.language === 'English')
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

const findLanguage = ref('')
const foundCount = computed(() => {
  const query = (findLanguage.value || '').trim().toLowerCase()
  if (!query) return 0
  return points.value.filter((p) => p.language.toLowerCase().includes(query)).length
})

function openFoundLanguage() {
  const query = (findLanguage.value || '').trim().toLowerCase()
  if (!query) return
  const match = points.value.find((p) => p.language.toLowerCase().includes(query))
  if (match) inspect(match)
}

function openInSearch(treebank, withResponse) {
  detailOpen.value = false
  // Either the scope alone (the denominator) or scope plus response (the numerator) --
  // a response's with/without blocks simply append to the scope's request text.
  const request = withResponse ? `${x.scope.trim()}\n${x.response.trim()}` : x.scope
  emit('open-search', { treebank, request, scheme: scheme.value })
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
  serverLanguages.value = response.languages
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
  stopRefine()
  running.value = false
  clearInterval(timer)
}

async function runPlot() {
  stopPlot()
  error.value = ''
  ranSignature.value = computeSignature()
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

// ------------------------------------------------------------------- deferred refining
//
// The fast pass leaves the giants sampled at their budget even when the policy wanted
// more -- rescanning Czech, German and Russian unasked was minutes of every cold run.
// This is the "more complete computation, proposed": the same measure, only the flagged
// languages' treebanks, at ten times the coverage. Results replace those languages'
// points in place; everything else on the plot is untouched.
const refining = ref(false)
const refineProgress = reactive({ done: 0, total: 0 })
let refineHandle = null

function stopRefine() {
  if (refineHandle) refineHandle.abort()
}

async function refinePlot() {
  const targets = new Set(refineTargets.value)
  const names = props.treebanks
    .filter((tb) => tb.scheme === scheme.value && targets.has(tb.language))
    .map((tb) => tb.name)
  if (!names.length || refining.value) return
  refining.value = true
  refineProgress.done = 0
  refineProgress.total = names.length

  refineHandle = api.measure(
    {
      x: axisBody(x),
      y: yCollapsed.value ? null : axisBody(y),
      scheme: scheme.value,
      treebanks: names,
      // Ten times the plot's budget: exactly the escalation the policy deferred. A
      // language this leaves under 100% is at the escalation ceiling; past that only
      // "exact (no sampling)" in the coverage control goes further.
      token_budget: Math.max((budget.value || 0) * 10, 1_000_000),
      min_scope: minScope.value,
    },
    (name, data) => {
      if (name === 'point') {
        refineProgress.done = data.done
        const index = perTreebank.value.findIndex((row) => row.treebank === data.treebank)
        if (index >= 0) perTreebank.value.splice(index, 1, data)
      } else if (name === 'done') {
        // Merge, do not replace: the refine run's `done` only knows the languages it
        // re-ran, and the rest of the plot must keep its language-level intervals.
        rawLanguages.value = rawLanguages.value.map((axis, i) => {
          const refined = new Map((data.languages[i] || []).map((entry) => [entry.language, entry]))
          return axis.map((entry) => refined.get(entry.language) || entry)
        })
        if (data.errors.length) {
          error.value = `${data.errors.length} treebank(s) failed: ${data.errors
            .slice(0, 3)
            .map((e) => e.treebank)
            .join(', ')}${data.errors.length > 3 ? '…' : ''}`
        }
      } else if (name === 'error') {
        error.value = data.message
      }
    },
  )
  try {
    await refineHandle.done
  } catch (exception) {
    if (exception.name !== 'AbortError') error.value = exception.message
  } finally {
    refining.value = false
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
    fit: fitAxes.value,
    bands: splitBands.value,
    dens: showDensity.value,
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
  fitAxes.value = !!state.fit
  splitBands.value = state.bands !== false
  showDensity.value = !!state.dens
}

// ------------------------------------------------------------------- saved queries
//
// A saved query IS a share-link payload with a name on it -- one serialisation, two
// transports. Loading one goes through the same applyState the link uses.
const saveOpen = ref(false)
const saveName = ref('')
const saving = ref(false)
const queriesOpen = ref(false)
const savedList = ref([])

async function doSaveQuery() {
  if (!saveName.value.trim()) return
  saving.value = true
  try {
    await myQueries.save(saveName.value.trim(), encodeState())
    saveOpen.value = false
    saveName.value = ''
    $q.notify({ message: 'query saved', timeout: 1400, position: 'bottom-right' })
  } catch (exception) {
    error.value = exception.message
  } finally {
    saving.value = false
  }
}

async function openSavedQueries() {
  try {
    savedList.value = (await myQueries.list()).queries
    queriesOpen.value = true
  } catch (exception) {
    error.value = exception.message
  }
}

function applySaved(entry) {
  queriesOpen.value = false
  try {
    applyState(entry.payload)
  } catch (exception) {
    error.value = `this saved query could not be read (${exception.message})`
    return
  }
  runPlot()
}

async function deleteSaved(entry) {
  await myQueries.remove(entry.id)
  savedList.value = savedList.value.filter((q) => q.id !== entry.id)
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
  // The old plot deliberately stays on screen: it is grayed out as stale (see
  // `plotStale`) rather than thrown away, and nothing recomputes until Plot is pressed.
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
.body--dark .axes {
  background: #1d1d1d;
  border-bottom-color: rgba(255, 255, 255, 0.12);
}
.y-handle {
  height: 100%;
  min-height: 120px;
  width: 34px;
  border: 1px solid rgba(0, 0, 0, 0.24);
  border-radius: 4px;
  cursor: pointer;
  color: #5c6b5c;
  user-select: none;
}
.y-handle:hover {
  background: rgba(20, 61, 20, 0.06);
  color: #143d14;
}
.y-handle-label {
  writing-mode: vertical-rl;
  font-size: 12px;
  letter-spacing: 0.06em;
  margin-top: 6px;
}
.body--dark .y-handle {
  border-color: rgba(255, 255, 255, 0.24);
  color: #9aa89a;
}
.body--dark .y-handle:hover {
  background: rgba(200, 220, 200, 0.08);
  color: #c9d6c4;
}
.plot-area {
  min-height: 0;
  /* A 25-band strip plot is taller than the page; it scrolls here, not on the body. */
  overflow-y: auto;
}
/* One tight line under the bar: the caption's default leading plus the section's
   padding read as a blank band between the numbers and the plot. */
.progress-caption {
  margin-top: 2px;
  line-height: 1.25;
}
.plot-stale {
  filter: grayscale(0.85) opacity(0.4);
  transition: filter 0.2s;
}
/* Sits inside the caption line; the caption is 12px grey, the button matches its scale. */
.refine-btn {
  margin-left: 6px;
  vertical-align: baseline;
}
.stale-banner {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  background: #fff8ec;
  border: 1px solid #e0c9a0;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 13px;
  color: #6b4e16;
}
.body--dark .stale-banner {
  background: #3a3320;
  border-color: #5c4d26;
  color: #e3c987;
}
</style>

<!-- Unscoped on purpose: q-tooltip teleports its element to <body>, outside the scope
     attribute, so scoped rules never reach it. Everything is namespaced under the
     tooltip's own class to keep it from leaking. -->
<style>
.refine-tooltip {
  max-width: 460px;
  padding: 10px 14px;
  font-size: 12.5px;
  line-height: 1.5;
}
.refine-tooltip .tip-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 7px;
}
.refine-tooltip .tip-langs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 5px;
  margin-bottom: 8px;
}
.refine-tooltip .tip-lang {
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 10px;
  padding: 0 8px;
  white-space: nowrap;
}
.refine-tooltip .tip-size {
  opacity: 0.65;
  font-size: 11px;
}
.refine-tooltip .tip-heading {
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-size: 10px;
  opacity: 0.7;
  margin: 8px 0 2px;
}
.refine-tooltip p {
  margin: 0;
}
</style>
