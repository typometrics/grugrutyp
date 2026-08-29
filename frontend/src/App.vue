<template>
  <q-layout view="hHh lpR fFf">
    <!-- Ivory, bordered, dark green on it: the header follows the logo's palette rather
         than fighting it with a blue bar. The logo IS the wordmark, so no text title. -->
    <q-header bordered class="site-header">
      <q-toolbar class="q-py-xs">
        <!-- Explicit dimensions: without them the tab bar measures itself before the
             image loads, decides it overflows, and leaves a stray scroll arrow ('>')
             floating over the Search tab. -->
        <img
          :src="$q.dark.isActive ? logoDarkUrl : logoUrl" alt="grugrutyp"
          width="69" height="42" class="site-logo q-mr-md"
        />
        <span class="site-subtitle gt-sm">Grew queries over UD &amp; SUD</span>
        <!-- active-color: the primary green vanishes on the dark header, so dark mode
             lightens it; the img icon cannot inherit text colour, so it swaps files. -->
        <q-tabs
          v-model="tab" dense no-caps shrink class="q-ml-md"
          :active-color="$q.dark.isActive ? 'green-3' : 'primary'" indicator-color="accent"
        >
          <q-tab name="plot" icon="scatter_plot" label="Typometrics" />
          <!-- Kim's hand-drawn dependency bouquet, recoloured to the site palette -->
          <q-tab
            name="search"
            :icon="`img:/grugrutyp/icons/simple-bouquet-${$q.dark.isActive ? 'light' : 'green'}.svg`"
            label="Search"
          />
        </q-tabs>
        <q-space />
        <q-btn
          v-if="audit && !audit.clean" flat dense no-caps icon="warning_amber"
          :label="`${audit.unconfigured.length} unconfigured`"
        >
          <q-tooltip class="audit-tooltip">
            These languages have no entry in the configuration and plot grey:
            {{ audit.unconfigured.join(', ') }}.
            Run scripts/config_audit.py.
          </q-tooltip>
        </q-btn>
        <q-btn
          flat dense round :icon="$q.dark.isActive ? 'light_mode' : 'dark_mode'"
          @click="toggleDark"
        >
          <q-tooltip>{{ $q.dark.isActive ? 'light mode' : 'dark mode' }}</q-tooltip>
        </q-btn>
        <q-btn flat dense no-caps icon="info_outline" label="about" @click="aboutOpen = true" />
      </q-toolbar>
    </q-header>

    <q-dialog v-model="aboutOpen">
      <q-card style="min-width: 520px; max-width: 720px">
        <q-tabs
          v-model="aboutTab" dense no-caps align="left"
          active-color="primary" indicator-color="accent"
        >
          <q-tab name="what" label="What is this" />
          <q-tab name="tech" label="Technical details" />
          <q-tab name="corpus" label="Corpus &amp; links" />
        </q-tabs>
        <q-separator />
        <q-tab-panels v-model="aboutTab" animated>
          <q-tab-panel name="what" class="about-text">
            <p>
              <b>grugrutyp</b> measures word order and other syntactic properties across
              the treebanks of Universal Dependencies, in both the UD and SUD annotation
              schemes.
            </p>
            <p>
              A measure is a pair of Grew requests. The <b>scope (S)</b> says what to
              count — all subject relations, say. The <b>response (Q)</b> says which of
              those also do something — the dependent follows its governor. Each language
              is plotted at <b>100 × #(S ∧ Q) / #(S)</b>.
            </p>
            <p class="text-weight-medium q-mb-xs">Hints</p>
            <ul class="q-mt-none">
              <li>Presets are starting points — load one, then edit the relation, the
                POS, the direction. The picker names the preset until you edit.</li>
              <li>Collapse the Y axis for a one-dimensional strip by language family.</li>
              <li>Click a dot: its treebanks, and buttons to open <b>S</b> (everything
                counted) or <b>S ∧ Q</b> (the numerator) in the search tab.</li>
              <li>The search tab can search one treebank, several, or a whole language,
                and can <i>cluster</i> the matchings by a key like <code>X.upos</code>
                instead of listing trees.</li>
              <li><b>share</b> gives a link that reproduces the plot exactly, and SVG/PNG/TSV
                exports. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs a search.</li>
            </ul>
          </q-tab-panel>
          <q-tab-panel name="tech" class="about-text">
            <p>
              <b>Error bars</b> are 95% Wilson score intervals on the language's
              proportion. Wilson rather than the normal approximation because typology
              lives at the edges — 0 of 5&thinsp;000, 3 of 50&thinsp;000 — where the
              normal interval runs off the scale or collapses to a point. A language
              plotted from 40 matchings shows a visibly wider bar than one from 400&thinsp;000.
            </p>
            <p>
              <b>One language, one number.</b> A language's treebanks are merged by
              summing their counts, never by averaging their percentages — a 27k-token
              treebank must not weigh as much as a 400k one. While a run is streaming,
              a language whose treebanks have not all arrived is drawn small.
            </p>
            <p>
              <b>Sampling.</b> By default each language is measured on up to ~100k tokens,
              drawn as a deterministic random sample of sentences across all its treebanks
              in proportion to their size. If the sample turns out too thin for a reliable
              number — scope too small, interval too wide, or fewer than 10 hits — that
              language is automatically re-measured on a tenfold sample ("refined on a
              larger sample" in the progress line). <i>Exact (no sampling)</i> in the
              options computes on the full corpus, for paper-ready numbers.
            </p>
            <p>
              <b>Caching.</b> Every (treebank, query) result is cached, and the preset
              measures are precomputed — preset plots appear in seconds. A novel query's
              first run has to scan the corpus and can take minutes; every later run of
              it is instant.
            </p>
            <p>
              <b>Min. scope matchings</b> hides languages whose denominator is below the
              threshold — the count of hidden languages is shown next to the progress
              line. It filters the display only; nothing is recomputed when it moves.
            </p>
          </q-tab-panel>
          <q-tab-panel name="corpus" class="about-text">
            <p>
              <b>Universal Dependencies {{ corpusVersion }}</b>, imported in both schemes:
              {{ treebanks.length.toLocaleString() }} treebanks,
              {{ languageCount }} languages,
              {{ (tokenCount / 1e6).toFixed(1) }}M syntactic words.
            </p>
            <ul class="q-mt-none">
              <li><a href="https://grew.fr/doc/request/" target="_blank" rel="noopener">
                Grew request syntax</a> — the query language used here</li>
              <li><a href="https://universal.grew.fr" target="_blank" rel="noopener">
                universal.grew.fr</a> — Grew match on single treebanks, by the Grew team</li>
              <li><a href="https://universaldependencies.org" target="_blank" rel="noopener">
                universaldependencies.org</a> — the UD project and its annotation guidelines</li>
              <li><a href="https://surfacesyntacticud.github.io/" target="_blank" rel="noopener">
                surfacesyntacticud.github.io</a> — the SUD annotation scheme</li>
              <li><a href="https://typometrics.elizia.net" target="_blank" rel="noopener">
                typometrics.elizia.net</a> — the current typometrics site this tool succeeds</li>
            </ul>
          </q-tab-panel>
        </q-tab-panels>
      </q-card>
    </q-dialog>

    <q-page-container>
      <!-- Exactly the viewport minus the header -- q-page's default is min-height, which
           lets the content run a few pixels past 100% and opens a permanent scrollbar.
           Anything taller than the page (a long 1-D strip, a list of trees) scrolls
           inside its own view instead. -->
      <q-page :style-fn="(offset) => ({ height: `calc(100vh - ${offset}px)` })">
        <q-banner v-if="loadError" dense class="bg-red-1 text-red-9">
          <template #avatar><q-icon name="error_outline" /></template>
          {{ loadError }}
        </q-banner>

        <!-- Both views stay mounted: a plot takes a minute to compute and switching to a
             tree and back must not throw it away. -->
        <div v-show="tab === 'plot'" class="full-height">
          <PlotView :treebanks="treebanks" @open-search="openSearch" />
        </div>
        <div v-show="tab === 'search'" class="full-height view-scroll">
          <SearchView
            ref="search" :treebanks="treebanks"
            :scheme="scheme" @update:scheme="(v) => (scheme = v)"
          />
        </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api } from './api'
import logoUrl from './assets/grugrutyp.svg'
import logoDarkUrl from './assets/grugrutyp-dark.svg'
import PlotView from './views/PlotView.vue'
import SearchView from './views/SearchView.vue'

const $q = useQuasar()

function toggleDark() {
  $q.dark.toggle()
  localStorage.setItem('grugrutyp-dark', $q.dark.isActive ? '1' : '0')
}

const tab = ref('plot')

// Each tab has its own address, so /grugrutyp/#/search can be bookmarked and sent.
// Shared-plot links (#plot=...) are a different kind of fragment and are handled --
// and then cleared -- by PlotView.
const TAB_HASHES = { plot: '#/typometrics', search: '#/search' }
function applyHashTab() {
  const found = Object.entries(TAB_HASHES).find(([, hash]) => location.hash === hash)
  if (found) tab.value = found[0]
}
watch(tab, (value) => {
  if (location.hash !== TAB_HASHES[value]) {
    history.replaceState(null, '', location.pathname + location.search + TAB_HASHES[value])
  }
})

const aboutOpen = ref(false)
const aboutTab = ref('what')
const corpusVersion = ref('')
const languageCount = computed(() => new Set(treebanks.value.map((tb) => tb.language)).size)
const tokenCount = computed(() => treebanks.value.reduce((sum, tb) => sum + tb.n_tokens, 0))
const scheme = ref('SUD')
const treebanks = ref([])
const loadError = ref('')
const audit = ref(null)
const search = ref(null)

async function openSearch(payload) {
  scheme.value = payload.scheme
  tab.value = 'search'
  await nextTick()
  search.value?.openQuery(payload)
}

onMounted(async () => {
  $q.dark.set(localStorage.getItem('grugrutyp-dark') === '1')
  applyHashTab()
  window.addEventListener('hashchange', applyHashTab)
  try {
    const response = await api.treebanks()
    treebanks.value = response.treebanks
    corpusVersion.value = response.version || ''
  } catch (error) {
    loadError.value = `could not load treebanks: ${error.message}`
  }
  // Advisory only: an unconfigured language plots grey rather than failing, so the drift
  // has to be surfaced rather than waited for. See docs/language-config.md.
  try {
    audit.value = await api.configAudit()
  } catch {
    audit.value = null
  }
})
</script>

<style>
.site-header {
  background: #faf8f2;
  color: #143d14;
  border-bottom: 1px solid #e3ded2;
}
.body--dark .site-header {
  background: #1b201a;
  color: #c9d6c4;
  border-bottom: 1px solid #2e352c;
}
.body--dark .site-subtitle {
  color: #8fa189;
}
.site-logo {
  height: 42px;
  display: block;
}
/* Two fixed tabs never legitimately overflow; the arrows only ever appear as the
   layout-shift artifact described above. */
.site-header .q-tabs__arrow {
  display: none;
}
.site-subtitle {
  font-style: italic;
  font-size: 13px;
  color: #5c6b5c;
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
.body--dark .cypher {
  background: #26292b;
}
/* Browser-default link colours (navy, visited purple) disappear on a dark background. */
.body--dark a:link,
.body--dark a:visited {
  color: #8ab4f8;
}
.opacity-70 {
  opacity: 0.7;
}
.audit-tooltip {
  max-width: 460px;
  font-size: 12px;
}
.about-text {
  font-size: 14px;
  line-height: 1.55;
}
.view-scroll {
  overflow-y: auto;
}
.about-text p {
  margin-bottom: 10px;
}
</style>
