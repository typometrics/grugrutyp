<template>
  <div class="row full-height no-wrap">
    <!-- Everything except the chat: the chat is a sibling SIDEBAR, so opening it pushes
         the plot aside instead of covering it. min-width 0 lets the pane shrink, and
         no-wrap is load-bearing: Quasar's .column wraps by default, and in a wrapping
         column the flex line takes the width of its widest child's CONTENT — the chart
         canvas — so .plot-area would stretch to the old canvas width and overflow under
         the sidebar instead of shrinking with the pane (measured, not theory). -->
    <div class="column col main-pane no-wrap">
    <!-- ================================== axis panels, across the top (Kim's layout) -->
    <div class="axes q-px-sm q-pt-sm q-pb-xs">
      <div class="row q-col-gutter-sm items-stretch">
        <div :class="yCollapsed ? 'col' : 'col-12 col-md-6'">
          <AxisPanel
            axis="x" :presets="presets" :treebank="previewTreebank" :scheme="scheme" :label="x.label"
            v-model:scope="x.scope" v-model:response="x.response"
            v-model:kind="x.kind" v-model:expression="x.expression"
            v-model:aggregation="x.aggregation" v-model:unit="x.unit"
            @label="(v) => (x.label = v)"
          />
        </div>
        <div v-if="!yCollapsed" class="col-12 col-md-6">
          <AxisPanel
            axis="y" :presets="presets" :treebank="previewTreebank" :scheme="scheme"
            collapsible :label="y.label"
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
        <q-btn
          v-if="points.length && !yCollapsed" flat dense no-caps icon="query_stats"
          label="statistics" @click="statsOpen = true"
        >
          <q-tooltip>
            Correlation, regression, cloud shape — computed in the browser, no account
            needed
          </q-tooltip>
        </q-btn>
        <q-chip
          v-if="restrictLanguages" dense removable color="accent" text-color="white"
          @remove="restrictLanguages = null"
        >
          {{ restrictLanguages.length }} language{{ restrictLanguages.length === 1 ? '' : 's' }} only
          <q-tooltip>{{ restrictLanguages.join(', ') }} — remove to plot all languages</q-tooltip>
        </q-chip>
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
          <!-- Live escalation notices: a run silently re-reading a million tokens now
               says which language it is doing that for, while it does it. -->
          <span v-if="running && refiningNow.length" class="text-orange-9">
            · enlarging the sample for {{ refiningNowNames }}…
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
                  <span v-for="entry in refineShown" :key="entry.name" class="tip-lang">
                    {{ entry.name }}&nbsp;<span class="tip-size">{{ entry.size }}</span>
                  </span>
                  <span v-if="refineHidden" class="tip-lang tip-more">
                    +{{ refineHidden }} more
                  </span>
                </div>
                <div class="tip-heading">Why</div>
                <p>
                  Every language is measured on a bounded sample. When that proves too
                  thin — this measure left too few matchings, or too wide an interval —
                  the sample normally grows tenfold by itself. But each such rescan costs
                  minutes on this corpus, so a run performs only a handful automatically,
                  and the largest languages never rescan unasked. The rest wait for you
                  here.
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

      <!-- An empty plot with a live progress line reads as a hang; when the cause is a
           scope that matched nothing anywhere, say so, and say WHICH axis. Learned the
           hard way: a 2=relcl that should have been mod@relcl ran the full corpus for a
           blank screen. -->
      <q-banner v-if="deadAxis && !running" dense class="refine-banner q-mt-sm">
        <template #avatar><q-icon name="search_off" /></template>
        The <b>{{ deadAxis }} axis scope matched nothing in any language</b>, and a point
        needs both axes — that is why the plot is empty. The live preview under that
        scope shows the same zero on one treebank. A frequent cause in SUD: deep
        relations are written <code>mod@relcl</code>, not <code>2=relcl</code>.
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
        :regression="showRegression && plotStats ? plotStats.regression : null"
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

    </div><!-- /main-pane -->

    <!-- ------------------------------------- plot statistics (no LLM, no account) -->
    <PlotStatistics
      v-model="statsOpen" v-model:show-line="showRegression"
      :stats="plotStats" :x-label="xLabel" :y-label="yLabel"
    />

    <!-- ----------------------------------------------- the side chat (Phase 6.6) -->
    <q-btn
      v-if="user?.llm_allowed && !chatOpen" round color="primary" icon="forum"
      class="chat-fab" @click="chatOpen = true"
    >
      <q-tooltip anchor="top middle" self="bottom middle">
        Talk through a comparison — the assistant proposes the queries
      </q-tooltip>
    </q-btn>
    <div v-if="chatOpen" class="chat-panel column no-wrap" :style="{ width: chatWidth + 'px' }">
      <div class="chat-resize" @pointerdown="startChatResize" />
      <div class="row items-center q-px-sm q-py-xs chat-head">
        <q-icon name="forum" size="16px" class="q-mr-xs" />
        <span class="text-weight-medium">typometrics assistant</span>
        <q-space />
        <q-btn flat dense round size="sm" icon="close" @click="chatOpen = false" />
      </div>
      <div ref="chatScroll" class="chat-scroll col q-pa-sm">
        <div v-if="!chatMessages.length" class="text-caption text-grey-7">
          Say what you want to compare — a phenomenon, two phenomena against each other,
          for all languages or a family. The assistant proposes the queries and comments
          them; nothing runs until you approve.
        </div>
        <div v-for="(message, index) in chatMessages" :key="index" class="q-mb-sm">
          <!-- Language and group names in the prose are live: click one and it rings on
               the plot, exactly like typing it in the find box. -->
          <div class="chat-bubble" :class="message.role">
            <template v-for="(segment, si) in chatSegments(message.content)" :key="si">
              <a v-if="segment.name" class="lang-link" @click="ringLanguage(segment.name)">{{ segment.text }}</a>
              <template v-else>{{ segment.text }}</template>
            </template>
          </div>
          <!-- Proposal cards: one from a chat turn, up to three follow-ups from an
               analysis. Same card, same approval: nothing runs until "load & plot". -->
          <div
            v-for="(proposal, pi) in message.proposals || []" :key="'proposal' + pi"
            class="chat-proposal q-mt-xs"
          >
            <div v-if="proposal.comment" class="text-caption q-mb-xs">
              <template v-for="(segment, si) in chatSegments(proposal.comment)" :key="si">
                <a v-if="segment.name" class="lang-link" @click="ringLanguage(segment.name)">{{ segment.text }}</a>
                <template v-else>{{ segment.text }}</template>
              </template>
            </div>
            <pre class="grew-snippet nl-draft">X — {{ proposal.x.label || 'measure' }}
{{ proposal.x.scope }}{{ proposal.x.response ? '\n' + proposal.x.response : '' }}{{ proposal.x.expression ? '\n' + proposal.x.aggregation + ' of ' + proposal.x.expression : '' }}</pre>
            <pre v-if="proposal.y" class="grew-snippet nl-draft">Y — {{ proposal.y.label || 'measure' }}
{{ proposal.y.scope }}{{ proposal.y.response ? '\n' + proposal.y.response : '' }}{{ proposal.y.expression ? '\n' + proposal.y.aggregation + ' of ' + proposal.y.expression : '' }}</pre>
            <div v-if="proposal.languages" class="text-caption text-grey-7">
              restricted to:
              <template v-for="(name, ni) in proposal.languages" :key="ni">
                <a class="lang-link" @click="ringLanguage(name)">{{ name }}</a><span
                  v-if="ni < proposal.languages.length - 1">, </span>
              </template>
            </div>
            <q-btn
              dense unelevated no-caps size="sm" color="primary" icon="scatter_plot"
              label="load & plot" class="q-mt-xs" @click="applyProposal(proposal)"
            />
          </div>
        </div>
        <div v-if="chatBusy" class="text-caption text-grey-7">thinking…</div>
      </div>
      <div class="row q-pa-xs q-gutter-xs items-end chat-input-row">
        <q-input
          ref="chatInputBox"
          v-model="chatInput" dense outlined autogrow class="col"
          placeholder="e.g. compare adjective and numeral placement in Slavic"
          @keydown.enter.exact.prevent="sendChat"
        />
        <q-btn
          dense flat icon="send" :disable="chatBusy || !chatInput.trim()" @click="sendChat"
        />
      </div>
      <div class="q-px-sm q-pb-xs">
        <q-btn
          v-if="points.length && !running" dense flat no-caps size="sm" icon="insights"
          label="analyse these results" :loading="analysing" @click="analyseResults"
        >
          <q-tooltip>
            analyses the plot on screen: {{ xLabel }}{{ yCollapsed ? '' : ' × ' + yLabel }}
          </q-tooltip>
        </q-btn>
      </div>
    </div>

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
              <q-item-section>
                {{ name }}
                <q-item-label caption>{{ treebankValues(name) }}</q-item-label>
              </q-item-section>
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
import { api, llm, myQueries } from '../api'
import { user } from '../user'
import AppearanceCustomize from '../components/AppearanceCustomize.vue'
import AxisPanel from '../components/AxisPanel.vue'
import PlotStatistics from '../components/PlotStatistics.vue'
import ScatterPlot from '../components/ScatterPlot.vue'
import { matchesFind } from '../findmatch'
import { scatterStats } from '../stats'

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
// The server clamps anonymous "exact" to 1M tokens/language (the escalation ceiling)
// -- exact disk-scans of the giants are for signed-in users. Say so in the option
// rather than silently serving a different coverage than the label promised.
const budgetOptions = computed(() => [
  { label: 'Fast — 100k tokens/language', value: 100000 },
  { label: 'Closer — 500k tokens/language', value: 500000 },
  {
    label: user.value ? 'Exact — no sampling' : 'Exact — up to 1M tokens/language (sign in for full)',
    value: 0,
  },
])
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
    restrictLanguages.value,
  ])
}
const plotStale = computed(
  () => progress.total > 0 && ranSignature.value !== computeSignature(),
)

const running = ref(false)
const error = ref('')
const progress = reactive({ done: 0, total: 0 })
// Languages currently having their sample enlarged (the `escalating` SSE event);
// a language leaves the list when its points land.
const refiningNow = ref([])
const refiningNowNames = computed(() => {
  const names = refiningNow.value.map((l) => l.replace(/_/g, ' '))
  return names.length <= 3 ? names.join(', ') : `${names.slice(0, 3).join(', ')} +${names.length - 3}`
})
const elapsed = ref(0)
const rawLanguages = ref([[], []])
const perTreebank = ref([])
const plot = ref(null)
let handle = null
let timer = null

const detailOpen = ref(false)
const detail = ref(null)

/**
 * One treebank's own values for the drill-down dialog — the heterogeneity diagnostic
 * the audit asked for (typology §8): a language whose treebanks disagree by twenty
 * points must show it where the treebanks are listed, not hide it behind per-treebank
 * searches. The counts are already streamed per treebank; this just reads them.
 */
function treebankValues(name) {
  const row = perTreebank.value.find((r) => r.treebank === name)
  if (!row || !row.axes?.length) return ''
  const one = (axis, spec) => {
    if (!axis || axis.value == null || !axis.n_scope) return null
    return axis.value.toFixed(1) + (spec.kind === 'aggregate' ? '' : '%')
  }
  const parts = []
  const xPart = one(row.axes[0], x)
  if (xPart) parts.push(xPart)
  if (!yCollapsed.value && row.axes[1]) {
    const yPart = one(row.axes[1], y)
    if (yPart) parts.push(yPart)
  }
  if (!parts.length) return 'below min scope'
  return `${parts.join(' · ')}  (n=${row.axes[0].n_scope.toLocaleString()})`
}

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
const totalLanguages = computed(() => {
  const chosen = restrictLanguages.value && new Set(restrictLanguages.value)
  return new Set(
    props.treebanks
      .filter((tb) => tb.scheme === scheme.value && (!chosen || chosen.has(tb.language)))
      .map((tb) => tb.language),
  ).size
})
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

// A rare measure can flag 40+ languages, and one chip per language turned the tooltip
// into a panel covering the whole plot with its own explanation pushed off screen
// (Kim, 2026-09-04). The list is sorted biggest-first and the big ones are the point,
// so the tail becomes a count.
const TIP_LANGS_SHOWN = 12
const refineShown = computed(() => refineDetails.value.slice(0, TIP_LANGS_SHOWN))
const refineHidden = computed(() => Math.max(0, refineDetails.value.length - TIP_LANGS_SHOWN))

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

/** The axis whose scope matched nothing anywhere -- a language only reaches
 *  `rawLanguages` for an axis when its scope counted something, so an empty axis list
 *  next to a populated one names the culprit. */
const deadAxis = computed(() => {
  if (!progress.total || points.value.length) return ''
  const [xs, ys] = rawLanguages.value
  if (xs.length && !yCollapsed.value && !ys.length) return 'Y'
  if (!xs.length && (yCollapsed.value || ys.length)) return 'X'
  return ''
})

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
const foundCount = computed(() =>
  points.value.filter((p) => matchesFind(p.language, p.label, findLanguage.value)).length,
)

function openFoundLanguage() {
  const match = points.value.find((p) => matchesFind(p.language, p.label, findLanguage.value))
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
  // The machine remembers what was last plotted: a reload restores it (share links
  // still win — they are applied first and then saved by this very line).
  try {
    localStorage.setItem(LAST_PLOT_KEY, encodeState())
  } catch { /* a full or blocked localStorage must never block a plot */ }
  running.value = true
  progress.done = 0
  progress.total = 0
  refiningNow.value = []
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
  if (restrictLanguages.value) {
    const chosen = new Set(restrictLanguages.value)
    body.treebanks = props.treebanks
      .filter((tb) => tb.scheme === scheme.value && chosen.has(tb.language))
      .map((tb) => tb.name)
  }

  handle = api.measure(body, (name, data) => {
    if (name === 'start') {
      progress.total = data.n_treebanks
    } else if (name === 'escalating') {
      if (!refiningNow.value.includes(data.language)) {
        refiningNow.value = [...refiningNow.value, data.language]
      }
    } else if (name === 'point') {
      progress.done = data.done
      refiningNow.value = refiningNow.value.filter((l) => l !== data.language)
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
    langs: restrictLanguages.value,
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
  restrictLanguages.value =
    Array.isArray(state.langs) && state.langs.length ? state.langs : null
}

const LAST_PLOT_KEY = 'grugrutyp-last-plot'

// ---------------------------------------------------------- the side chat (6.6)
//
// The conversation lives in this component's memory only; the backend is stateless
// (the history travels with each turn) and each turn spends one unit of the same LLM
// quota. A proposal never runs itself: "load & plot" is the human in the loop.
// ---------------------------------------- plot statistics (no LLM, no account)
//
// Everything is computed in the browser from the plotted points (src/stats.js, verified
// against scipy by scripts/stats_check.py); it live-updates as points stream in. The
// regression line follows the CURRENT points: replot and it refits.
const statsOpen = ref(false)
const showRegression = ref(false)
const plotStats = computed(() => (yCollapsed.value ? null : scatterStats(points.value)))

const chatOpen = ref(false)
const chatMessages = ref([])
const chatInput = ref('')
const chatBusy = ref(false)
const analysing = ref(false)
const chatScroll = ref(null)
const chatInputBox = ref(null)

// The panel opens to be typed in — put the cursor there.
watch(chatOpen, (open) => {
  if (open) nextTick(() => chatInputBox.value?.focus())
})

// The sidebar's width, draggable at its left edge and remembered.
const CHAT_WIDTH_KEY = 'grugrutyp-chat-width'
const chatWidth = ref(
  Math.min(
    Number(localStorage.getItem(CHAT_WIDTH_KEY)) || 420,
    Math.round(window.innerWidth * 0.7),
  ),
)

function startChatResize(event) {
  event.preventDefault() // no text selection while dragging
  const move = (e) => {
    chatWidth.value = Math.round(
      Math.min(Math.max(300, window.innerWidth - e.clientX), window.innerWidth * 0.7),
    )
  }
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    localStorage.setItem(CHAT_WIDTH_KEY, String(chatWidth.value))
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}

// ------------------------------------------------- clickable names in the chat prose
//
// Any known language or group name in a message becomes a find-language trigger.
// Matching is CASE-SENSITIVE on purpose: group labels like "Other" would otherwise
// linkify the word "other" in every sentence. Longest name first, so "Ancient Greek"
// wins over "Greek"; underscores and spaces both accepted in multi-word names.
const nameRegex = computed(() => {
  const names = new Set()
  for (const item of serverLanguages.value) {
    if (item.language) names.add(item.language.replace(/_/g, ' '))
    if (item.label) names.add(item.label)
  }
  for (const point of points.value) {
    names.add(point.language.replace(/_/g, ' '))
    if (point.label) names.add(point.label)
  }
  const sorted = [...names].filter((name) => name.length > 2).sort((a, b) => b.length - a.length)
  if (!sorted.length) return null
  const escaped = sorted.map((name) =>
    name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '[ _]'),
  )
  // Lookarounds, not \b: a name can end in a non-word character (K'iche') and \b
  // between two non-word characters never matches.
  return new RegExp(`(?<!\\w)(?:${escaped.join('|')})(?!\\w)`, 'g')
})

/** A message split into plain-text and clickable-name segments. */
function chatSegments(text) {
  const regex = nameRegex.value
  if (!regex) return [{ text }]
  const segments = []
  let last = 0
  regex.lastIndex = 0
  for (let match; (match = regex.exec(text)); ) {
    if (match.index > last) segments.push({ text: text.slice(last, match.index) })
    segments.push({ text: match[0], name: match[0].replace(/_/g, ' ') })
    last = match.index + match[0].length
  }
  if (last < text.length) segments.push({ text: text.slice(last) })
  return segments
}

function ringLanguage(name) {
  findLanguage.value = name.replace(/_/g, ' ')
}
// A proposal may restrict the plot to named languages; shown as a removable chip so a
// later manual Plot cannot silently stay restricted.
const restrictLanguages = ref(null)

function scrollChat() {
  nextTick(() => {
    if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight
  })
}

async function sendChat() {
  const text = chatInput.value.trim()
  if (!text || chatBusy.value) return
  chatMessages.value.push({ role: 'user', content: text })
  chatInput.value = ''
  chatBusy.value = true
  scrollChat()
  try {
    const history = chatMessages.value.map((m) => ({ role: m.role, content: m.content }))
    const result = await llm.chat(history, scheme.value)
    chatMessages.value.push(
      result.ok
        ? { role: 'assistant', content: result.reply,
            proposals: result.proposal ? [result.proposal] : null }
        : { role: 'assistant', content: `(that failed: ${result.error})` },
    )
  } catch (exception) {
    chatMessages.value.push({ role: 'assistant', content: `(error: ${exception.message})` })
  } finally {
    chatBusy.value = false
    scrollChat()
  }
}

function applyProposal(proposal) {
  const load = (axis, draft) => {
    axis.scope = draft.scope
    axis.response = draft.response
    axis.kind = draft.kind
    axis.expression = draft.expression || ''
    axis.aggregation = draft.aggregation || 'avg'
    axis.label = draft.label || ''
  }
  load(x, proposal.x)
  if (proposal.y) {
    load(y, proposal.y)
    yCollapsed.value = false
  } else {
    yCollapsed.value = true
  }
  if (proposal.languages) {
    const known = new Set(
      props.treebanks.filter((tb) => tb.scheme === scheme.value).map((tb) => tb.language),
    )
    const usable = proposal.languages.filter((name) => known.has(name))
    const unknown = proposal.languages.filter((name) => !known.has(name))
    if (unknown.length) {
      chatMessages.value.push({
        role: 'assistant',
        content: `(not in the corpus, skipped: ${unknown.join(', ')})`,
      })
    }
    restrictLanguages.value = usable.length ? usable : null
  } else {
    restrictLanguages.value = null
  }
  runPlot()
}

async function analyseResults() {
  analysing.value = true
  chatOpen.value = true
  try {
    const result = await llm.analyze({
      x_label: xLabel.value,
      y_label: yCollapsed.value ? '' : yLabel.value,
      scheme: scheme.value,
      points: points.value.slice(0, 400).map((p) => ({
        language: p.language,
        family: p.label,
        x: Number(p.x.toFixed(3)),
        y: yCollapsed.value ? null : Number(p.y.toFixed(3)),
      })),
      // What the axes compute and what was said so far: this is what lets the model
      // notice that the plot on screen is not the question just asked, say so, and
      // re-propose the right plot instead of analysing past the user.
      x_query: `${x.scope}\n${x.response}`.trim(),
      y_query: yCollapsed.value ? '' : `${y.scope}\n${y.response}`.trim(),
      messages: chatMessages.value.slice(-8).map((m) => ({ role: m.role, content: m.content })),
    })
    chatMessages.value.push({
      role: 'assistant',
      content: result.ok ? result.reply : `(analysis failed: ${result.error})`,
      proposals: result.ok && result.proposals?.length ? result.proposals : null,
    })
  } catch (exception) {
    chatMessages.value.push({ role: 'assistant', content: `(error: ${exception.message})` })
  } finally {
    analysing.value = false
    scrollChat()
  }
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

/**
 * A filename findable in Downloads next week: scheme + the axis labels, slugged —
 * `sud-2-token-subj-inversion-vs-3-token-subj-inversion.svg`. A chat plot gets the
 * model's own axis labels (every proposal names its axes), a preset its preset name,
 * and a bare hand-typed query the relation describe() extracts from the scope. No LLM
 * call at save time, so it works logged-out too.
 */
const exportName = computed(() => {
  const slug = (text) =>
    text.toLowerCase().replace(/%/g, 'pct').replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/, '')
  const parts = [scheme.value.toLowerCase(), slug(xLabel.value)]
  if (!yCollapsed.value && slug(yLabel.value)) parts.push('vs', slug(yLabel.value))
  if (restrictLanguages.value) parts.push(`${restrictLanguages.value.length}-languages`)
  const name = parts.filter(Boolean).join('-')
  return name.length > 8 ? name : 'grugrutyp-plot'
})

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
  download(
    new Blob([lines.join('\n')], { type: 'text/tab-separated-values' }),
    `${exportName.value}.tsv`,
  )
}

function exportPng() {
  const data = plot.value?.toPng()
  if (!data) return
  const link = document.createElement('a')
  link.href = data
  link.download = `${exportName.value}.png`
  link.click()
}

function exportSvg() {
  const svg = plot.value?.toSvg()
  if (!svg) return
  download(new Blob([svg], { type: 'image/svg+xml' }), `${exportName.value}.svg`)
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
  } else {
    // No link: this machine's last plotted query beats the default presets. Whatever
    // was last plotted is in the measures cache, so the auto-run below is fast.
    const saved = localStorage.getItem(LAST_PLOT_KEY)
    if (saved) {
      try {
        applyState(saved)
      } catch { /* an unreadable save (old version, cleared fields) → default presets */ }
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
.main-pane {
  min-width: 0;
}
/* The chat button floats where the panel opens — it reads as the panel's collapsed
   state, and disappears while the panel is up. */
.chat-fab {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 6;
}
/* The side chat: a full-height SIDEBAR flexed next to the main pane, so it pushes the
   plot aside rather than covering it, and stops below the site header by construction
   (the q-page is already the viewport minus the header). Width is inline, dragged at
   the left edge. `no-wrap` in the template is load-bearing: Quasar's .column wraps by
   default, and in a wrapping flex container the line takes the cross-size of its
   *widest child's content* — one long query line in a proposal <pre> and every
   stretched row (bubbles, the input) lays out wider than the panel and leaks out. */
.chat-panel {
  position: relative;
  flex: 0 0 auto;
  min-width: 300px;
  max-width: 70vw;
  height: 100%;
  background: #fff;
  border-left: 1px solid rgba(0, 0, 0, 0.2);
  box-shadow: -3px 0 12px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}
.chat-resize {
  position: absolute;
  left: -2px;
  top: 0;
  bottom: 0;
  width: 7px;
  cursor: col-resize;
  z-index: 1;
}
.chat-resize:hover {
  background: rgba(128, 128, 128, 0.25);
}
.lang-link {
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 2px;
}
.lang-link:hover {
  color: #d45500;
}
.body--dark .chat-panel {
  background: #232323;
  border-color: rgba(255, 255, 255, 0.2);
}
.chat-head {
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}
.body--dark .chat-head {
  border-bottom-color: rgba(255, 255, 255, 0.12);
}
.chat-scroll {
  overflow-y: auto;
  min-height: 0;
}
.chat-bubble {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.chat-bubble.user {
  background: rgba(20, 61, 20, 0.08);
  margin-left: 36px;
}
.chat-bubble.assistant {
  background: rgba(0, 0, 0, 0.045);
  margin-right: 20px;
}
.body--dark .chat-bubble.user {
  background: rgba(160, 210, 160, 0.14);
}
.body--dark .chat-bubble.assistant {
  background: rgba(255, 255, 255, 0.07);
}
.chat-proposal {
  margin-right: 20px;
  padding-left: 8px;
  border-left: 2px solid var(--q-accent);
}
.chat-input-row {
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
.body--dark .chat-input-row {
  border-top-color: rgba(255, 255, 255, 0.12);
}
.nl-draft {
  background: rgba(0, 0, 0, 0.05);
  padding: 6px 9px;
  border-radius: 4px;
  margin: 2px 0;
  /* the panel is 400px wide: wrap long query lines rather than hide them behind a
     horizontal scrollbar (overrides the global .grew-snippet white-space: pre) */
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.body--dark .nl-draft {
  background: rgba(255, 255, 255, 0.07);
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
/* Hard ceilings, not just a max-width: the language list grows with the measure, and
   a tooltip that outgrows the viewport hides both the plot and its own text. */
.refine-tooltip {
  max-width: min(460px, 88vw);
  max-height: min(560px, 70vh);
  overflow-y: auto;
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
.refine-tooltip .tip-more {
  border-style: dashed;
  opacity: 0.8;
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
