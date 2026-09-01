<template>
  <div class="q-pa-md admin-page">
    <!-- ------------------------------------------------------------------ token gate -->
    <q-card v-if="!authed" flat bordered class="q-mx-auto q-mt-xl" style="max-width: 440px">
      <q-card-section>
        <div class="text-h6 q-mb-sm">Admin</div>
        <p class="text-caption text-grey-7">
          The token is <code>GRUGRUTYP_ADMIN_TOKEN</code> in the server's
          <code>.env</code>. It stays in this browser.
        </p>
        <q-input
          v-model="tokenInput" dense outlined type="password" label="admin token"
          @keyup.enter="tryToken"
        />
        <q-banner v-if="tokenError" dense class="bg-red-1 text-red-9 q-mt-sm">
          {{ tokenError }}
        </q-banner>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn unelevated no-caps color="primary" label="unlock" :loading="tokenTrying"
               @click="tryToken" />
      </q-card-actions>
    </q-card>

    <template v-else>
      <div class="row items-center q-mb-sm">
        <q-tabs
          v-model="section" dense no-caps align="left"
          active-color="primary" indicator-color="accent"
        >
          <q-tab name="audit" label="Release audit" />
          <q-tab name="languages" label="Languages" />
          <q-tab name="appearance" label="Appearance" />
          <q-tab name="users" label="Users" />
          <q-tab name="queries" label="Query log" />
        </q-tabs>
        <q-space />
        <q-btn flat dense no-caps icon="logout" label="forget token" @click="logout" />
      </div>

      <q-banner v-if="error" dense class="bg-red-1 text-red-9 q-mb-sm">
        <template #avatar><q-icon name="error_outline" /></template>
        {{ error }}
      </q-banner>

      <!-- ------------------------------------------------------------- release audit -->
      <div v-if="section === 'audit'">
        <q-banner v-if="audit && audit.clean" dense class="bg-green-1 text-green-9">
          <template #avatar><q-icon name="check_circle_outline" /></template>
          The configuration is clean for {{ audit.version }}: every language in the
          database has a row, a grouping and a colour.
        </q-banner>

        <template v-if="audit && !audit.clean">
          <div v-if="audit.renames.length" class="q-mb-md">
            <div class="text-subtitle2">
              Probable renames — confirm to carry the old row's curation over
            </div>
            <q-list dense bordered class="rounded-borders">
              <q-item v-for="entry in audit.renames" :key="entry.language">
                <q-item-section>
                  <b>{{ entry.language }}</b>&nbsp;← {{ entry.was }}
                  <span class="text-caption text-grey-7">
                    ({{ entry.via }}, confidence {{ entry.confidence }})
                  </span>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    dense unelevated size="sm" no-caps color="primary" label="confirm rename"
                    @click="editRename(entry)"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </div>

          <div v-if="unpairedUnconfigured.length" class="q-mb-md">
            <div class="text-subtitle2">Unconfigured — these plot grey until classified</div>
            <q-list dense bordered class="rounded-borders">
              <q-item v-for="name in unpairedUnconfigured" :key="name">
                <q-item-section>{{ name }}</q-item-section>
                <q-item-section side>
                  <q-btn
                    dense unelevated size="sm" no-caps color="primary" label="classify"
                    @click="editLanguage({ language: name })"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </div>

          <div v-if="audit.unstyled.length" class="q-mb-md">
            <div class="text-subtitle2">Labels with no colour (they walk up or go grey)</div>
            <q-chip
              v-for="label in audit.unstyled" :key="label" dense clickable
              @click="editAppearance({ group: label })"
            >
              {{ label }}
            </q-chip>
          </div>

          <div v-if="audit.incomplete.length" class="q-mb-md">
            <div class="text-subtitle2">Rows with empty groupings</div>
            <q-chip
              v-for="name in audit.incomplete" :key="name" dense clickable
              @click="editExistingLanguage(name)"
            >
              {{ name }}
            </q-chip>
          </div>
        </template>

        <div v-if="audit" class="text-caption text-grey-7 q-mt-sm">
          {{ audit.orphaned.length }} configured languages are not in this release; their
          rows are kept on purpose — a language dropped from one release often returns.
        </div>
      </div>

      <!-- ----------------------------------------------------------- languages table -->
      <div v-if="section === 'languages'">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-input v-model="languageFilter" dense outlined clearable placeholder="filter"
                   style="width: 200px" />
          <q-btn dense unelevated no-caps color="primary" icon="add" label="add language"
                 @click="editLanguage({})" />
          <span class="text-caption text-grey-7">
            {{ filteredLanguages.length }} of {{ languageRows.length }} rows — every save
            is one git commit on <code>languages.tsv</code>
          </span>
        </div>
        <q-markup-table dense flat bordered class="config-table">
          <thead>
            <tr>
              <th v-for="column in languageColumns" :key="column" class="text-left">
                {{ column.replace(/_/g, ' ') }}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredLanguages" :key="row.language">
              <td v-for="column in languageColumns" :key="column">{{ row[column] }}</td>
              <td>
                <q-btn flat dense size="sm" icon="edit" @click="editLanguage({ ...row })" />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </div>

      <!-- ---------------------------------------------------------- appearance table -->
      <div v-if="section === 'appearance'">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-btn dense unelevated no-caps color="primary" icon="add" label="add group"
                 @click="editAppearance({})" />
          <span class="text-caption text-grey-7">
            group label → colour and marker; fine labels without a row inherit their
            parent grouping's style
          </span>
        </div>
        <q-markup-table dense flat bordered class="config-table" style="max-width: 480px">
          <thead>
            <tr><th class="text-left">group</th><th class="text-left">colour</th>
                <th class="text-left">marker</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="row in appearanceRows" :key="row.group">
              <td>{{ row.group }}</td>
              <td>
                <span class="swatch" :style="{ background: row.color }" /> {{ row.color }}
              </td>
              <td>{{ MARKER_GLYPHS[row.marker] || '' }} {{ row.marker }}</td>
              <td>
                <q-btn flat dense size="sm" icon="edit" @click="editAppearance({ ...row })" />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </div>

      <!-- ------------------------------------------------------------------- users -->
      <div v-if="section === 'users'">
        <div class="text-caption text-grey-7 q-mb-sm">
          Accounts arrive by OAuth sign-in (Google / GitHub / ORCID) — nothing to create
          here. Two flags per person: <b>admin</b> opens this page without the token;
          <b>LLM access</b> is the allowlist for the plain-text→Grew feature, the one
          thing that spends money per use.
        </div>
        <q-markup-table dense flat bordered>
          <thead>
            <tr>
              <th class="text-left">name</th><th class="text-left">via</th>
              <th class="text-left">email</th><th class="text-left">last login</th>
              <th>admin</th><th>LLM access</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in userRows" :key="account.id">
              <td>{{ account.name || '—' }}</td>
              <td>{{ account.provider }} · {{ account.subject }}</td>
              <td>{{ account.email || '—' }}</td>
              <td>{{ account.last_login.slice(0, 16).replace('T', ' ') }}</td>
              <td class="text-center">
                <q-toggle
                  :model-value="account.is_admin" dense
                  @update:model-value="(v) => setUserFlag(account, 'is_admin', v)"
                />
              </td>
              <td class="text-center">
                <q-toggle
                  :model-value="account.llm_allowed" dense color="accent"
                  @update:model-value="(v) => setUserFlag(account, 'llm_allowed', v)"
                />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
        <div v-if="!userRows.length" class="text-caption text-grey-7 q-mt-sm">
          nobody has signed in yet
        </div>
      </div>

      <!-- --------------------------------------------------------------- query log -->
      <div v-if="section === 'queries'">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-btn-toggle
            v-model="queryKind" dense no-caps unelevated toggle-color="primary"
            :options="[{ label: 'all', value: '' }, { label: 'measures', value: 'measure' },
                       { label: 'searches', value: 'search' }]"
            @update:model-value="loadQueries"
          />
          <q-btn flat dense no-caps icon="refresh" label="refresh" @click="loadQueries" />
          <span v-if="queryStats" class="text-caption text-grey-7">
            {{ queryStats.total }} logged ({{ queryStats.errors }} failed) —
            no IPs, no users, {{ '' }}pruned after 180 days
          </span>
        </div>
        <q-list dense bordered separator class="rounded-borders">
          <q-expansion-item
            v-for="entry in queryRows" :key="entry.id" dense expand-separator
          >
            <template #header>
              <q-item-section>
                <div class="row items-center q-gutter-xs no-wrap query-header">
                  <q-badge :color="entry.error ? 'red-7' : entry.kind === 'measure' ? 'primary' : 'teal-7'">
                    {{ entry.kind }}
                  </q-badge>
                  <span class="text-caption text-grey-7">{{ entry.ts }}</span>
                  <span class="text-caption">{{ entry.scheme }}</span>
                  <span class="text-caption text-grey-7 ellipsis">{{ entry.target }}</span>
                  <q-space />
                  <span v-if="entry.seconds != null" class="text-caption">
                    {{ entry.seconds.toFixed(1) }}s
                  </span>
                  <span v-if="entry.results != null" class="text-caption text-grey-7">
                    {{ entry.results }} results
                  </span>
                  <span v-if="entry.cached" class="text-caption text-grey-7">
                    {{ entry.cached }} cached
                  </span>
                </div>
              </q-item-section>
            </template>
            <div class="q-px-md q-pb-sm">
              <pre class="grew-snippet query-text">{{ entry.query }}</pre>
              <div v-if="entry.error" class="text-caption text-red-8">{{ entry.error }}</div>
            </div>
          </q-expansion-item>
        </q-list>
        <div v-if="!queryRows.length" class="text-caption text-grey-7 q-mt-sm">
          nothing logged yet
        </div>
      </div>
    </template>

    <!-- ------------------------------------------------------- language edit dialog -->
    <q-dialog v-model="languageDialog">
      <q-card style="min-width: 420px">
        <q-card-section>
          <div class="text-h6">
            {{ languageEdit.original_language ? 'Confirm rename' : languageEdit._new ? 'New language' : 'Edit language' }}
          </div>
          <div v-if="languageEdit.original_language" class="text-caption text-grey-7">
            {{ languageEdit.original_language }} → {{ languageEdit.language }} — the row
            keeps its curation under the new name
          </div>
        </q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-input v-model="languageEdit.language" dense outlined label="language"
                   :readonly="!languageEdit._new && !languageEdit.original_language" />
          <div class="row q-col-gutter-sm">
            <div v-for="column in ['group', 'genus', 'subgenus', 'simple_group', 'area', 'typology', 'lcode']"
                 :key="column" class="col-6">
              <q-input v-model="languageEdit[column]" dense outlined
                       :label="column.replace(/_/g, ' ')" />
            </div>
          </div>
          <div class="text-caption text-grey-7">
            Model a new language on a configured sibling — groupings are curation
            decisions (docs/language-config.md).
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="save & commit" :loading="saving"
                 @click="saveLanguage" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ------------------------------------------------------ appearance edit dialog -->
    <q-dialog v-model="appearanceDialog">
      <q-card style="min-width: 380px">
        <q-card-section>
          <div class="text-h6">{{ appearanceEdit._new ? 'New group style' : 'Edit group style' }}</div>
        </q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-input v-model="appearanceEdit.group" dense outlined label="group label"
                   :readonly="!appearanceEdit._new" />
          <q-input v-model="appearanceEdit.color" dense outlined label="colour">
            <template #prepend>
              <span class="swatch" :style="{ background: appearanceEdit.color }" />
            </template>
            <template #append>
              <q-icon name="colorize" class="cursor-pointer">
                <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                  <q-color v-model="appearanceEdit.color" no-header-tabs format-model="hex" />
                </q-popup-proxy>
              </q-icon>
            </template>
          </q-input>
          <q-select
            v-model="appearanceEdit.marker" dense outlined label="marker" emit-value map-options
            :options="MARKERS.map((m) => ({ label: `${MARKER_GLYPHS[m]} ${m}`, value: m }))"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="save & commit" :loading="saving"
                 @click="saveAppearance" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { api, admin } from '../api'

const $q = useQuasar()

const MARKERS = ['circle', 'triangle', 'rect', 'rectRot', 'cross', 'crossRot', 'star', 'line', 'dash']
const MARKER_GLYPHS = {
  circle: '●', triangle: '▲', rect: '■', rectRot: '◆',
  cross: '✚', crossRot: '✖', star: '✳', line: '▬', dash: '╌',
}

const authed = ref(false)
const tokenInput = ref('')
const tokenError = ref('')
const tokenTrying = ref(false)
const section = ref('audit')
const error = ref('')

const audit = ref(null)
const languageColumns = ref([])
const languageRows = ref([])
const languageFilter = ref('')
const appearanceRows = ref([])

const queryRows = ref([])
const queryStats = ref(null)
const queryKind = ref('')
const userRows = ref([])

async function setUserFlag(account, flag, value) {
  const response = await admin.putUser({ id: account.id, [flag]: value })
  const index = userRows.value.findIndex((row) => row.id === account.id)
  if (index >= 0) userRows.value.splice(index, 1, response.user)
}

const filteredLanguages = computed(() => {
  const query = (languageFilter.value || '').toLowerCase()
  if (!query) return languageRows.value
  return languageRows.value.filter((row) =>
    Object.values(row).some((value) => value.toLowerCase().includes(query)),
  )
})

// The audit's rename suggestions already cover part of `unconfigured`; the list of
// genuinely new languages is the remainder, which is what needs classifying from scratch.
const unpairedUnconfigured = computed(() => {
  if (!audit.value) return []
  const paired = new Set(audit.value.renames.map((entry) => entry.language))
  return audit.value.unconfigured.filter((name) => !paired.has(name))
})

async function tryToken() {
  tokenTrying.value = true
  tokenError.value = ''
  admin.setToken(tokenInput.value.trim())
  try {
    await admin.queries(1)
    authed.value = true
    await loadAll()
  } catch (exception) {
    admin.clearToken()
    tokenError.value = exception.message
  } finally {
    tokenTrying.value = false
  }
}

function logout() {
  admin.clearToken()
  authed.value = false
  tokenInput.value = ''
}

async function loadAll() {
  try {
    const [auditResponse, languagesResponse, appearanceResponse, usersResponse] =
      await Promise.all([
        api.configAudit(), admin.languages(), admin.appearance(), admin.users(),
      ])
    audit.value = auditResponse
    languageColumns.value = languagesResponse.columns
    languageRows.value = languagesResponse.rows
    appearanceRows.value = appearanceResponse.rows
    userRows.value = usersResponse.users
    await loadQueries()
  } catch (exception) {
    error.value = exception.message
  }
}

async function loadQueries() {
  const response = await admin.queries(300, queryKind.value)
  queryRows.value = response.queries
  queryStats.value = response.stats
}

// ------------------------------------------------------------------ language editing

const languageDialog = ref(false)
const languageEdit = ref({})
const saving = ref(false)

function editLanguage(row) {
  languageEdit.value = {
    language: '', group: '', genus: '', subgenus: '', simple_group: '',
    area: '', typology: '', lcode: '',
    _new: !row.language || !languageRows.value.some((r) => r.language === row.language),
    ...row,
  }
  languageDialog.value = true
}

function editExistingLanguage(name) {
  const row = languageRows.value.find((r) => r.language === name)
  if (row) editLanguage({ ...row })
}

/** Confirming a rename: the new on-disk name takes over the orphan row's curation. */
function editRename(entry) {
  const old = languageRows.value.find((r) => r.language === entry.was)
  editLanguage({ ...(old || {}), language: entry.language, original_language: entry.was, _new: false })
}

async function saveLanguage() {
  saving.value = true
  try {
    const body = { ...languageEdit.value }
    delete body._new
    const result = await admin.putLanguage(body)
    notifyCommit(result)
    languageDialog.value = false
    await loadAll()
  } catch (exception) {
    error.value = exception.message
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- appearance editing

const appearanceDialog = ref(false)
const appearanceEdit = ref({})

function editAppearance(row) {
  appearanceEdit.value = {
    group: '', color: 'royalBlue', marker: 'circle',
    _new: !row.group || !appearanceRows.value.some((r) => r.group === row.group),
    ...row,
  }
  appearanceDialog.value = true
}

async function saveAppearance() {
  saving.value = true
  try {
    const body = { ...appearanceEdit.value }
    delete body._new
    const result = await admin.putAppearance(body)
    notifyCommit(result)
    appearanceDialog.value = false
    await loadAll()
  } catch (exception) {
    error.value = exception.message
  } finally {
    saving.value = false
  }
}

function notifyCommit(result) {
  if (!result.changed.length) {
    $q.notify({ message: 'nothing changed', timeout: 1200, position: 'bottom-right' })
  } else if (result.committed) {
    $q.notify({
      message: `saved & committed: ${result.changed.join(', ')}`,
      timeout: 2500, position: 'bottom-right',
    })
  } else {
    // The file is written either way; an uncommitted edit is a warning, not a failure.
    $q.notify({
      type: 'warning', position: 'bottom-right', timeout: 6000,
      message: `saved, but the git commit failed: ${result.commit_error}`,
    })
  }
}

onMounted(async () => {
  if (admin.token()) {
    try {
      await admin.queries(1)
      authed.value = true
      await loadAll()
    } catch {
      admin.clearToken()
    }
  }
})
</script>

<style scoped>
.admin-page {
  max-width: 1100px;
  margin: 0 auto;
}
.config-table {
  max-height: 62vh;
  overflow-y: auto;
}
.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  vertical-align: middle;
}
.query-header {
  width: 100%;
  min-width: 0;
}
.query-text {
  max-height: 180px;
  overflow: auto;
  margin: 0 0 4px;
}
</style>
