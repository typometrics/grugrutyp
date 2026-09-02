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
          <!-- Not advertised to visitors: the tab exists once #/admin has been opened in
               this browser, or a token is already stored. The token itself gates the API. -->
          <q-tab v-if="adminVisible" name="admin" icon="settings" label="Admin" />
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
        <!-- Sign-in: only when at least one OAuth provider is configured server-side,
             so the button never promises what .env cannot deliver. -->
        <q-btn-dropdown
          v-if="!user && authProviders.length" flat dense no-caps
          icon="login" label="sign in" auto-close
        >
          <q-list dense>
            <q-item
              v-for="provider in authProviders" :key="provider"
              clickable tag="a" :href="auth.loginUrl(provider)"
            >
              <q-item-section avatar>
                <q-icon :name="PROVIDER_ICONS[provider] || 'login'" size="18px" />
              </q-item-section>
              <q-item-section>{{ PROVIDER_LABELS[provider] || provider }}</q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>
        <q-btn v-else-if="user" flat dense no-caps class="q-px-sm">
          <q-avatar size="24px" class="q-mr-xs">
            <!-- no-referrer: googleusercontent refuses avatar requests that carry one -->
            <img
              v-if="user.avatar" :src="user.avatar" referrerpolicy="no-referrer"
              :alt="user.name || 'account'"
            />
            <q-icon v-else name="account_circle" size="24px" />
          </q-avatar>
          <span class="gt-xs">{{ user.name || PROVIDER_LABELS[user.provider] || 'account' }}</span>
          <q-icon name="arrow_drop_down" size="18px" />
          <q-menu auto-close>
            <q-list dense>
              <q-item>
                <q-item-section>
                  <q-item-label caption>
                    via {{ PROVIDER_LABELS[user.provider] || user.provider }}
                    <span v-if="user.llm_allowed"> · LLM access</span>
                  </q-item-label>
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable @click="doLogout">
                <q-item-section avatar><q-icon name="logout" size="18px" /></q-item-section>
                <q-item-section>sign out</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
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
          <q-tab name="reading" label="Reading plots" />
          <q-tab name="groups" label="Groupings" />
          <q-tab name="data" label="Data choices" />
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
            <p>
              It is a fusion of four ancestors. From
              <a href="https://typometrics.elizia.net" target="_blank" rel="noopener">typometrics</a>
              come the measures and the scatter plots — but where that site offers a
              fixed set of precomputed measures, here every measure is a query you can
              write and edit. From the
              <a href="https://grew.fr/doc/request/" target="_blank" rel="noopener">Grew</a>
              query language and the
              <a href="https://universal.grew.fr" target="_blank" rel="noopener">universal.grew.fr</a>
              match server comes the way of asking — the search tab plays that server's
              role across all of UD and SUD at once. From
              <a href="https://autogramm.github.io/grex-lrec-coling-2024/" target="_blank" rel="noopener">grex</a>
              (Herrera, Le Corro &amp; Kahane 2024, LREC-COLING) comes the shape of a
              measure itself — the <b>scope / response</b> query pair. And from
              <a href="https://aclanthology.org/2025.tlt-1.4/" target="_blank" rel="noopener">
              Deworetzki &amp; Ljunglöf 2025</a> comes the graph-database encoding: the
              treebanks live in Neo4j, which is what turns a corpus-wide Grew query from
              minutes of scanning into seconds.
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
          <q-tab-panel name="reading" class="about-text">
            <!-- Condensed from the old site's "Interpretation of graphs"
                 (Presentation.vue, Gerdes & Peng) — the only real documentation the
                 measures ever had, ported rather than lost. -->
            <p>
              <b>One dimension.</b> Collapse the Y axis and each language is a point on a
              single 0–100 scale, one strip per family. Where the mass sits is the
              typology: on head-initiality of <code>subj</code>, most languages sit far
              left — subjects overwhelmingly precede the verb. The <i>density</i> option
              draws the distribution over the strip.
            </p>
            <p>
              <b>Two dimensions.</b> Each language is placed by its two values. Japanese
              has 0.4% of subjects and 7.4% of objects after the verb, so it sits in the
              bottom-left corner of the subject–object plot. The <i>diagonal</i> (y = x)
              is worth switching on when both axes share a scale: which side of it a
              language falls on says which of the two measures is larger.
            </p>
            <p>
              <b>The cloud's shape is the finding.</b> A cloud filling a square means the
              two measures vary freely. An empty corner is an
              <b>implicational universal</b>: a triangle with no points at top-left reads
              "every language that does X also does Y, but not the reverse" — the
              pronominal-versus-nominal object plot in
              <a href="https://doi.org/10.5334/gjgl.764" target="_blank" rel="noopener">
              Gerdes, Kahane &amp; Chen 2021</a> is the canonical example. Tight clusters
              are families or areas; switching <i>colour by</i> between family, area and
              typology helps tell inheritance from convergence.
            </p>
            <p>
              <b>Practical reading aids.</b> Click a family in the legend to hide it —
              Indo-European covers everything else. <i>Fit axes</i> zooms a percentage
              axis to the distribution. <i>Error bars</i> show each point's 95% interval.
              The <i>min. scope matchings</i> slider hides languages whose denominator is
              too small to trust, and says how many it hid.
            </p>
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
              number — scope too small, interval too wide, or fewer than 10 hits — the
              language is re-measured on a tenfold sample: automatically when that is
              cheap ("refined on a larger sample" in the progress line), and for the
              largest languages, where the rescan takes minutes, a banner proposes it
              instead ("refine on a larger sample"). <i>Exact (no sampling)</i> in the
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
            <p>
              <b>Logging.</b> Queries are logged — their text, timing and result size,
              to improve the tool and find slow query shapes — but never who asked: no
              IP address or account is recorded, and entries are deleted after 180 days.
            </p>
          </q-tab-panel>
          <q-tab-panel name="groups" class="about-text">
            <p>
              Every language carries <b>six groupings</b>, and "Colour by" on the plot
              picks one. They are curation decisions from the original typometrics
              configuration, not derived data — which is why "Agglutinating" can sit
              beside "Semitic" in the default view.
            </p>
            <q-btn-toggle
              v-model="groupingsView" dense no-caps unelevated toggle-color="primary"
              :options="groupingsViews.map((v) => ({ label: v.replace(/_/g, ' '), value: v }))"
              class="q-mb-xs"
            />
            <p class="text-caption text-grey-7 q-mb-sm">
              {{ VIEW_EXPLANATIONS[groupingsView] }}
            </p>
            <div v-if="currentGroups.length" class="groupings-list">
              <div
                v-for="entry in currentGroups" :key="entry.label"
                class="grouping-row" :title="entry.languages.join(', ')"
              >
                <span class="grouping-swatch" :style="{ color: entry.color }">
                  {{ MARKER_GLYPHS[entry.marker] || '●' }}
                </span>
                <span class="grouping-name">{{ entry.label }}</span>
                <span class="text-caption text-grey-7">{{ entry.languages.length }}</span>
              </div>
            </div>
            <div v-else class="text-caption text-grey-7">loading…</div>
            <p class="text-caption text-grey-7 q-mt-sm q-mb-none">
              Hover a group for its languages. Colours and markers live in
              <code>data/meta/*.tsv</code>; an unconfigured language plots grey.
            </p>
          </q-tab-panel>
          <!-- Mirrors docs/data-choices.md — the two must change together. -->
          <q-tab-panel name="data" class="about-text">
            <p>
              Raw UD/SUD releases are not analysis-ready: some treebanks duplicate each
              other, some "languages" are not one language, and some classifications in
              the inherited configuration were wrong. Every departure we make from the
              raw data is listed here; anything not listed is served as released.
            </p>
            <p class="q-mb-xs"><b>Deduplicated / excluded from language points</b>
              (still individually searchable):</p>
            <ul>
              <li><b>Chinese-GSDSimp</b> — the same 4,997 sentences as GSD, re-scripted;
                keeping both counted one corpus twice.</li>
              <li><b>Japanese-BCCWJLUW / -GSDLUW / -PUDLUW</b> — the same texts
                re-tokenized (long-unit words); keeping both counted every Japanese
                sentence twice under two segmentations.</li>
              <li><b>French-PoitevinDIVITAL</b> — Poitevin is a distinct Oïl variety,
                not modern French; pending its own language point.</li>
            </ul>
            <p class="q-mb-xs"><b>Corrected classifications</b> (they were factually
              wrong): Macedonian → Baltoslavic (was Hellenic); Madi, Paumarí → Arawan;
              Xavánte, Borôro → Macro-Jê; Vietnamese → Austroasiatic and Thai → Kra-Dai
              (neither is Sino-Austronesian); sign languages → their own <b>Sign</b>
              group (not Romance/Germanic); Haitian Creole and Naija → <b>Creole</b>
              (not their lexifiers' branches; Naija's area is Africa); Persian, Pashto,
              Zazaki, the Kurdish varieties → the <b>Iranian</b> branch (they showed as
              bare "Indo-European"); Armenian and Albanian likewise named as branches;
              the code-switching corpora (Telugu-English, Turkish-English,
              Turkish-German, Maghrebi-Arabic-French) carry an honest
              <b>Code-switching</b> label instead of one parent's family.</p>
            <p class="q-mb-xs"><b>Deliberate oddities we keep:</b> a language point
              merges all its treebanks (registers, genres, centuries — click a dot for
              the per-treebank values; when they disagree beyond the error bar, the
              merged number describes the corpus mix, not the language); historical
              stages are separate, unflagged points (~24 of ~190); "Agglutinating"
              deliberately overrides the family for six languages; "Sino-Austronesian"
              follows Sagart's hypothesis for Sinitic + Austronesian; all IE branches
              plot royalBlue so IE reads as one block — use the genus view for
              branch colours.</p>
            <p class="q-mb-xs"><b>The basic tree only:</b> UD's <i>enhanced</i> graph
              (extra edges, empty nodes) is not imported — we count the basic tree. On
              an enhanced treebank the same query in grew-match can return nearly
              double our count (measured: <code>1=aux</code> on English-GUM, 16,859
              enhanced vs 8,257 basic). Different graphs, not a disagreement.</p>
            <p class="text-caption text-grey-7 q-mb-none">
              Beyond the treebank selection above, no count is altered: these choices
              decide which treebanks enter a language's point and what the legend calls
              things. The canonical list lives in <code>docs/data-choices.md</code>.
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
              <li><a href="https://github.com/typometrics/grugrutyp" target="_blank" rel="noopener">
                github.com/typometrics/grugrutyp</a> — this tool's source</li>
            </ul>
            <p class="text-weight-medium q-mb-xs">Papers</p>
            <ul class="q-mt-none">
              <li>Gerdes, Kahane &amp; Chen (2021)
                <a href="https://doi.org/10.5334/gjgl.764" target="_blank" rel="noopener">
                Typometrics: From Implicational to Quantitative Universals in Word Order
                Typology</a>, <i>Glossa</i> 6(1) — the programme this site implements</li>
              <li>Kahane, Peng &amp; Gerdes (2023)
                <a href="https://aclanthology.org/2023.depling-1.7/" target="_blank" rel="noopener">
                Word order flexibility: a typometric study</a>, <i>Depling</i></li>
              <li>Chen, Gerdes, Kahane &amp; Courtin (2021)
                <a href="https://gerdes.fr/papiers/2021/The%20Co-Effect%20of%20Menzerath-Altmann%20Law%20and%20Heavy%20Constituent%20Shift%20in%20Natural%20Languages.pdf"
                   target="_blank" rel="noopener">
                The Co-Effect of Menzerath-Altmann Law and Heavy Constituent Shift</a>,
                <i>Qualico</i> — behind the Menzerath presets</li>
              <li>Herrera, Le Corro &amp; Kahane (2024)
                <a href="https://autogramm.github.io/grex-lrec-coling-2024/" target="_blank" rel="noopener">
                grex</a>, <i>LREC-COLING</i> — the scope/response query-pair vocabulary</li>
              <li>Deworetzki &amp; Ljunglöf (2025)
                <a href="https://aclanthology.org/2025.tlt-1.4/" target="_blank" rel="noopener">
                Graph Databases for Fast Queries in UD Treebanks</a>, <i>TLT</i> — the
                Neo4j encoding</li>
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
        <div v-if="adminVisible" v-show="tab === 'admin'" class="full-height view-scroll">
          <AdminView />
        </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { api, admin, auth } from './api'
import { user, authProviders, loadUser, logout } from './user'
import logoUrl from './assets/grugrutyp.svg'
import logoDarkUrl from './assets/grugrutyp-dark.svg'
import AdminView from './views/AdminView.vue'
import PlotView from './views/PlotView.vue'
import SearchView from './views/SearchView.vue'

const $q = useQuasar()

function toggleDark() {
  $q.dark.toggle()
  localStorage.setItem('grugrutyp-dark', $q.dark.isActive ? '1' : '0')
}

const tab = ref('plot')

// The admin tab is not advertised: it appears once /grugrutyp/admin is visited in this
// browser or a token is already stored; the token is what actually gates the API.
const adminVisible = ref(!!admin.token())

// Each tab is a real path -- /grugrutyp/search, /grugrutyp/admin -- served by nginx's
// SPA fallback (try_files ... /grugrutyp/index.html), so no '#/' routing like the old
// site's. Shared-plot links (#plot=...) are a genuine fragment and stay one: the plot
// definition is kept out of server logs on purpose, and PlotView consumes and clears it.
const BASE = import.meta.env.BASE_URL // '/grugrutyp/'
const TAB_PATHS = { plot: `${BASE}typometrics`, search: `${BASE}search`, admin: `${BASE}admin` }
// The old '#/search'-style addresses are bookmarked and in sent links; they redirect.
const LEGACY_HASHES = { '#/typometrics': 'plot', '#/search': 'search', '#/admin': 'admin' }

function applyAddressTab() {
  const fromHash = LEGACY_HASHES[location.hash]
  const found =
    fromHash || Object.entries(TAB_PATHS).find(([, path]) => location.pathname === path)?.[0]
  if (!found) return
  if (found === 'admin') adminVisible.value = true
  tab.value = found
  if (fromHash) {
    history.replaceState(null, '', TAB_PATHS[found] + location.search)
  }
}
watch(tab, (value) => {
  if (location.pathname !== TAB_PATHS[value]) {
    history.replaceState(null, '', TAB_PATHS[value] + location.search)
  }
})

const aboutOpen = ref(false)
const aboutTab = ref('what')
const corpusVersion = ref('')

const PROVIDER_LABELS = { google: 'Google', github: 'GitHub', orcid: 'ORCID' }
// Quasar bundles Material icons only; the brands get close-enough glyphs rather than
// three inline SVG logos with three trademark policies.
const PROVIDER_ICONS = { google: 'alternate_email', github: 'code', orcid: 'science' }

async function doLogout() {
  await logout()
  $q.notify({ message: 'signed out', timeout: 1200, position: 'bottom-right' })
}

// ------------------------------------------------------------- groupings tab data
const VIEW_EXPLANATIONS = {
  family:
    'The default — the granularity the original site plotted at: mostly genetic ' +
    'families (Italic, Semitic), with typological classes like Agglutinating kept ' +
    'alongside on purpose.',
  group: 'The broadest genetic unit: Indo-European, Afroasiatic, Caucasian…',
  genus: 'One level finer than the family view: Japonic, Italic, Iranian…',
  simple_group: 'A deliberately coarse split, for plots where family colours are noise.',
  area:
    'Geographic, not genetic — inheritance between levels does not apply. Codes from ' +
    'the original configuration: E Europe · ME Middle East · As Asia · I Indian ' +
    'subcontinent · SA South America · Af Africa · O Oceania.',
  typology: 'Morphological type cutting across genetics: Agglutinating, Isolating…',
}
const MARKER_GLYPHS = {
  circle: '●', triangle: '▲', rect: '■', rectRot: '◆', rectRounded: '▮',
  cross: '✚', crossRot: '✖', star: '✳', line: '▬', dash: '╌',
}
const groupingsView = ref('family')
const groupingsViews = ref(['family'])
const groupingsCache = ref({})

const currentGroups = computed(() => groupingsCache.value[groupingsView.value] || [])

async function loadGroupings(view) {
  if (groupingsCache.value[view]) return
  const response = await api.languages(view)
  groupingsViews.value = response.views
  const byLabel = new Map()
  for (const item of response.languages) {
    const label = item.label || 'unknown'
    if (!byLabel.has(label)) {
      byLabel.set(label, {
        label,
        color: (item.color || 'darkgrey').toLowerCase(),
        marker: item.marker || 'circle',
        languages: [],
      })
    }
    byLabel.get(label).languages.push(item.language.replace(/_/g, ' '))
  }
  groupingsCache.value = {
    ...groupingsCache.value,
    [view]: [...byLabel.values()].sort((a, b) => b.languages.length - a.languages.length),
  }
}

watch([aboutOpen, aboutTab, groupingsView], () => {
  if (aboutOpen.value && aboutTab.value === 'groups') loadGroupings(groupingsView.value)
})
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
  applyAddressTab()
  loadUser()
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
.groupings-list {
  columns: 2;
  max-height: 320px;
  overflow-y: auto;
}
.grouping-row {
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 1px 4px;
  break-inside: avoid;
  cursor: default;
}
.grouping-swatch {
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}
.grouping-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.about-text p {
  margin-bottom: 10px;
}
</style>
