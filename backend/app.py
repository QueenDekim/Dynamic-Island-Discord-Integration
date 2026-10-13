"""Minimal OAuth2 code-exchange service for the Discord desktop RPC bridge.

Only used to exchange a one-use authorization code for a token.
Never log authorization codes, user access tokens or secrets.
"""
import hmac
import os
from collections import defaultdict
from time import monotonic

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Dynamic Island Discord OAuth Bridge", docs_url=None, redoc_url=None)
attempts = defaultdict(list)


class ExchangeRequest(BaseModel):
    code: str = Field(min_length=8, max_length=2048)
    redirect_uri: str = Field(min_length=8, max_length=2048)


@app.get("/health")
async def health():
    return {"ok": True, "service": "dynamic-island-discord-oauth"}


@app.post("/v1/oauth/exchange")
async def exchange(payload: ExchangeRequest, x_bridge_key: str = Header(default="")):
    expected_key = os.environ.get("BRIDGE_API_KEY", "")
    secret = os.environ.get("DISCORD_CLIENT_SECRET", "")
    client_id = os.environ.get("DISCORD_CLIENT_ID", "1559606305025556480")
    redirect = os.environ.get("DISCORD_REDIRECT_URI", "")

    if not expected_key or len(expected_key) < 24 or not secret or not redirect:
        raise HTTPException(503, "Server is not configured")
    if not hmac.compare_digest(expected_key, x_bridge_key):
        raise HTTPException(401, "Unauthorized")
    if payload.redirect_uri != redirect:
        raise HTTPException(400, "Unexpected redirect_uri")

    # Coarse local rate limiter, in addition to host firewall reverse-proxy limits.
    now = monotonic()
    history = attempts[x_bridge_key]
    history[:] = [x for x in history if now - x < 60]
    if len(history) >= 10:
        raise HTTPException(429, "Rate limit")
    history.append(now)

    try:
        async with httpx.AsyncClient(timeout=12) as http:
            response = await http.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": secret,
                    "grant_type": "authorization_code",
                    "code": payload.code,
                    "redirect_uri": redirect,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.RequestError:
        raise HTTPException(502, "Discord token endpoint unreachable")
    if response.status_code != 200:
        # Expose only the machine-readable OAuth error category, never the
        # authorization code, access token, client secret, or request payload.
        error_code = "unknown_error"
        try:
            value = response.json().get("error", "")
            if isinstance(value, str) and value in {
                "invalid_grant", "invalid_client", "invalid_request",
                "invalid_scope", "unauthorized_client", "access_denied",
                "unsupported_grant_type", "server_error",
            }:
                error_code = value
        except (ValueError, AttributeError):
            pass
        raise HTTPException(400, f"Discord OAuth exchange: {error_code} (upstream HTTP {response.status_code})")
    data = response.json()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in"),
        "token_type": data.get("token_type"),
        "scope": data.get("scope"),
    }


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=2048)


@app.post("/v1/oauth/refresh")
async def refresh(payload: RefreshRequest, x_bridge_key: str = Header(default="")):
    expected_key = os.environ.get("BRIDGE_API_KEY", "")
    secret = os.environ.get("DISCORD_CLIENT_SECRET", "")
    client_id = os.environ.get("DISCORD_CLIENT_ID", "1559606305025556480")
    if not expected_key or len(expected_key) < 24 or not secret:
        raise HTTPException(503, "Server is not configured")
    if not hmac.compare_digest(expected_key, x_bridge_key):
        raise HTTPException(401, "Unauthorized")
    try:
        async with httpx.AsyncClient(timeout=12) as http:
            response = await http.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": secret,
                    "grant_type": "refresh_token",
                    "refresh_token": payload.refresh_token,
                },
            )
    except httpx.RequestError:
        raise HTTPException(502, "Discord token endpoint unreachable")
    if response.status_code != 200:
        raise HTTPException(401, "Discord refresh token rejected")
    data = response.json()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in"),
        "token_type": data.get("token_type"),
        "scope": data.get("scope"),
    }

from fastapi.responses import HTMLResponse

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback():
    return HTMLResponse(
        "<!doctype html><html><meta charset='utf-8'><title>Discord OAuth</title>"
        "<body>Return to the Dynamic Island desktop app.</body></html>",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


class RevokeRequest(BaseModel):
    token: str = Field(min_length=8, max_length=2048)


@app.post("/v1/oauth/revoke")
async def revoke(payload: RevokeRequest, x_bridge_key: str = Header(default="")):
    expected_key = os.environ.get("BRIDGE_API_KEY", "")
    secret = os.environ.get("DISCORD_CLIENT_SECRET", "")
    if not expected_key or len(expected_key) < 24 or not secret:
        raise HTTPException(503, "Server is not configured")
    if not hmac.compare_digest(expected_key, x_bridge_key):
        raise HTTPException(401, "Unauthorized")
    data = {
        "client_id": os.environ.get("DISCORD_CLIENT_ID", "1559606305025556480"),
        "client_secret": secret,
        "token": payload.token,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post("https://discord.com/api/oauth2/token/revoke",
                                         data=data)
    except httpx.RequestError:
        raise HTTPException(502, "Discord revoke endpoint unreachable")
    if response.status_code != 200:
        raise HTTPException(502, "Discord token revocation failed")
    return {"revoked": True}
