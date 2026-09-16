<template>
  <div class="findings-page q-pa-md">
    <div class="findings-column">
      <div class="text-body2 q-mb-md intro">
        Scatters the pattern-mining programme surfaced and a human kept — each with the
        reason it is interesting. Everything here is a <b>hypothesis</b>: it survived the
        permutation and lineage checks, not yet the full promotion protocol
        (<span class="mono">docs/pattern-mining.md</span>). "Plot it" opens the live
        measure — first visits compute the uncached languages, so points stream in.
        <q-btn
          flat dense no-caps color="primary" icon="help_outline" label="How this was done"
          class="q-ml-sm" @click="showMethod = true"
        />
      </div>

      <q-dialog v-model="showMethod">
        <q-card class="method-card">
          <q-card-section class="row items-center q-pb-none">
            <div class="text-h6">{{ method.title || 'How this was done' }}</div>
            <q-space />
            <q-btn icon="close" flat round dense v-close-popup />
          </q-card-section>
          <q-card-section>
            <template v-for="section in method.sections" :key="section.heading">
              <div class="text-subtitle2 q-mt-md">{{ section.heading }}</div>
              <div class="text-body2 why">{{ section.text }}</div>
            </template>
          </q-card-section>
        </q-card>
      </q-dialog>

      <q-banner v-if="error" dense class="bg-red-1 text-red-9 q-mb-md">
        <template #avatar><q-icon name="error_outline" /></template>
        {{ error }}
      </q-banner>

      <template v-for="group in groups" :key="group.name">
        <div class="text-overline text-grey-7 q-mt-lg q-mb-xs">{{ group.name }}</div>
        <q-card
          v-for="finding in group.findings" :key="finding.key"
          flat bordered class="q-mb-md finding-card"
        >
          <q-card-section class="q-pb-xs">
            <div class="text-h6">{{ finding.title }}</div>
            <div class="text-caption text-grey-7">{{ finding.stats }}</div>
          </q-card-section>
          <q-card-section class="q-pt-xs text-body2 why">
            {{ finding.why }}
          </q-card-section>
          <q-card-actions>
            <q-btn
              unelevated no-caps color="primary" icon="scatter_plot" label="Plot it"
              @click="$emit('open-plot', encode(finding.state))"
            />
            <q-btn
              flat no-caps color="grey-7" icon="link" label="Copy link"
              @click="copyLink(finding)"
            />
          </q-card-actions>
        </q-card>
      </template>

      <div class="text-overline text-grey-7 q-mt-lg q-mb-xs">All scored pairs</div>
      <q-card flat bordered class="q-mb-xl">
        <q-card-section class="q-pb-none text-body2 why">
          The {{ ranked.n_shown }} strongest of the {{ ranked.n_pairs_scored }} measure
          pairs the miner scored, with every score component kept separate. <b>Sorting by
          a column is choosing your own definition of interesting</b>: |r| for the
          tightest laws, grid emptiness for forbidden regions, lineage survival for
          family-proof patterns, claim support for inequality universals. Plotting is one
          click; the prose is yours to write.
        </q-card-section>
        <q-card-section>
          <q-table
            :rows="ranked.pairs" :columns="columns" row-key="key"
            :filter="tableFilter" :pagination="{ rowsPerPage: 15, sortBy: 'surprise', descending: true }"
            flat dense wrap-cells binary-state-sort
          >
            <template #top>
              <q-input
                v-model="tableFilter" dense outlined clearable debounce="200"
                placeholder="filter by measure name…" class="table-filter"
              >
                <template #prepend><q-icon name="search" /></template>
              </q-input>
            </template>
            <template #body-cell-plot="props">
              <q-td :props="props">
                <q-btn
                  v-if="props.row.state" dense flat round color="primary" icon="scatter_plot"
                  @click="$emit('open-plot', encode(props.row.state))"
                >
                  <q-tooltip>plot this pair</q-tooltip>
                </q-btn>
                <q-icon v-else name="block" color="grey-5">
                  <q-tooltip>uses the miner's exclusion list — not expressible as one query pair</q-tooltip>
                </q-icon>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { api } from '../api'

defineEmits(['open-plot'])
const $q = useQuasar()

const findings = ref([])
const method = ref({ sections: [] })
const error = ref('')
const showMethod = ref(false)
const ranked = ref({ n_pairs_scored: 0, n_shown: 0, pairs: [] })
const tableFilter = ref('')

const num = (field) => (row) => Number(row[field]) || 0
const columns = [
  { name: 'plot', label: '', field: 'state', sortable: false, align: 'center' },
  { name: 'x', label: 'X', field: 'x', sortable: true, align: 'left' },
  { name: 'y', label: 'Y', field: 'y', sortable: true, align: 'left' },
  { name: 'n_langs', label: 'n', field: num('n_langs'), sortable: true },
  { name: 'pearson', label: 'r', field: num('pearson'), sortable: true },
  { name: 'lineage_r', label: 'lineage r', field: num('lineage_r'), sortable: true },
  { name: 'grid_empty', label: 'empty region', field: num('grid_empty'), sortable: true },
  { name: 'boot_survival', label: 'lineage survival', field: num('boot_survival'), sortable: true },
  {
    name: 'claim', label: 'inequality', field: 'claim', sortable: true, align: 'left',
    format: (v, row) => (v && Number(row.claim_viol_rate) <= 0.05 ? v : ''),
  },
  { name: 'surprise', label: 'surprise', field: num('surprise'), sortable: true },
]

// Same encoding as PlotView's share links: base64url of the UTF-8 JSON state.
function encode(state) {
  const bytes = new TextEncoder().encode(JSON.stringify(state))
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function copyLink(finding) {
  const url = `${location.origin}/grugrutyp/#plot=${encode(finding.state)}`
  navigator.clipboard.writeText(url)
  $q.notify({ message: 'link copied', timeout: 1200 })
}

// Groups in order of first appearance, so the JSON file controls the page order.
const groups = computed(() => {
  const seen = new Map()
  for (const finding of findings.value) {
    if (!seen.has(finding.group)) seen.set(finding.group, [])
    seen.get(finding.group).push(finding)
  }
  return [...seen.entries()].map(([name, list]) => ({ name, findings: list }))
})

onMounted(async () => {
  try {
    const response = await api.findings()
    findings.value = response.findings
    method.value = response.method || { sections: [] }
    const rankedResponse = await api.findingsRanked()
    rankedResponse.pairs.forEach((pair, index) => (pair.key = index))
    ranked.value = rankedResponse
  } catch (exception) {
    error.value = `could not load the findings (${exception.message})`
  }
})
</script>

<style scoped>
.findings-page {
  display: flex;
  justify-content: center;
}
.findings-column {
  max-width: 860px;
  width: 100%;
}
.why {
  line-height: 1.55;
}
.mono {
  font-family: monospace;
  font-size: 0.9em;
}
.intro {
  opacity: 0.85;
}
.method-card {
  max-width: 720px;
}
.table-filter {
  width: 280px;
}
</style>
