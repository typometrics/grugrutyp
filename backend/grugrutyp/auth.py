"""OAuth login: Google, GitHub, ORCID. Phase 6.3, decided with Kim 2026-09-01.

Three providers and no password accounts, ever -- grugrutyp holds no credentials, only
the identity a provider vouched for. ORCID is the researcher option; the truly European
institutional login (eduGAIN/CLARIN) and the EUDI wallet are documented as future
providers in `docs/accounts.md` -- everything here is plain OAuth2/OIDC through authlib,
so adding one is a registration, not a redesign.

A provider appears in `/auth/providers` only when its credentials are in `.env`
(`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `GITHUB_...`, `ORCID_...`), so the frontend
shows exactly the buttons that will work and the feature ships dark until the OAuth apps
are registered.

The session is a signed cookie (starlette's SessionMiddleware, secret in `.env`) holding
nothing but the user id; everything else is read from the store per request.
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .engine.neo4j_engine import load_env
from .users import get_users

load_env()

# The public URL of this API, as the OAuth providers and the browser see it. Explicit
# rather than derived from the request: behind nginx the app sees 127.0.0.1:8020, and a
# redirect_uri built from that would be rejected by every provider.
PUBLIC_BASE = os.environ.get("GRUGRUTYP_PUBLIC_BASE", "http://127.0.0.1:8020").rstrip("/")
# Where to land after a login: the site the API serves (…/grugrutyp/api -> …/grugrutyp/).
SITE_BASE = PUBLIC_BASE[: -len("/api")] + "/" if PUBLIC_BASE.endswith("/api") else "/"

oauth = OAuth()

# name -> the keys .env must hold for the provider to be offered
_PROVIDER_ENV = {
    "google": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "github": ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
    "orcid": ("ORCID_CLIENT_ID", "ORCID_CLIENT_SECRET"),
}


def _configured(provider: str) -> bool:
    return all(os.environ.get(key) for key in _PROVIDER_ENV[provider])


if _configured("google"):
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
if _configured("github"):
    oauth.register(
        name="github",
        client_id=os.environ["GITHUB_CLIENT_ID"],
        client_secret=os.environ["GITHUB_CLIENT_SECRET"],
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user"},
    )
if _configured("orcid"):
    oauth.register(
        name="orcid",
        client_id=os.environ["ORCID_CLIENT_ID"],
        client_secret=os.environ["ORCID_CLIENT_SECRET"],
        authorize_url="https://orcid.org/oauth/authorize",
        access_token_url="https://orcid.org/oauth/token",
        # ORCID's token endpoint wants the credentials as POST fields, not basic auth.
        token_endpoint_auth_method="client_secret_post",
        client_kwargs={"scope": "/authenticate"},
    )


async def _identity(provider: str, request: Request) -> tuple[str, str, str, str]:
    """`(subject, name, email, avatar)` from the provider's callback.

    The subject is the provider's *stable* identifier -- Google's `sub`, GitHub's numeric
    `id`, the ORCID iD -- never the email or login name, both of which people change.
    The avatar is a URL when the provider has one (Google `picture`, GitHub
    `avatar_url`); ORCID has no profile pictures and the UI falls back to an icon.
    """
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    if provider == "google":
        info = token.get("userinfo") or {}
        return (
            str(info["sub"]),
            info.get("name") or "",
            info.get("email") or "",
            info.get("picture") or "",
        )
    if provider == "github":
        response = await client.get("user", token=token)
        info = response.json()
        return (
            str(info["id"]),
            info.get("name") or info.get("login") or "",
            info.get("email") or "",
            info.get("avatar_url") or "",
        )
    # ORCID answers the /authenticate scope with the iD and name inside the token itself.
    return str(token["orcid"]), token.get("name") or "", "", ""


router = APIRouter()


@router.get("/auth/providers")
def providers() -> dict:
    return {"providers": [name for name in _PROVIDER_ENV if _configured(name)]}


@router.get("/auth/login/{provider}")
async def login(provider: str, request: Request):
    if provider not in _PROVIDER_ENV or not _configured(provider):
        raise HTTPException(status_code=404, detail={"message": f"no such provider: {provider}"})
    redirect_uri = f"{PUBLIC_BASE}/auth/callback/{provider}"
    return await oauth.create_client(provider).authorize_redirect(request, redirect_uri)


@router.get("/auth/callback/{provider}")
async def callback(provider: str, request: Request):
    if provider not in _PROVIDER_ENV or not _configured(provider):
        raise HTTPException(status_code=404, detail={"message": f"no such provider: {provider}"})
    try:
        subject, name, email, avatar = await _identity(provider, request)
    except OAuthError as exc:
        # A cancelled consent screen lands here; back to the site, not a JSON error page.
        return RedirectResponse(f"{SITE_BASE}?login=failed&reason={exc.error}")
    user = get_users().login(provider, subject, name, email, avatar)
    request.session.clear()
    request.session["uid"] = user["id"]
    return RedirectResponse(SITE_BASE)


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


def current_user(request: Request) -> dict | None:
    uid = request.session.get("uid")
    return get_users().get(uid) if uid else None


def require_user(request: Request) -> dict:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail={"message": "not signed in"})
    return user


@router.get("/auth/me")
def me(request: Request) -> dict:
    user = current_user(request)
    if user is None:
        return {"user": None}
    # The session owner gets their own row minus nothing -- but other users' emails are
    # nobody's business, so only the admin endpoint returns other people's rows.
    return {"user": user}


# --------------------------------------------------------------------- saved queries


class SaveQuery(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: str = Field(min_length=1, max_length=20_000)  # the share-link state, opaque


@router.get("/me/queries")
def my_queries(user: dict = Depends(require_user)) -> dict:
    return {"queries": get_users().queries(user["id"])}


@router.post("/me/queries")
def save_query(body: SaveQuery, user: dict = Depends(require_user)) -> dict:
    return {"query": get_users().add_query(user["id"], body.name.strip(), body.payload)}


@router.delete("/me/queries/{query_id}")
def delete_query(query_id: int, user: dict = Depends(require_user)) -> dict:
    if not get_users().delete_query(user["id"], query_id):
        raise HTTPException(status_code=404, detail={"message": "no such saved query"})
    return {"ok": True}
