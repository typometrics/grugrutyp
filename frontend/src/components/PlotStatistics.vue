<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="stats-card">
      <q-card-section class="row items-center q-pb-none">
        <q-icon name="query_stats" size="20px" class="q-mr-sm" />
        <div class="text-subtitle1">Statistics on this plot</div>
        <q-space />
        <q-btn v-close-popup flat dense round icon="close" />
      </q-card-section>

      <q-card-section v-if="!stats" class="text-grey-7">
        Statistics need at least three plotted languages, both axes, and some variation
        on each of them.
      </q-card-section>

      <template v-else>
        <q-card-section class="q-pt-sm">
          <div class="text-caption text-grey-7 q-mb-xs">
            {{ stats.n }} languages · X = {{ xLabel }} · Y = {{ yLabel }}
          </div>
          <table class="stats-table">
            <thead>
              <tr><th></th><th>mean</th><th>median</th><th>sd</th></tr>
            </thead>
            <tbody>
              <tr>
                <th>X</th><td>{{ round2(stats.x.mean) }}</td>
                <td>{{ round2(stats.x.median) }}</td><td>{{ round2(stats.x.sd) }}</td>
              </tr>
              <tr>
                <th>Y</th><td>{{ round2(stats.y.mean) }}</td>
                <td>{{ round2(stats.y.median) }}</td><td>{{ round2(stats.y.sd) }}</td>
              </tr>
            </tbody>
          </table>

          <div class="q-mt-md stat-line">
            <b>Pearson r = {{ round3(stats.pearson.r) }}</b> ({{ pFormat(stats.pearson.p) }})
            — <b>Spearman ρ = {{ round3(stats.spearman.rho) }}</b>
            ({{ pFormat(stats.spearman.p) }})
          </div>
          <div class="stat-line">
            <b>Regression:</b> Y ≈ {{ round2(stats.regression.intercept) }}
            {{ stats.regression.slope < 0 ? '−' : '+' }}
            {{ round3(Math.abs(stats.regression.slope)) }}·X,
            R² = {{ round3(stats.regression.r2) }}
          </div>
          <q-checkbox
            :model-value="showLine" dense size="sm" class="q-mt-xs"
            label="draw the regression line on the plot"
            @update:model-value="emit('update:showLine', $event)"
          />

          <div v-if="stats.quadrants.used >= 12" class="q-mt-md">
            <div class="text-caption text-grey-7">
              Median split ({{ round2(stats.quadrants.mx) }}, {{ round2(stats.quadrants.my) }})
              — each corner would hold ~{{ Math.round(stats.quadrants.used / 4) }} languages
              under independence:
            </div>
            <table class="stats-table q-mt-xs">
              <tbody>
                <tr>
                  <th>low X · high Y: {{ stats.quadrants.counts.lh }}</th>
                  <th>high X · high Y: {{ stats.quadrants.counts.hh }}</th>
                </tr>
                <tr>
                  <th>low X · low Y: {{ stats.quadrants.counts.ll }}</th>
                  <th>high X · low Y: {{ stats.quadrants.counts.hl }}</th>
                </tr>
              </tbody>
            </table>
            <div v-if="emptyCorner" class="stat-line q-mt-xs">
              The <b>{{ emptyCorner.name }}</b> corner is (nearly) empty —
              {{ emptyCorner.reading }}
            </div>
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section class="stats-bricks">
          <p>
            <b>r</b> measures straight-line association, −1…+1. <b>ρ</b> only asks
            whether the languages are ordered the same way on both axes — closer to what
            an implicational claim says, and indifferent to outliers. <b>R²</b> is the
            share of the variance in Y that a straight line on X accounts for; the slope
            reads "one more point of X goes with
            {{ stats ? round3(stats.regression.slope) : 'b' }} points of Y" — descriptive,
            not causal.
          </p>
          <p>
            An empty corner in the median split is the signature of a <b>one-way
            implication</b> ("languages high on X are high on Y, but not the reverse") —
            a shape a symmetric correlation coefficient cannot distinguish from a plain
            linear trend.
          </p>
          <p class="caveat">
            <b>The caveat that matters:</b> languages are not independent samples —
            related languages inherit their patterns together (Galton's problem). Each
            language counts once here, whatever its corpus size, but the p-values assume
            independence and are therefore optimistic. Before reading a trend as a
            universal, check that it also holds <i>within</i> families — click families
            in the legend to isolate them.
          </p>
        </q-card-section>
      </template>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // the scatterStats() bundle, or null when it cannot be computed
  stats: { type: Object, default: null },
  xLabel: { type: String, default: 'X' },
  yLabel: { type: String, default: 'Y' },
  // whether the regression line is currently drawn on the plot
  showLine: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'update:showLine'])

const round2 = (value) => value.toFixed(2)
const round3 = (value) => value.toFixed(3)
// Below 0.001 the exact figure is noise (and the independence assumption is doing more
// work than the data); above it, two significant digits.
const pFormat = (p) =>
  p == null ? '' : p < 0.001 ? 'p < 0.001' : `p = ${p.toPrecision(2)}`

const CORNERS = {
  hl: ['high X · low Y', 'read: high X implies high Y (but high Y allows low X).'],
  lh: ['low X · high Y', 'read: high Y implies high X (but high X allows low Y).'],
  ll: ['low X · low Y', 'read: every language is high on at least one of the two.'],
  hh: ['high X · high Y', 'read: the two highs exclude each other.'],
}

/** The emptiest corner, but only when it is genuinely empty: at most one language, or
 *  under 5% of the split where a quarter is expected. */
const emptyCorner = computed(() => {
  if (!props.stats) return null
  const { counts, used } = props.stats.quadrants
  if (used < 12) return null
  const [corner, count] = Object.entries(counts).sort((a, b) => a[1] - b[1])[0]
  if (count > Math.max(1, 0.05 * used)) return null
  const [name, reading] = CORNERS[corner]
  return { name, reading }
})
</script>

<style scoped>
.stats-card {
  width: 480px;
  max-width: 92vw;
}
.stats-table {
  border-collapse: collapse;
  font-size: 13px;
}
.stats-table th,
.stats-table td {
  border: 1px solid rgba(128, 128, 128, 0.35);
  padding: 3px 10px;
  text-align: right;
  font-weight: normal;
}
.stats-table thead th {
  color: #777;
}
.stat-line {
  font-size: 13px;
  line-height: 1.5;
}
.stats-bricks {
  font-size: 12.5px;
  line-height: 1.55;
  color: #555;
}
.body--dark .stats-bricks {
  color: #b5b5b5;
}
.stats-bricks p {
  margin-bottom: 8px;
}
.stats-bricks .caveat {
  margin-bottom: 0;
}
</style>
