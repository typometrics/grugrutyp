<template>
  <div class="plot-wrapper">
    <canvas ref="canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Chart,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  Legend,
} from 'chart.js'

Chart.register(LinearScale, PointElement, ScatterController, Tooltip, Legend)

const props = defineProps({
  // [{ language, x, y, label, color, marker, n_scope, ci, sampled, escalated }]
  points: { type: Array, default: () => [] },
  xLabel: { type: String, default: 'X' },
  yLabel: { type: String, default: 'Y' },
  oneDimensional: { type: Boolean, default: false },
  showLabels: { type: Boolean, default: true },
  showErrorBars: { type: Boolean, default: false },
})
const emit = defineEmits(['pick'])

const canvas = ref(null)
let chart = null

/**
 * Language names next to their points.
 *
 * The current site does this and it is not decoration: a typological scatter is read by
 * asking "where is Japanese", and a plot that answers only on hover cannot be put in a
 * paper. Drawn by hand rather than pulling in chartjs-plugin-datalabels -- it is twenty
 * lines, and one fewer dependency in a page that has to keep working for years.
 *
 * Labels are skipped when they would overlap one already drawn. Dropping a label is
 * better than an unreadable pile, and the point itself stays visible either way.
 */
const labelPlugin = {
  id: 'languageLabels',
  afterDatasetsDraw(instance) {
    if (!props.showLabels) return
    const { ctx } = instance
    const drawn = []
    ctx.save()
    ctx.font = '11px system-ui, sans-serif'
    ctx.textBaseline = 'middle'

    instance.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = instance.getDatasetMeta(datasetIndex)
      if (meta.hidden) return
      meta.data.forEach((element, index) => {
        const text = dataset.data[index]?.language?.replace(/_/g, ' ')
        if (!text) return
        const x = element.x + 6
        const y = element.y
        const width = ctx.measureText(text).width
        const box = { left: x, right: x + width, top: y - 6, bottom: y + 6 }
        const clash = drawn.some(
          (other) =>
            box.left < other.right &&
            box.right > other.left &&
            box.top < other.bottom &&
            box.bottom > other.top,
        )
        if (clash) return
        drawn.push(box)
        ctx.fillStyle = dataset.borderColor
        ctx.fillText(text, x, y)
      })
    })
    ctx.restore()
  },
}

/** 95% Wilson whiskers, drawn under the points. */
const errorBarPlugin = {
  id: 'errorBars',
  beforeDatasetsDraw(instance) {
    if (!props.showErrorBars) return
    const { ctx, scales } = instance
    ctx.save()
    ctx.lineWidth = 1
    instance.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = instance.getDatasetMeta(datasetIndex)
      if (meta.hidden) return
      ctx.strokeStyle = dataset.borderColor
      ctx.globalAlpha = 0.35
      dataset.data.forEach((point, index) => {
        const element = meta.data[index]
        if (!element) return
        if (point.xCi) {
          ctx.beginPath()
          ctx.moveTo(scales.x.getPixelForValue(point.xCi[0]), element.y)
          ctx.lineTo(scales.x.getPixelForValue(point.xCi[1]), element.y)
          ctx.stroke()
        }
        if (point.yCi && !props.oneDimensional) {
          ctx.beginPath()
          ctx.moveTo(element.x, scales.y.getPixelForValue(point.yCi[0]))
          ctx.lineTo(element.x, scales.y.getPixelForValue(point.yCi[1]))
          ctx.stroke()
        }
      })
    })
    ctx.restore()
  },
}

function buildDatasets() {
  // One dataset per family label: chart.js then gives us a working legend, and clicking a
  // family to hide it is exactly the interaction a typologist wants when Indo-European
  // covers everything else.
  const groups = new Map()
  for (const point of props.points) {
    if (!groups.has(point.label)) groups.set(point.label, [])
    groups.get(point.label).push(point)
  }

  const bands = [...groups.keys()].sort()
  return bands.map((label) => {
    const members = groups.get(label)
    return {
      label,
      borderColor: members[0].color,
      backgroundColor: members[0].color,
      pointStyle: members[0].marker,
      pointRadius: 6,
      pointHoverRadius: 9,
      showLine: false,
      data: members.map((point, index) => ({
        // In 1-D the y coordinate carries no information, so it becomes a family band
        // with a little spread -- a strip plot. Points would otherwise sit on one line
        // and hide each other completely.
        x: point.x,
        y: props.oneDimensional ? bands.indexOf(label) + (index % 5) * 0.12 - 0.24 : point.y,
        language: point.language,
        n_scope: point.n_scope,
        n_hit: point.n_hit,
        xCi: point.xCi,
        yCi: point.yCi,
        sampled: point.sampled,
        escalated: point.escalated,
        n_treebanks: point.n_treebanks,
      })),
    }
  })
}

function render() {
  if (!canvas.value) return
  const datasets = buildDatasets()

  if (chart) {
    chart.data.datasets = datasets
    chart.options.scales.x.title.text = props.xLabel
    chart.options.scales.y.title.text = props.oneDimensional ? '' : props.yLabel
    chart.options.scales.y.ticks.display = !props.oneDimensional
    chart.update('none') // 'none': the plot fills in as SSE lands, and animating each
    return // arrival makes 700 points look like a lava lamp
  }

  chart = new Chart(canvas.value, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      onClick(event, elements) {
        if (!elements.length) return
        const { datasetIndex, index } = elements[0]
        emit('pick', chart.data.datasets[datasetIndex].data[index])
      },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: 100,
          title: { display: true, text: props.xLabel },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
        y: {
          type: 'linear',
          min: props.oneDimensional ? -1 : 0,
          max: props.oneDimensional ? undefined : 100,
          title: { display: !props.oneDimensional, text: props.yLabel },
          ticks: { display: !props.oneDimensional },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
      },
      plugins: {
        legend: { position: 'right', labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: {
          callbacks: {
            title: (items) => items[0].raw.language.replace(/_/g, ' '),
            label(item) {
              const point = item.raw
              const lines = [`${props.xLabel}: ${point.x.toFixed(2)}%`]
              if (!props.oneDimensional) lines.push(`${props.yLabel}: ${point.y.toFixed(2)}%`)
              lines.push(
                `${point.n_hit.toLocaleString()} of ${point.n_scope.toLocaleString()} matchings`,
              )
              if (point.xCi) {
                lines.push(`95%: ${point.xCi[0].toFixed(2)}–${point.xCi[1].toFixed(2)}`)
              }
              if (point.n_treebanks > 1) lines.push(`${point.n_treebanks} treebanks, summed`)
              // Never let a sampled number pass as an exact one.
              if (point.escalated) lines.push('full corpus (escalated from a sample)')
              else if (point.sampled) lines.push('sampled')
              return lines
            },
          },
        },
      },
    },
    plugins: [labelPlugin, errorBarPlugin],
  })
}

onMounted(render)
watch(
  () => [props.points, props.xLabel, props.yLabel, props.oneDimensional],
  render,
  { deep: true },
)
watch(
  () => [props.showLabels, props.showErrorBars],
  () => chart && chart.update('none'),
)
onBeforeUnmount(() => chart && chart.destroy())

defineExpose({
  toPng: () => (chart ? chart.toBase64Image('image/png', 1) : null),
})
</script>

<style scoped>
.plot-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 420px;
}
</style>
