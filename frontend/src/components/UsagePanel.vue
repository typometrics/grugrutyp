<template>
  <div>
    <div class="row items-center q-gutter-sm q-mb-md">
      <q-btn-toggle
        v-model="days" dense no-caps unelevated toggle-color="primary"
        :options="[{ label: '30 days', value: 30 }, { label: '90 days', value: 90 },
                   { label: '1 year', value: 365 }]"
        @update:model-value="load"
      />
      <q-btn flat dense no-caps icon="refresh" label="refresh" @click="load" />
      <span class="text-caption text-grey-7">
        since {{ data?.since }} — from the site's nginx log (hourly) and the query log;
        no IPs stored, a visitor is counted per day
      </span>
    </div>

    <q-banner v-if="data && !data.available" dense class="bg-orange-1 q-mb-md">
      <code>data/usage.sqlite</code> does not exist yet — run
      <code>scripts/usage_stats.py --backfill</code>.
    </q-banner>

    <div class="row q-col-gutter-md q-mb-md">
      <div v-for="tile in tiles" :key="tile.label" class="col-6 col-sm-4 col-md-2">
        <q-card flat bordered>
          <q-card-section class="q-pa-sm">
            <div class="text-caption text-grey-7">{{ tile.label }}</div>
            <div class="text-h5">{{ tile.value.toLocaleString() }}</div>
            <div class="text-caption text-grey-6">{{ tile.note }}</div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-card flat bordered class="q-mb-md">
      <q-card-section class="q-pa-sm">
        <div class="text-subtitle2 q-mb-xs">Daily visitors (humans)</div>
        <div style="position: relative; height: 260px"><canvas ref="canvas" /></div>
      </q-card-section>
    </q-card>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-6">
        <div class="text-subtitle2 q-mb-xs">Queries run in grugrutyp, by kind</div>
        <q-markup-table dense flat bordered>
          <thead><tr><th class="text-left">kind</th><th class="text-right">runs</th>
            <th class="text-right">failed</th></tr></thead>
          <tbody>
            <tr v-for="row in queryTotals" :key="row.kind">
              <td>{{ row.kind }}</td><td class="text-right">{{ row.n }}</td>
              <td class="text-right">{{ row.errors }}</td>
            </tr>
            <tr v-if="!queryTotals.length"><td colspan="3" class="text-grey-6">none</td></tr>
          </tbody>
        </q-markup-table>
      </div>
      <div class="col-12 col-md-6">
        <div class="text-subtitle2 q-mb-xs">External referrers (human page views)</div>
        <q-markup-table dense flat bordered>
          <tbody>
            <tr v-for="row in data?.referrers || []" :key="row.host">
              <td>{{ row.host }}</td><td class="text-right">{{ row.n }}</td>
            </tr>
            <tr v-if="!(data?.referrers || []).length"><td class="text-grey-6">none</td></tr>
          </tbody>
        </q-markup-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale,
  Tooltip, Legend,
} from 'chart.js'
import { admin } from '../api'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend)

const emit = defineEmits(['error'])
const days = ref(90)
const data = ref(null)
const canvas = ref(null)
let chart = null

// Sections as written by scripts/usage_stats.py; `home` is `/` (the legacy SPA until the
// welcome page replaces it).
const SERIES = [
  { section: 'grugrutyp', label: 'grugrutyp', color: '#1f6feb' },
  { section: 'legacy', label: 'legacy site (API users)', color: '#b35900' },
  { section: 'home', label: 'home page /', color: '#6e7781' },
  { section: 'all', label: 'whole site', color: '#2da44e' },
]

function total(section, metric) {
  return (data.value?.counts || [])
    .filter((c) => c.section === section && c.metric === metric)
    .reduce((sum, c) => sum + c.n, 0)
}

const tiles = computed(() => [
  { label: 'grugrutyp visitors', value: total('grugrutyp', 'visitors'), note: 'sum of daily' },
  { label: 'grugrutyp page loads', value: total('grugrutyp', 'pageviews'), note: 'humans' },
  { label: 'measures run', value: total('grugrutyp', 'measures'), note: 'POST /measure' },
  { label: 'legacy visitors', value: total('legacy', 'visitors'), note: 'sum of daily' },
  { label: 'legacy plots', value: total('legacy', 'api_calls'), note: 'API calls, humans' },
  { label: 'bot requests', value: ['grugrutyp', 'legacy', 'home', 'menzerath', 'flux']
      .reduce((s, sec) => s + total(sec, 'bot_requests'), 0), note: 'excluded above' },
])

const queryTotals = computed(() => {
  const by = {}
  for (const q of data.value?.queries || []) {
    by[q.kind] ??= { kind: q.kind, n: 0, errors: 0 }
    by[q.kind].n += q.n
    by[q.kind].errors += q.errors
  }
  return Object.values(by).sort((a, b) => b.n - a.n)
})

function dayRange() {
  const out = []
  const start = new Date(`${data.value.since}T00:00:00Z`)
  const today = new Date()
  for (let d = start; d <= today; d = new Date(d.getTime() + 86400000)) {
    out.push(d.toISOString().slice(0, 10))
  }
  return out
}

function draw() {
  if (!canvas.value || !data.value) return
  const labels = dayRange()
  const lookup = {}
  for (const c of data.value.counts) {
    if (c.metric === 'visitors') lookup[`${c.section}|${c.day}`] = c.n
  }
  const datasets = SERIES.map((s) => ({
    label: s.label,
    data: labels.map((d) => lookup[`${s.section}|${d}`] ?? 0),
    borderColor: s.color,
    backgroundColor: s.color,
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.2,
  }))
  if (chart) chart.destroy()
  chart = new Chart(canvas.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { position: 'bottom' } },
    },
  })
}

async function load() {
  try {
    data.value = await admin.usage(days.value)
    await nextTick()
    draw()
  } catch (e) {
    emit('error', e.message || String(e))
  }
}

onMounted(load)
onBeforeUnmount(() => chart?.destroy())
</script>
