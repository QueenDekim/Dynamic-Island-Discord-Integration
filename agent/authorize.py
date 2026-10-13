"""Authorize the desktop Discord RPC integration using an OAuth2 application."""
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen
from rpc import DiscordRPC
from auth_store import save_token

CLIENT_ID = "1559606305025556480"
CONFIG = Path(__file__).with_name("config.json")
STORE = Path(os.environ["LOCALAPPDATA"]) / "DynamicIslandDiscord" / "oauth.dpapi"


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("client_id") != CLIENT_ID:
        raise RuntimeError("Incorrect client ID")
    url = config["backend_url"].rstrip("/") + "/v1/oauth/exchange"
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1:"):
        raise RuntimeError("OAuth backend URL requires HTTPS")

    rpc = DiscordRPC(CLIENT_ID)
    rpc.connect()
    print("Discord IPC connected. Discord may show an authorization dialog.")
    response = rpc.call("AUTHORIZE", {
        "client_id": CLIENT_ID,
        "scopes": ["rpc", "rpc.voice.read", "identify"]
    }, timeout=90)
    code = response.get("code") if isinstance(response, dict) else None
    if not code:
        raise RuntimeError("Discord did not return an authorization code")

    data = json.dumps({"code": code,
                       "redirect_uri": config["redirect_uri"]}).encode()
    req = Request(url, data=data, headers={
        "Content-Type": "application/json",
        "X-Bridge-Key": config["bridge_api_key"],
        "User-Agent": "DynamicIslandDiscord/1.0",
    }, method="POST")
    with urlopen(req, timeout=15) as reply:
        session = json.loads(reply.read(65536))
    if not session.get("access_token"):
        raise RuntimeError("No OAuth access granted")
    session["obtained_at"] = time.time()
    save_token(STORE, session)
    rpc.call("AUTHENTICATE", {"access_token": session["access_token"]})
    print("Discord user authorization successful. Credentials are encrypted for this Windows account.")
    rpc.close()


if __name__ == "__main__":
    main()
