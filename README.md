# Dynamic Island — Discord Voice Integration

Discord Application (without bot): 1559606305025556480

Project components:
- backend/  FastAPI OAuth2 code/refresh exchange in Docker.
- agent/    Windows Discord desktop RPC bridge and avatar cache.
- windhawk/ Standalone Discord card for Dynamic Island for Windows — Fork.

## Verified today
- Local desktop RPC named pipe: handshake -> READY for application ID.
- Windhawk C++ source compiles under Windhawk clang -fsyntax-only.
- Voice state model writes UTF-8 TSV with channel, server, member count, microphone status.
- Python modules compile.
- The RPC scopes have NOT yet been authorized. Voice API access is contingent on Discord approval/testing status.
- No Bot Token and no user-account automation via the Discord gateway.

## 1. Discord Developer Portal

In https://discord.com/developers/applications/1559606305025556480:
- Keep the application as a Discord Application. No bot is needed.
- For test access to RPC: your account must be the owner or approved tester.
- Request access to privileged OAuth2 scopes rpc, rpc.voice.read, rpc.notifications.read.
  They are partner-approval gated; creating an application alone is not sufficient.
- OAuth2: register exactly https://ddii.dekimdev.ru/oauth/callback
  (the same value in backend/.env and agent/config.json).

Official docs:
https://discord.com/developers/docs/topics/rpc
https://discord.com/developers/docs/topics/oauth2

## 2. Docker backend

On 2026-10-13 the backend was built and deployed on Dekim-PC via Docker Desktop.
`docker compose ps` showed `discord-oauth` running on `0.0.0.0:18080:8080`.
The local health endpoint and https://ddii.dekimdev.ru/health both returned HTTP 200.
Keep Docker Desktop running for the locally deployed container to remain available.

Configure backend/.env from backend/.env.example, changing:
- DISCORD_CLIENT_SECRET — Client Secret from the app's OAuth2 page. Never send it in chat.
- DISCORD_REDIRECT_URI — exact registered redirect URI.
- BRIDGE_API_KEY — randomly generated 32+ character shared key.

Deploy:
    cd backend
    docker compose up -d --build

Docker listens on 0.0.0.0:18080, because the reverse proxy lives on a separate server.
Reverse proxy to http://DOCKER_SERVER_IP:18080 with HTTPS at https://ddii.dekimdev.ru.
Configure the Docker host firewall to permit TCP/18080 only from the proxy IP.
Test GET https://ddii.dekimdev.ru/health.
The registered OAuth Redirect URI is https://ddii.dekimdev.ru/oauth/callback.

The backend only exchanges OAuth2 codes and refresh tokens. It does NOT
read Discord voice, store participant data, receive microphone/audio
samples, or need Discord bot permissions.

## 3. Windows agent

An agent/config.json was generated locally using the configured backend environment.
The Windows agent was started and registered for startup in the current user's HKCU Run key.

For reinstalling, copy agent/config.example.json to agent/config.json and fill:
- client_id = 1559606305025556480
- backend_url = HTTPS URL of your backend (without trailing slash)
- bridge_api_key = same BRIDGE_API_KEY as backend
- redirect_uri = same redirect URI from the Developer Portal

Then, in a regular Windows terminal with Python 3.12:

    cd C:\Projects\DynamicIslandDiscord\agent
    python diagnose_rpc.py
    python agent.py

The agent creates status.tsv so the Discord card appears in the island even
before login. Hover to expand it and click Log in. Discord Desktop presents
an authorization dialog; the agent exchanges its short-lived authorization code
through your backend and encrypts tokens with Windows DPAPI.
After successful login, the same button becomes Log out. Logout revokes the
refresh token on the backend (if reachable) and always deletes the local token.

To register the agent to start automatically after Windows login, run:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install_autostart.ps1

The agent must be running for the card login/logout button to respond.

When agent.py runs, the selected voice channel is polled every four
seconds. Guild name/icon, channel name, participant count/avatars and
mute/deafen state are persisted into:
    %LOCALAPPDATA%\DynamicIslandDiscord\state.tsv
    %LOCALAPPDATA%\DynamicIslandDiscord\assets\

No tokens or secrets are ever written to that state file.

If authorization fails with an RPC permission error, the app lacks
necessary Discord approval/scopes. identify/guilds alone are insufficient.
Set agent/config.json enable_notifications=false to omit the notification scope
until Discord grants it. Voice RPC still requires rpc and rpc.voice.read approval.
Do NOT substitute a user account token, scraped Discord client data or a bot.

## 4. Windhawk

The complete patched source is:
    windhawk\mod-integrated-discord.wh.cpp

The verified source has also been copied to
    C:\ProgramData\Windhawk\EditorWorkspace\mod.wh.cpp
Reopen the editor in Windhawk and compile. Do not paste the original pre-patch source.
The patch remains available independently; the project
also retains windhawk\mod-before-discord.wh.cpp.
It includes the header:
    C:\Projects\DynamicIslandDiscord\windhawk\discord_bridge.h
Keep this directory at the same path unless you adjust the include.

Enable Modules > Discord in Windhawk.

Discord is NOT a standalone pill or a separate Activity. It is the final tab
in the primary expanded island's mouse-wheel sequence:
clock/media -> calendar -> weather? -> hardware? -> file tray? -> Discord.
Expand the MAIN island and scroll to the Discord tab to click Log in or Log out.
The button has a dedicated hit-test and mouse capture for reliable clicks.

During an ongoing call, the single COLLAPSED island adds an inline voice
section next to the clock or media: server icon, elapsed time, mute indicator,
and Discord audio-level bars. It never creates a second capsule.
On the expanded Discord tab: server, channel, timer, member count, avatars,
and Log out. If signed out: the same tab offers Log in.

A copy of the prior two-pill implementation is stored in
windhawk\mod-before-integrated-discord.wh.cpp.

The agent subscribes to Discord RPC NOTIFICATION_CREATE. If rpc.notifications.read
is approved for the application, new incoming Discord notifications are shown
in the island via the existing notification card for five seconds. This is NOT
full message-history access and will not display messages Discord itself does
not notify the user about. No user token scraping or self-bot is used.

The duration is measured from the first observation by the local agent,
so restarting the agent while in a call may restart the timer.
The amplitude bars use Discord process Core Audio metering, NOT raw
microphone or voice audio; other sounds from Discord (such as notification
sounds) can also affect them. Nothing records or transmits audio.

## Tests

    python agent\test_voice_state.py

Clang syntax validation (Windows PowerShell):

    & 'C:\Program Files\Windhawk\Compiler\bin\clang++.exe' '@C:\Program Files\Windhawk\Compiler\compile_flags.txt' '-IC:\Program Files\Windhawk\Compiler\include' '-DWH_MOD_ID="dynamic-island-for-windows-fork"' -fsyntax-only 'C:\Projects\DynamicIslandDiscord\windhawk\mod-integrated-discord.wh.cpp'

## OAuth troubleshooting (2026-10-13)

- `rpc.py` was updated to avoid simultaneous reads and writes on one synchronous
  Windows Discord IPC handle. The request/reply test now completes in under one second.
- The HTTPS reverse proxy rejects the default Python urllib User-Agent with
  Cloudflare error 1010. The Windows agent now sends `User-Agent: DynamicIslandDiscord/1.0`.
- On a real authorization attempt, the Discord token API returned
  `invalid_client` (HTTP 401). The current `DISCORD_CLIENT_SECRET` configuration
  is exactly 64 hexadecimal characters, matching the typical format of the
  application's Public Key. Verify it is the actual OAuth2 **Client Secret**,
  not the **Public Key**, in the Discord Developer Portal. Do not share it.
- After correcting the backend/.env file, redeploy using
  `docker compose up -d --build --force-recreate` in the backend folder.
  The agent is already running and can retry when Log in is pressed.
- The Windhawk editor source has been updated to use the icon extracted from the
  installed Discord.exe rather than the placeholder D. Reopen the Windhawk
  editor and compile it again.


## Discord waveform: process-isolated audio (2026-10-13)

The collapsed Discord voice widget now uses WASAPI process loopback on
the Discord.exe process tree (VAD\Process_Loopback, Windows 10 build
20348+). No default Windows audio endpoint meter or IAudioSessionManager2
global fallback is used.

Audio samples are processed locally to RMS amplitude and discarded.
Nothing is recorded or sent to Docker. Capture runs only for a connected
Discord voice call while not deafened, and gracefully returns silence
rather than mixing in sounds from other Windows applications.

The eight rounded accent bars now respond to the current Discord audio
envelope all together and use the same attack/release weighting as the
media waveform. Old samples no longer slide left-to-right or vice versa.

Code:
- windhawk/discord_process_loopback.h -- filtered WASAPI backend.
- windhawk/discord_bridge.h -- lifecycle and ~35ms sampling.
- windhawk/mod-isolated-audio.wh.cpp -- validated full mod source.
- windhawk/mod-before-isolated-audio.wh.cpp -- full backup.
- windhawk/discord_bridge.before-isolated-audio.h -- original bridge.
- windhawk/test_process_loopback.cpp -- native activation test.

Verification:
- Windhawk Clang syntax check: success (exit 0).
- Native test: PROCESS_LOOPBACK_STARTED=1; CAPTURE_TEST_EXIT=0.
- Process-loopback program linked successfully without mmdevapi library.
- In testing Discord audio was nearly silent (~0.0001). Actual waveform
  reaction to speech must be confirmed during a live voice call.

Reopen Windhawk editor and compile the updated source at:
C:\ProgramData\Windhawk\EditorWorkspace\mod.wh.cpp
