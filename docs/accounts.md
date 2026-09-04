# Accounts

Phase 6.3. Decided with Kim 2026-09-01: **Google + GitHub + ORCID**, OAuth only.
The trigger was Phase 6.5 — LLM features need an allowlist, an allowlist needs identities.

## 1. The provider set, and the European question

Kim asked for Google/GitHub SSO "as on arborator.grew.fr" plus **a European option**.
Findings (2026-09-01, sources in the session log):

* There is **no European consumer IdP** users already carry. "Sign in with Proton" does
  not exist (only their SimpleLogin subsidiary offers OIDC, with a negligible user base);
  FranceConnect is restricted to public services.
* The real European answer is the **EU Digital Identity Wallet** (eIDAS 2.0): member
  states must ship wallets by Dec 2026, private-sector acceptance obligations start
  ~Dec 2027, protocol is OAuth2/OIDC (HAIP). No practical relying-party path for a small
  research site yet. **Revisit in 2027** — it will slot into the same authlib layer.
* The European *institutional* option is **eduGAIN** federated university login (RENATER
  in France; CLARIN's Service Provider Federation is the domain-appropriate umbrella).
  SAML federation work with a registration process — worth it only once real
  registrations show institutional demand.
* **ORCID** fills the gap now: the researcher identity, plain OAuth2, one registration.
  Not European in incorporation, but community-governed, and it names exactly the people
  an LLM allowlist is about.

So: Google + GitHub (parity with arborator), ORCID (researchers), eduGAIN and the EUDI
wallet as documented future providers.

## 2. Rules

* **No password accounts, ever.** grugrutyp holds no credentials — only the identity a
  provider vouched for: `(provider, subject)` where subject is the *stable* id (Google
  `sub`, GitHub numeric `id`, ORCID iD), never an email or login name.
* A provider is offered **only if its credentials are in `.env`** — the UI asks
  `/auth/providers` and shows exactly the buttons that will work. The feature ships dark
  until the OAuth apps are registered.
* The session is a **signed cookie** (starlette SessionMiddleware, secret
  `GRUGRUTYP_SESSION_SECRET` in `.env`, 30 days, SameSite=Lax — Lax because the OAuth
  callback is a top-level redirect and Strict would drop the state cookie).
* Two flags per user, set on the admin page: `is_admin` (opens `/admin` without the
  token; the token stays as bootstrap and break-glass) and `llm_allowed` (the Phase 6.5
  allowlist — off by default, money is opt-in per person).
* **Saved queries** are a name over the share-link payload, stored opaque. One
  serialisation, two transports; the link format is already versioned (`v: 1`).
* Privacy: the user table holds name and email as the provider reported them, nothing
  else; `/auth/me` returns only the session owner's row; other rows are admin-only.
  The query log remains unlinked to accounts — adding a user column there is a decision
  deliberately NOT taken (querylog.py docstring).

## 3. Registering the OAuth apps (admin task, once per provider)

Callback URLs are `https://typometrics.elizia.net/grugrutyp/api/auth/callback/<provider>`.

| provider | where | notes | `.env` keys |
|---|---|---|---|
| Google | console.cloud.google.com → APIs & Services → Credentials → OAuth client ID (web) | add the callback as an authorised redirect URI; configure the consent screen (external, scopes openid/email/profile) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| GitHub | github.com → Settings → Developer settings → OAuth Apps | homepage `https://typometrics.elizia.net/grugrutyp/`, the callback above | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` |
| ORCID | orcid.org → your record → Developer tools | the free public API is enough (`/authenticate` scope); redirect URI as above | `ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET` |

After adding keys: `systemctl restart grugrutyp-api`. The sign-in button appears by
itself once at least one provider is configured.

**Bootstrap the first admin**: sign in, then on the admin page (opened with the `.env`
token) flip your own account's `admin` toggle. From then on the page opens with the
session alone.

## 4. Files

| file | what |
|---|---|
| `backend/grugrutyp/auth.py` | provider registry, login/callback/logout, `/auth/me`, saved-query routes |
| `backend/grugrutyp/users.py` | SQLite store: users, flags, saved queries |
| `frontend/src/user.js` | the one piece of cross-view state |
| `App.vue` header | sign-in menu (only configured providers) / account menu |
| `PlotView.vue` share menu | Save query / My queries |
| `AdminView.vue` Users tab | the two toggles |

## Anonymous limits (audit 2026-09-02)

Exact-mode measures (`token_budget` 0/null) are clamped to the escalation ceiling
(1M tokens/language) for anonymous requests — full disk-scans of the giant treebanks
are for signed-in users. The budget option says so; the start event carries the
effective budget. Transport backstops live in nginx: 1MB body cap and per-IP
rate/connection limits on the API, and a 6-stream cap on `/measure`.

The two rate-limit zones are separate on purpose (2026-09-04): with one shared zone,
a page load's own dozen API calls filled the bucket and the SPA's auto-plot was
rejected with a 503 by its siblings. `/measure` now has its own budget, and
concurrency — not request rate — is what actually protects the disks.
