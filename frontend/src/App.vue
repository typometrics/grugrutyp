<template>
  <q-layout view="hHh lpR fFf">
    <!-- Ivory, bordered, dark green on it: the header follows the logo's palette rather
         than fighting it with a blue bar. The logo IS the wordmark, so no text title. -->
    <q-header bordered class="site-header">
      <q-toolbar class="q-py-xs">
        <img :src="logoUrl" alt="grugrutyp" class="site-logo q-mr-md" />
        <span class="site-subtitle gt-sm">Grew queries over UD &amp; SUD</span>
        <q-tabs
          v-model="tab" dense no-caps shrink class="q-ml-md"
          active-color="primary" indicator-color="accent"
        >
          <q-tab name="plot" icon="scatter_plot" label="Typometrics" />
          <q-tab name="search" icon="account_tree" label="Search" />
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
          flat dense no-caps icon="help_outline" label="Grew syntax"
          href="https://grew.fr/doc/request/" target="_blank"
        />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <q-page>
        <q-banner v-if="loadError" dense class="bg-red-1 text-red-9">
          <template #avatar><q-icon name="error_outline" /></template>
          {{ loadError }}
        </q-banner>

        <!-- Both views stay mounted: a plot takes a minute to compute and switching to a
             tree and back must not throw it away. -->
        <div v-show="tab === 'plot'">
          <PlotView :treebanks="treebanks" @open-search="openSearch" />
        </div>
        <div v-show="tab === 'search'">
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
import { nextTick, onMounted, ref } from 'vue'
import { api } from './api'
import logoUrl from './assets/grugrutyp.svg'
import PlotView from './views/PlotView.vue'
import SearchView from './views/SearchView.vue'

const tab = ref('plot')
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
  try {
    const response = await api.treebanks()
    treebanks.value = response.treebanks
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
.site-logo {
  height: 42px;
  display: block;
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
.opacity-70 {
  opacity: 0.7;
}
.audit-tooltip {
  max-width: 460px;
  font-size: 12px;
}
</style>
