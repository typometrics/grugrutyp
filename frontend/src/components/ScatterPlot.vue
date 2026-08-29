<template>
  <div ref="wrapper" class="plot-wrapper" :style="wrapperStyle">
    <canvas ref="canvas" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Chart,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  Legend,
} from 'chart.js'

Chart.register(LinearScale, PointElement, ScatterController, Tooltip, Legend)

// Same antiqua as the rest of the page (quasar-variables.sass) -- the plot is the part
// of the interface that ends up in papers, so it is the last place to fall back to a
// system sans.
const SERIF = "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif"
Chart.defaults.font.family = SERIF

const props = defineProps({
  // [{ language, x, y, label, color, marker, n_scope, ci, sampled, escalated }]
  points: { type: Array, default: () => [] },
  xLabel: { type: String, default: 'X' },
  yLabel: { type: String, default: 'Y' },
  oneDimensional: { type: Boolean, default: false },
  // 'none' | 'optimal' (skip labels that would overlap one already drawn) | 'all'
  labelMode: { type: String, default: 'optimal' },
  showErrorBars: { type: Boolean, default: false },
  // The y = x line. Only meaningful in 2-D with both axes on the same scale, which the
  // parent is responsible for knowing; here it is just drawn when asked.
  showDiagonal: { type: Boolean, default: false },
  // Force a 1:1 plot area, so equal distances on both axes look equal.
  square: { type: Boolean, default: false },
  // A substring typed in the find-language box: matching points get rings and their
  // labels win every collision.
  highlight: { type: String, default: '' },
  // 1-D only: one row per colour group (the classic strip) or everything on one line.
  bands: { type: Boolean, default: true },
  // 1-D only: draw a kernel density estimate above the strip -- per band when banded
  // (half-violins), one overall curve otherwise.
  showDensity: { type: Boolean, default: false },
  // A ratio axis is pinned to 0-100; an aggregate is measured in words or nodes and has
  // to auto-scale, or every language lands in the bottom few percent of the chart.
  xPercent: { type: Boolean, default: true },
  yPercent: { type: Boolean, default: true },
})
const emit = defineEmits(['pick'])

const canvas = ref(null)
let chart = null

// A strip plot needs a row per family, and with ~25 families in the full corpus those rows
// have to be tall enough to hold a 6px marker and an 11px label without the neighbouring
// band's points reading as part of this one. The 2-D scatter just fills its container.
const bandCount = ref(0)
const wrapper = ref(null)

// ------------------------------------------------------------------ square chart area
//
// Fourth iteration, converged with Kim: full width stays -- legend and all -- and the
// wrapper GROWS TALLER until the chart area (the data region) is square; the plot pane
// scrolls if that exceeds the viewport. The plugin measures the area after each layout
// and adjusts the wrapper height; chart.js's resize observer relayouts, and the loop
// converges when the area is square within 2px.
const squareHeight = ref(0)

const wrapperStyle = computed(() => {
  if (props.oneDimensional) {
    // Ungrouped, the strip is one row and fits any viewport -- the banded layout is the
    // one that has to grow with ~25 families and scroll.
    return { minHeight: `${Math.max(420, bandCount.value * 38 + 90)}px` }
  }
  if (props.square && squareHeight.value) {
    return { height: `${squareHeight.value}px`, minHeight: '420px' }
  }
  return {}
})

const squareAreaPlugin = {
  id: 'squareArea',
  afterLayout(instance) {
    if (!props.square || props.oneDimensional) {
      squareHeight.value = 0
      return
    }
    const area = instance.chartArea
    const diff = Math.round(area.right - area.left - (area.bottom - area.top))
    if (Math.abs(diff) <= 2) return
    squareHeight.value = Math.max(420, instance.height + diff)
  },
}

/**
 * Language names next to their points.
 *
 * The current site does this and it is not decoration: a typological scatter is read by
 * asking "where is Japanese", and a plot that answers only on hover cannot be put in a
 * paper. Drawn by hand rather than pulling in chartjs-plugin-datalabels -- it is twenty
 * lines, and one fewer dependency in a page that has to keep working for years.
 *
 * In 'optimal' mode (the default) labels are skipped when they would overlap one already
 * drawn -- dropping a label beats an unreadable pile, and the point itself stays visible
 * either way. 'all' draws every label regardless, which is what the old site did and is
 * still the right mode for an export where the reader can zoom.
 */
const labelPlugin = {
  id: 'languageLabels',
  afterDatasetsDraw(instance) {
    const query = (props.highlight || '').trim().toLowerCase()
    if (props.labelMode === 'none' && !query) return
    const { ctx } = instance
    const drawn = []
    ctx.save()
    ctx.textBaseline = 'middle'

    // Collect every candidate first, highlighted ones ahead of the rest: a label the
    // user is actively searching for must win any collision, and must be drawn even in
    // 'none' mode.
    const candidates = []
    instance.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = instance.getDatasetMeta(datasetIndex)
      if (meta.hidden) return
      meta.data.forEach((element, index) => {
        const language = dataset.data[index]?.language
        if (!language) return
        const matched = !!query && language.toLowerCase().includes(query)
        if (props.labelMode === 'none' && !matched) return
        candidates.push({ element, matched, color: dataset.borderColor,
                          text: language.replace(/_/g, ' ') })
      })
    })
    candidates.sort((a, b) => Number(b.matched) - Number(a.matched))

    for (const { element, matched, color, text } of candidates) {
      ctx.font = `${matched ? 'bold ' : ''}11px ${SERIF}`
      const width = ctx.measureText(text).width
      const area = instance.chartArea
      // Draw to the left of the point when the label would otherwise run past the plot
      // area and into the legend -- which is exactly what happens to the languages at
      // 100%, and those are the ones a reader most wants named.
      const x = element.x + 6 + width > area.right ? element.x - 6 - width : element.x + 6
      const y = element.y
      const box = { left: x, right: x + width, top: y - 6, bottom: y + 6 }
      if (!matched && props.labelMode !== 'all') {
        const clash = drawn.some(
          (other) =>
            box.left < other.right &&
            box.right > other.left &&
            box.top < other.bottom &&
            box.bottom > other.top,
        )
        if (clash) continue
      }
      drawn.push(box)
      ctx.fillStyle = color
      ctx.fillText(text, x, y)
    }
    ctx.restore()
  },
}

/** Rings around the languages matching the find box -- two concentric accent circles,
 *  so a dot stays findable even inside a dense cluster. */
const highlightPlugin = {
  id: 'highlightRings',
  afterDatasetsDraw(instance) {
    const query = (props.highlight || '').trim().toLowerCase()
    if (!query) return
    const { ctx } = instance
    ctx.save()
    ctx.strokeStyle = '#d45500'
    instance.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = instance.getDatasetMeta(datasetIndex)
      if (meta.hidden) return
      dataset.data.forEach((point, index) => {
        if (!point.language?.toLowerCase().includes(query)) return
        const element = meta.data[index]
        if (!element) return
        ctx.lineWidth = 2.5
        ctx.beginPath()
        ctx.arc(element.x, element.y, 10, 0, 2 * Math.PI)
        ctx.stroke()
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.arc(element.x, element.y, 14, 0, 2 * Math.PI)
        ctx.stroke()
      })
    })
    ctx.restore()
  },
}

/** The y = x line, under everything else. Which side of it a language falls on is the
 *  question a two-measure scatter often exists to ask. */
const diagonalPlugin = {
  id: 'diagonal',
  beforeDatasetsDraw(instance) {
    if (!props.showDiagonal || props.oneDimensional) return
    const { ctx, scales } = instance
    const from = Math.max(scales.x.min, scales.y.min)
    const to = Math.min(scales.x.max, scales.y.max)
    if (from >= to) return
    ctx.save()
    ctx.strokeStyle = 'rgba(0,0,0,0.25)'
    ctx.lineWidth = 1
    ctx.setLineDash([5, 4])
    ctx.beginPath()
    ctx.moveTo(scales.x.getPixelForValue(from), scales.y.getPixelForValue(from))
    ctx.lineTo(scales.x.getPixelForValue(to), scales.y.getPixelForValue(to))
    ctx.stroke()
    ctx.restore()
  },
}

/** Gaussian KDE over `values`, evaluated on `steps` grid points, Silverman bandwidth. */
function kde(values, gridMin, gridMax, steps) {
  const n = values.length
  if (n < 2 || gridMin >= gridMax) return null
  const mean = values.reduce((a, b) => a + b, 0) / n
  const sd = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / n)
  const h = Math.max((gridMax - gridMin) / 200, 1.06 * (sd || 1) * n ** -0.2)
  const points = []
  let peak = 0
  for (let i = 0; i <= steps; i++) {
    const x = gridMin + (i / steps) * (gridMax - gridMin)
    let density = 0
    for (const value of values) {
      const z = (x - value) / h
      density += Math.exp(-0.5 * z * z)
    }
    density /= n * h * Math.sqrt(2 * Math.PI)
    points.push([x, density])
    peak = Math.max(peak, density)
  }
  return { points, peak }
}

/** Any CSS colour (the styles file uses names) to rgba at a given alpha. */
function withAlpha(ctx, color, alpha) {
  ctx.fillStyle = color // the canvas normalises names to #rrggbb
  const hex = ctx.fillStyle
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

/** 1-D density curves: half-violins per family band, or one overall curve when the
 *  strip is ungrouped. Screen aid, drawn under the points. */
const densityPlugin = {
  id: 'density',
  beforeDatasetsDraw(instance) {
    if (!props.oneDimensional || !props.showDensity) return
    const { ctx, scales } = instance

    const drawCurve = (values, base, rise, fill, stroke) => {
      const estimate = kde(values, scales.x.min, scales.x.max, 120)
      if (!estimate || !estimate.peak) return
      ctx.beginPath()
      estimate.points.forEach(([x, density], index) => {
        const px = scales.x.getPixelForValue(x)
        const py = scales.y.getPixelForValue(base + rise * (density / estimate.peak))
        if (index) ctx.lineTo(px, py)
        else ctx.moveTo(px, py)
      })
      const baseY = scales.y.getPixelForValue(base)
      ctx.lineTo(scales.x.getPixelForValue(scales.x.max), baseY)
      ctx.lineTo(scales.x.getPixelForValue(scales.x.min), baseY)
      ctx.closePath()
      ctx.fillStyle = fill
      ctx.fill()
      ctx.strokeStyle = stroke
      ctx.lineWidth = 1
      ctx.stroke()
    }

    ctx.save()
    if (props.bands) {
      instance.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = instance.getDatasetMeta(datasetIndex)
        if (meta.hidden) return
        drawCurve(
          dataset.data.map((point) => point.x),
          bandLabels.indexOf(dataset.label) + 0.25,
          0.65,
          withAlpha(ctx, dataset.borderColor, 0.13),
          withAlpha(ctx, dataset.borderColor, 0.45),
        )
      })
    } else {
      const values = []
      instance.data.datasets.forEach((dataset, datasetIndex) => {
        if (instance.getDatasetMeta(datasetIndex).hidden) return
        values.push(...dataset.data.map((point) => point.x))
      })
      drawCurve(values, 0.42, 0.5, 'rgba(20,61,20,0.10)', 'rgba(20,61,20,0.45)')
    }
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

// The family label of each band, by index. In 1-D the y axis is categorical, and without
// this the reader can see that two points sit on different rows but not what either row
// means -- the legend gives the colour, not the position.
let bandLabels = []

function buildDatasets() {
  // One dataset per family label: chart.js then gives us a working legend, and clicking a
  // family to hide it is exactly the interaction a typologist wants when Indo-European
  // covers everything else.
  const groups = new Map()
  for (const point of props.points) {
    if (!groups.has(point.label)) groups.set(point.label, [])
    groups.get(point.label).push(point)
  }

  const bands = props.bands ? [...groups.keys()].sort() : ['']
  bandLabels = bands
  bandCount.value = bands.length
  return [...groups.keys()].sort().map((label) => {
    const members = groups.get(label)
    return {
      label,
      borderColor: members[0].color,
      backgroundColor: members[0].color,
      pointStyle: members[0].marker,
      // A percent axis is pinned to 0-100, so a language at exactly 100 sits on the edge
      // of the chart area and its marker was drawn half-cut. Let points overflow; the
      // layout padding below gives them room before the canvas edge.
      clip: false,
      // Small while provisional (its language's treebanks are still arriving and the
      // point is still moving), full size once settled.
      pointRadius: members.map((point) => (point.provisional ? 3 : 6)),
      pointHoverRadius: 9,
      showLine: false,
      data: members.map((point, index) => ({
        // In 1-D the y coordinate carries no information, so it becomes a family band
        // with a little spread -- a strip plot. Points would otherwise sit on one line
        // and hide each other completely. Ungrouped, everything shares band 0 and gets
        // a wider spread, since ~190 languages share the line.
        x: point.x,
        y: props.oneDimensional
          ? props.bands
            ? bands.indexOf(label) + (index % 3) * 0.11 - 0.11
            : (index % 7) * 0.12 - 0.36
          : point.y,
        language: point.language,
        n_scope: point.n_scope,
        n_hit: point.n_hit,
        xCi: point.xCi,
        yCi: point.yCi,
        sampled: point.sampled,
        escalated: point.escalated,
        provisional: point.provisional,
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
    chart.options.scales.y.ticks.display = true
    chart.options.scales.x.min = props.xPercent ? 0 : undefined
    chart.options.scales.x.max = props.xPercent ? 100 : undefined
    chart.options.scales.y.min = props.oneDimensional ? -1 : props.yPercent ? 0 : undefined
    chart.options.scales.y.max = props.oneDimensional
      ? bandLabels.length
      : props.yPercent
        ? 100
        : undefined
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
      layout: { padding: { top: 10, right: 10, left: 4, bottom: 4 } },
      onClick(event, elements) {
        // In a dense cluster the default 'nearest' hit is whichever point sits on top --
        // which is exactly wrong while the user is ringing a language to click it. With
        // a find query active, the click snaps to the nearest MATCHING point within a
        // generous radius, occluded or not, direct hit or not.
        let chosen = elements.length
          ? { datasetIndex: elements[0].datasetIndex, index: elements[0].index }
          : null
        const query = (props.highlight || '').trim().toLowerCase()
        if (query) {
          let bestDistance = 24 ** 2 // px²
          chart.data.datasets.forEach((dataset, datasetIndex) => {
            const meta = chart.getDatasetMeta(datasetIndex)
            if (meta.hidden) return
            dataset.data.forEach((point, index) => {
              if (!point.language?.toLowerCase().includes(query)) return
              const element = meta.data[index]
              if (!element) return
              const distance = (element.x - event.x) ** 2 + (element.y - event.y) ** 2
              if (distance < bestDistance) {
                bestDistance = distance
                chosen = { datasetIndex, index }
              }
            })
          })
        }
        if (!chosen) return
        emit('pick', chart.data.datasets[chosen.datasetIndex].data[chosen.index])
      },
      scales: {
        x: {
          type: 'linear',
          min: props.xPercent ? 0 : undefined,
          max: props.xPercent ? 100 : undefined,
          title: { display: true, text: props.xLabel, padding: { top: 12 } },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
        y: {
          type: 'linear',
          min: props.oneDimensional ? -1 : props.yPercent ? 0 : undefined,
          max: props.oneDimensional ? undefined : props.yPercent ? 100 : undefined,
          title: { display: !props.oneDimensional, text: props.yLabel },
          ticks: {
            display: true,
            stepSize: props.oneDimensional ? 1 : undefined,
            // In 1-D the band index is the family; a bare "0, 1, 2" would be noise.
            callback: (value) =>
              props.oneDimensional
                ? (Number.isInteger(value) ? bandLabels[value] : '') ?? ''
                : value,
          },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
      },
      plugins: {
        // padding: vertical air between legend rows -- 25 families at the default 10px
        // read as one solid column.
        legend: { position: 'right', labels: { usePointStyle: true, boxWidth: 8, padding: 16 } },
        tooltip: {
          callbacks: {
            title: (items) => items[0].raw.language.replace(/_/g, ' '),
            label(item) {
              const point = item.raw
              const lines = [
                `${props.xLabel}: ${point.x.toFixed(2)}${props.xPercent ? '%' : ''}`,
              ]
              if (!props.oneDimensional) {
                lines.push(`${props.yLabel}: ${point.y.toFixed(2)}${props.yPercent ? '%' : ''}`)
              }
              lines.push(
                `${point.n_hit.toLocaleString()} of ${point.n_scope.toLocaleString()} matchings`,
              )
              if (point.xCi) {
                lines.push(`95%: ${point.xCi[0].toFixed(2)}–${point.xCi[1].toFixed(2)}`)
              }
              if (point.n_treebanks > 1) lines.push(`${point.n_treebanks} treebanks, summed`)
              if (point.provisional) {
                lines.push('provisional — more treebanks of this language still computing')
              }
              // Never let a sampled number pass as an exact one.
              if (point.escalated) lines.push('full corpus (escalated from a sample)')
              else if (point.sampled) lines.push('sampled')
              return lines
            },
          },
        },
      },
    },
    plugins: [squareAreaPlugin, densityPlugin, labelPlugin, errorBarPlugin, diagonalPlugin, highlightPlugin],
  })
}

onMounted(render)
watch(
  () => props.square,
  () => chart && chart.update('none'), // afterLayout applies or clears the extra padding
)
watch(
  () => [props.points, props.xLabel, props.yLabel, props.oneDimensional, props.bands],
  render,
  { deep: true },
)
watch(
  () => [props.labelMode, props.showErrorBars, props.showDiagonal, props.highlight,
         props.showDensity],
  () => chart && chart.update('none'),
)
onBeforeUnmount(() => chart && chart.destroy())

// ------------------------------------------------------------------ vector export
//
// Chart.js renders to a canvas and has no SVG backend, and the usual answer (a canvas2svg
// shim fed to a second chart) is a dependency fighting chart.js internals. There is no
// need for either: everything on the plot -- scales, elements, legend -- is readable off
// the live chart instance, so the exporter re-emits exactly the figure on screen as SVG.
// If the two ever disagree, the exporter is wrong by definition.

const escapeXml = (text) =>
  String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const svgText = (x, y, text, { size = 11, fill = '#666', anchor = 'start', rotate = 0 } = {}) =>
  `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${size}" fill="${fill}"` +
  ` text-anchor="${anchor}" dominant-baseline="middle"` +
  (rotate ? ` transform="rotate(${rotate} ${x.toFixed(1)} ${y.toFixed(1)})"` : '') +
  `>${escapeXml(text)}</text>`

/** One marker, matching chart.js's pointStyle vocabulary closely enough for print. */
function svgMarker(style, x, y, r, color) {
  const stroke = `stroke="${color}" stroke-width="2" fill="none"`
  switch (style) {
    case 'triangle': {
      const h = r * 1.2
      return `<polygon points="${x},${y - h} ${x - h},${y + h * 0.8} ${x + h},${y + h * 0.8}" fill="${color}"/>`
    }
    case 'rect':
      return `<rect x="${x - r * 0.9}" y="${y - r * 0.9}" width="${r * 1.8}" height="${r * 1.8}" fill="${color}"/>`
    case 'rectRot':
      return `<polygon points="${x},${y - r * 1.2} ${x + r * 1.2},${y} ${x},${y + r * 1.2} ${x - r * 1.2},${y}" fill="${color}"/>`
    case 'cross':
      return `<path d="M ${x - r} ${y} H ${x + r} M ${x} ${y - r} V ${y + r}" ${stroke}/>`
    case 'crossRot': {
      const d = r * 0.71
      return `<path d="M ${x - d} ${y - d} L ${x + d} ${y + d} M ${x - d} ${y + d} L ${x + d} ${y - d}" ${stroke}/>`
    }
    case 'star': {
      const d = r * 0.71
      return (
        `<path d="M ${x - r} ${y} H ${x + r} M ${x} ${y - r} V ${y + r}` +
        ` M ${x - d} ${y - d} L ${x + d} ${y + d} M ${x - d} ${y + d} L ${x + d} ${y - d}" ${stroke}/>`
      )
    }
    case 'line':
    case 'dash':
      return `<path d="M ${x - r} ${y} H ${x + r}" ${stroke}/>`
    default:
      return `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}"/>`
  }
}

function toSvg() {
  if (!chart) return null
  const { width: W, height: H, chartArea: area, scales, ctx } = chart
  const out = []
  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"` +
      ` viewBox="0 0 ${W} ${H}" font-family="Palatino, 'Book Antiqua', Georgia, serif">`,
    `<rect width="${W}" height="${H}" fill="white"/>`,
  )

  // Grid and tick labels, straight from the live scales.
  for (const tick of scales.x.ticks) {
    const px = scales.x.getPixelForValue(tick.value)
    out.push(
      `<line x1="${px.toFixed(1)}" y1="${area.top}" x2="${px.toFixed(1)}" y2="${area.bottom}" stroke="rgba(0,0,0,0.06)"/>`,
      svgText(px, area.bottom + 14, tick.label, { anchor: 'middle' }),
    )
  }
  for (const tick of scales.y.ticks) {
    if (tick.label === '' || tick.label == null) continue
    const py = scales.y.getPixelForValue(tick.value)
    out.push(
      `<line x1="${area.left}" y1="${py.toFixed(1)}" x2="${area.right}" y2="${py.toFixed(1)}" stroke="rgba(0,0,0,0.06)"/>`,
      svgText(area.left - 8, py, tick.label, { anchor: 'end' }),
    )
  }
  out.push(
    `<line x1="${area.left}" y1="${area.bottom}" x2="${area.right}" y2="${area.bottom}" stroke="#999"/>`,
    `<line x1="${area.left}" y1="${area.top}" x2="${area.left}" y2="${area.bottom}" stroke="#999"/>`,
  )
  if (props.xLabel) {
    out.push(
      svgText((area.left + area.right) / 2, area.bottom + 34, props.xLabel, {
        anchor: 'middle', size: 12, fill: '#444',
      }),
    )
  }
  if (props.yLabel && !props.oneDimensional) {
    out.push(
      svgText(14, (area.top + area.bottom) / 2, props.yLabel, {
        anchor: 'middle', size: 12, fill: '#444', rotate: -90,
      }),
    )
  }

  if (props.showDiagonal && !props.oneDimensional) {
    const from = Math.max(scales.x.min, scales.y.min)
    const to = Math.min(scales.x.max, scales.y.max)
    if (from < to) {
      out.push(
        `<line x1="${scales.x.getPixelForValue(from)}" y1="${scales.y.getPixelForValue(from)}"` +
          ` x2="${scales.x.getPixelForValue(to)}" y2="${scales.y.getPixelForValue(to)}"` +
          ` stroke="rgba(0,0,0,0.25)" stroke-dasharray="5 4"/>`,
      )
    }
  }

  // Points, error bars and labels, with the same collision rule the canvas uses.
  const drawn = []
  ctx.save()
  ctx.font = `11px ${SERIF}`
  chart.data.datasets.forEach((dataset, datasetIndex) => {
    const meta = chart.getDatasetMeta(datasetIndex)
    if (meta.hidden) return
    dataset.data.forEach((point, index) => {
      const element = meta.data[index]
      if (!element) return
      if (props.showErrorBars && point.xCi) {
        out.push(
          `<line x1="${scales.x.getPixelForValue(point.xCi[0]).toFixed(1)}" y1="${element.y.toFixed(1)}"` +
            ` x2="${scales.x.getPixelForValue(point.xCi[1]).toFixed(1)}" y2="${element.y.toFixed(1)}"` +
            ` stroke="${dataset.borderColor}" stroke-opacity="0.35"/>`,
        )
      }
      if (props.showErrorBars && point.yCi && !props.oneDimensional) {
        out.push(
          `<line x1="${element.x.toFixed(1)}" y1="${scales.y.getPixelForValue(point.yCi[0]).toFixed(1)}"` +
            ` x2="${element.x.toFixed(1)}" y2="${scales.y.getPixelForValue(point.yCi[1]).toFixed(1)}"` +
            ` stroke="${dataset.borderColor}" stroke-opacity="0.35"/>`,
        )
      }
      const radius = Array.isArray(dataset.pointRadius)
        ? dataset.pointRadius[index]
        : dataset.pointRadius
      out.push(svgMarker(dataset.pointStyle, element.x, element.y, radius, dataset.borderColor))

      if (props.labelMode === 'none') return
      const text = point.language?.replace(/_/g, ' ')
      if (!text) return
      const width = ctx.measureText(text).width
      const lx = element.x + 6 + width > area.right ? element.x - 6 - width : element.x + 6
      const box = { left: lx, right: lx + width, top: element.y - 6, bottom: element.y + 6 }
      if (props.labelMode !== 'all') {
        const clash = drawn.some(
          (other) =>
            box.left < other.right && box.right > other.left &&
            box.top < other.bottom && box.bottom > other.top,
        )
        if (clash) return
      }
      drawn.push(box)
      out.push(svgText(lx, element.y, text, { fill: dataset.borderColor }))
    })
  })
  ctx.restore()

  // Legend column, right of the plot area, where chart.js reserved the space for it.
  let legendY = (chart.legend?.top ?? area.top) + 14
  const legendX = (chart.legend?.left ?? area.right) + 12
  for (const item of chart.legend?.legendItems ?? []) {
    if (item.hidden) continue
    out.push(
      svgMarker(item.pointStyle, legendX, legendY, 4, item.strokeStyle || item.fillStyle),
      svgText(legendX + 10, legendY, item.text, { fill: '#444' }),
    )
    legendY += 17
  }

  out.push('</svg>')
  return out.join('\n')
}

defineExpose({
  toPng: () => (chart ? chart.toBase64Image('image/png', 1) : null),
  toSvg,
})
</script>

<style scoped>
.plot-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 420px;
  /* Always light, even in dark mode: the chart is a figure, and keeping it on white
     means the PNG/SVG exports are identical whatever theme the viewer uses. */
  background: #fff;
  border-radius: 4px;
}
</style>
