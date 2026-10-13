"""Discord desktop RPC integration and on-card login/logout controller.

Run continuously in the current Windows session. No bots, gateway self-bots
or access to messages other than Discord's own RPC notifications.
"""
import json
import os
import queue
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from auth_store import load_token, save_token
from controller import (
    BASE, TOKEN, COMMAND, NOTICE, VOICE,
    pop_command, publish_status, publish_notification,
)
from rpc import DiscordRPC, RPCError
from voice_state import normalize, cache_images, write_windhawk_tsv

CLIENT_ID = "1559606305025556480"
CONFIG = Path(__file__).with_name("config.json")
ASSETS = BASE / "assets"


def config_load():
    if not CONFIG.exists():
        raise RuntimeError("Configure agent/config.json before authorizing")
    conf = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    if conf.get("client_id") != CLIENT_ID:
        raise RuntimeError("Unexpected Application ID")
    if not str(conf.get("backend_url", "")).startswith("https://"):
        raise RuntimeError("backend_url must use HTTPS")
    if len(str(conf.get("bridge_api_key", ""))) < 24:
        raise RuntimeError("Missing bridge_api_key in agent/config.json")
    return conf


def oauth_post(config, path, values):
    body = json.dumps(values).encode("utf-8")
    req = Request(config["backend_url"].rstrip("/") + path,
                  data=body, headers={"Content-Type": "application/json",
                                      "X-Bridge-Key": config["bridge_api_key"],
                                      "User-Agent": "DynamicIslandDiscord/1.0"},
                  method="POST")
    try:
        with urlopen(req, timeout=16) as reply:
            return json.loads(reply.read(65536))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(4096)).get("detail", "Request denied")
        except (ValueError, AttributeError):
            detail = "Request denied"
        raise RuntimeError(f"OAuth backend HTTP {exc.code}: {str(detail)[:135]}") from None


def fresh_access_token(config):
    saved = load_token(TOKEN)
    if not saved:
        raise RuntimeError("No saved authorization")
    if time.time() >= saved.get("obtained_at", 0) + saved.get("expires_in", 3600) - 120:
        refresh_token = saved.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Session expired; log in again")
        saved = oauth_post(config, "/v1/oauth/refresh", {"refresh_token": refresh_token})
        saved["obtained_at"] = time.time()
        save_token(TOKEN, saved)
    return saved["access_token"]


def authorize(rpc, config):
    publish_status("authorizing")
    scopes = ["rpc", "rpc.voice.read", "identify"]
    if config.get("enable_notifications", True):
        scopes.append("rpc.notifications.read")
    result = rpc.call("AUTHORIZE", {
        "client_id": CLIENT_ID,
        "scopes": scopes
    }, timeout=90)
    if not isinstance(result, dict) or not result.get("code"):
        raise RuntimeError("Discord authorization did not provide a code")
    tokens = oauth_post(config, "/v1/oauth/exchange", {
        "code": result["code"],
        "redirect_uri": config["redirect_uri"]
    })
    if not tokens.get("access_token"):
        raise RuntimeError("OAuth backend returned no access token")
    tokens["obtained_at"] = time.time()
    save_token(TOKEN, tokens)
    return rpc.call("AUTHENTICATE", {"access_token": tokens["access_token"]})


def authenticated_connect(config):
    rpc = DiscordRPC(CLIENT_ID)
    rpc.connect()
    response = rpc.call("AUTHENTICATE", {"access_token": fresh_access_token(config)})
    return rpc, response


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    COMMAND.unlink(missing_ok=True)
    NOTICE.unlink(missing_ok=True)
    rpc = None
    connected = False
    notifications_ok = False
    logged_in = False
    last_channel = ""
    joined_at = 0.0
    guild_id = ""
    guild = {}
    next_poll = 0.0
    next_retry = 0.0
    last_status = 0.0
    status_text = ""
    publish_status("idle")
    print("Discord voice agent ready. Click Log in on the island to authorize.")
    try:
        while True:
            cmd = pop_command()
            now = time.monotonic()

            if cmd == "logout":
                if rpc:
                    rpc.close()
                    rpc = None
                try:
                    config = config_load()
                    tokens = load_token(TOKEN) or {}
                    token = tokens.get("refresh_token") or tokens.get("access_token")
                    if token:
                        oauth_post(config, "/v1/oauth/revoke", {"token": token})
                except Exception:
                    pass  # Local logout must succeed even when offline.
                TOKEN.unlink(missing_ok=True)
                NOTICE.unlink(missing_ok=True)
                write_windhawk_tsv({"connected": False}, VOICE)
                logged_in = False
                connected = False
                last_channel = ""
                joined_at = 0.0
                status_text = ""
                publish_status("idle")
                print("Logged out from Dynamic Island Discord.")

            if cmd == "login":
                try:
                    config = config_load()
                    if rpc:
                        rpc.close()
                    rpc = DiscordRPC(CLIENT_ID)
                    rpc.connect()
                    authorize(rpc, config)
                    logged_in = True
                    connected = True
                    guild_id = ""
                    next_poll = 0.0
                    notifications_ok = subscribe_notifications(rpc) if config.get("enable_notifications", True) else False
                    status_text = "" if notifications_ok else "Notifications scope unavailable"
                    publish_status("authorized", status_text)
                    print("Authorized Discord desktop RPC.")
                except Exception as error:
                    if rpc:
                        rpc.close()
                        rpc = None
                    logged_in = False
                    connected = False
                    status_text = str(error)[:220]
                    publish_status("error", status_text)
                    print("Discord authorization unavailable:", status_text, file=sys.stderr)

            if not logged_in and cmd != "login" and TOKEN.exists() and now >= next_retry:
                next_retry = now + 8.0
                try:
                    config = config_load()
                    rpc, identity = authenticated_connect(config)
                    logged_in = connected = True
                    next_poll = 0.0
                    guild_id = ""
                    notifications_ok = subscribe_notifications(rpc) if config.get("enable_notifications", True) else False
                    status_text = "" if notifications_ok else "Notifications scope unavailable"
                except Exception as error:
                    if rpc:
                        rpc.close()
                        rpc = None
                    logged_in = connected = False
                    status_text = str(error)[:220]

            if logged_in and rpc:
                try:
                    rpc.poll()
                except (RPCError, OSError, ValueError) as error:
                    status_text = str(error)[:220]
                    publish_status("error", status_text)
                    write_windhawk_tsv({"connected": False}, VOICE)
                    rpc.close()
                    rpc = None
                    logged_in = connected = False
                    next_retry = now + 5.0
                    continue
                while True:
                    try:
                        evt = rpc.events.get_nowait()
                    except queue.Empty:
                        break
                    if evt.get("evt") == "NOTIFICATION_CREATE":
                        publish_notification(evt.get("data", {}))

                if now >= next_poll:
                    next_poll = now + 4.0
                    try:
                        channel = rpc.call("GET_SELECTED_VOICE_CHANNEL")
                        if not isinstance(channel, dict) or not channel.get("id"):
                            joined_at = 0.0
                            last_channel = ""
                            write_windhawk_tsv({"connected": False}, VOICE)
                        else:
                            current = str(channel["id"])
                            if current != last_channel:
                                joined_at = time.time()
                                last_channel = current
                            current_guild = str(channel.get("guild_id", ""))
                            if guild_id != current_guild:
                                guild_id = current_guild
                                guild = rpc.call("GET_GUILD", {"guild_id": guild_id}) if guild_id else {}
                            settings = rpc.call("GET_VOICE_SETTINGS") or {}
                            state = normalize(channel, guild, settings, joined_at=joined_at)
                            cache_images(state, ASSETS)
                            write_windhawk_tsv(state, VOICE)
                    except Exception as error:
                        print("Discord voice poll:", str(error)[:200], file=sys.stderr)
                        write_windhawk_tsv({"connected": False}, VOICE)
                        if "disconnected" in str(error).lower():
                            rpc.close()
                            rpc = None
                            connected = logged_in = False
                            next_retry = now + 6.0

            if now - last_status >= 2.0:
                last_status = now
                mode = "authorized" if logged_in else ("error" if status_text else "idle")
                publish_status(mode, status_text)
            time.sleep(0.25)
    except KeyboardInterrupt:
        write_windhawk_tsv({"connected": False}, VOICE)
        publish_status("idle")
        if rpc:
            rpc.close()


def subscribe_notifications(rpc):
    try:
        rpc.call("SUBSCRIBE", {}, event="NOTIFICATION_CREATE")
        return True
    except RPCError as error:
        print("Discord RPC notifications unavailable:", error, file=sys.stderr)
        return False


if __name__ == "__main__":
    main()
