// Discord local RPC voice bridge: receives state published by the user's
// authorized Windows agent, without any Discord bot or account token in Windhawk.
#pragma once

std::wstring DIDiscordBasePath() {
    wchar_t path[32768] = {};
    const DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", path, ARRAYSIZE(path));
    if (!n || n >= ARRAYSIZE(path)) return {};
    return std::wstring(path) + L"\\DynamicIslandDiscord\\";
}

bool DIDiscordValidImagePath(const std::wstring& imagePath) {
    const std::wstring base = ToLowerCopy(DIDiscordBasePath() + L"assets\\");
    const std::wstring test = ToLowerCopy(imagePath);
    return !base.empty() && test.size() > base.size() &&
           test.compare(0, base.size(), base) == 0 &&
           test.find(L"..", base.size()) == std::wstring::npos;
}

BitmapPixels DIDiscordReadImage(const std::wstring& path) {
    static std::unordered_map<std::wstring, BitmapPixels> cache;
    if (!DIDiscordValidImagePath(path)) return {};
    const auto it = cache.find(path);
    if (it != cache.end()) return it->second;
    std::vector<uint8_t> bytes;
    BitmapPixels pixels;
    if (DIBBridgeReadFile(path, 250000, &bytes) &&
        DecodeImageBytesToPixels(bytes, &pixels)) {
        if (cache.size() > 48) cache.clear();
        cache[path] = pixels;
    }
    return pixels;
}

bool DIDiscordReadSnapshot(DiscordSnapshot* next) {
    const std::wstring base = DIDiscordBasePath();
    if (base.empty()) return false;
    std::vector<uint8_t> bytes;
    if (!DIBBridgeReadFile(base + L"state.tsv", 16384, &bytes, true)) return false;
    const std::string raw(bytes.begin(), bytes.end());
    std::vector<std::string> parts;
    size_t start = 0;
    while (start < raw.size() && parts.size() < 40) {
        size_t end = raw.find('\n', start);
        if (end == std::string::npos) end = raw.size();
        auto text = raw.substr(start, end - start);
        if (!text.empty() && text.back() == '\r') text.pop_back();
        parts.push_back(std::move(text));
        start = end + 1;
    }
    if (parts.size() < 10 || parts[0] != "DISCORD1" || parts[1] != "1")
        return false;
    next->connected = true;
    next->guildName = DIBBridgeUtf8(parts[2]);
    next->channelName = DIBBridgeUtf8(parts[3]);
    try {
        next->joinedUnix = std::max(int64_t{0}, std::stoll(parts[4]));
        next->memberCount = std::clamp(std::stoi(parts[5]), 0, 100000);
        next->micMuted = parts[6] == "1";
        next->deafened = parts[7] == "1";
        const int count = std::clamp(std::stoi(parts[9]), 0, 12);
        if (parts.size() < static_cast<size_t>(10 + count * 2)) return false;
        next->icon = DIDiscordReadImage(DIBBridgeUtf8(parts[8]));
        for (int i = 0; i < count; ++i) {
            DiscordMember member;
            member.name = DIBBridgeUtf8(parts[10 + i * 2]);
            member.avatar = DIDiscordReadImage(DIBBridgeUtf8(parts[11 + i * 2]));
            next->members.push_back(std::move(member));
        }
        const size_t channelIdField = static_cast<size_t>(10 + count * 2);
        if (parts.size() > channelIdField)
            next->channelId = DIBBridgeUtf8(parts[channelIdField]);
        if (parts.size() > channelIdField + 1)
            next->voiceStartedUnix = std::max(int64_t{0},
                std::stoll(parts[channelIdField + 1]));
    } catch (...) {
        return false;
    }
    return true;
}


// Small control/status protocol; never contains OAuth tokens.
bool DIDiscordReadStatus(DiscordSnapshot* next) {
    const std::wstring statusFile = DIDiscordBasePath() + L"status.tsv";
    std::vector<uint8_t> data;
    if (!DIBBridgeReadFile(statusFile, 2048, &data, false)) return false;
    // Accept both LF and CRLF. Earlier Windows agents used text-mode
    // write_text(), so the old prefix check rejected every status file.
    const std::string text(data.begin(), data.end());
    std::vector<std::string> lines;
    size_t pos = 0;
    while (pos < text.size() && lines.size() < 3) {
        const size_t end = text.find('\n', pos);
        std::string line = text.substr(pos, end == std::string::npos
                                               ? std::string::npos : end - pos);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        lines.push_back(std::move(line));
        if (end == std::string::npos) break;
        pos = end + 1;
    }
    if (lines.size() < 2 || lines[0] != "DISCORDSTATUS1") return false;
    const std::string& mode = lines[1];
    if (mode != "authorized" && mode != "idle" && mode != "authorizing" &&
        mode != "error") return false;
    WIN32_FILE_ATTRIBUTE_DATA attrs{};
    if (!GetFileAttributesExW(statusFile.c_str(), GetFileExInfoStandard, &attrs))
        return false;
    FILETIME current{};
    GetSystemTimeAsFileTime(&current);
    ULARGE_INTEGER present{}, modified{};
    present.LowPart = current.dwLowDateTime;
    present.HighPart = current.dwHighDateTime;
    modified.LowPart = attrs.ftLastWriteTime.dwLowDateTime;
    modified.HighPart = attrs.ftLastWriteTime.dwHighDateTime;
    const ULONGLONG maxAge = mode == "authorizing" ?
        1200000000ULL : 150000000ULL; // 120 or 15 seconds in 100-ns units
    if (present.QuadPart > modified.QuadPart &&
        present.QuadPart - modified.QuadPart > maxAge) return false;
    next->authError = DIBBridgeUtf8(lines.size() >= 3 ? lines[2] : "");
    next->agentAvailable = true;
    next->authenticated = mode == "authorized";
    next->authorizing = mode == "authorizing";
    return true;
}

bool DIDiscordWriteCommand(const wchar_t* action) {
    if (wcscmp(action, L"login") != 0 && wcscmp(action, L"logout") != 0)
        return false;
    const std::wstring base = DIDiscordBasePath();
    if (base.empty()) return false;
    const std::string payload = wcscmp(action, L"login") == 0
                                    ? "DISCORDCMD1\nlogin\n"
                                    : "DISCORDCMD1\nlogout\n";
    const std::wstring staging = base + L"command.new";
    const std::wstring target = base + L"command.txt";
    HANDLE h = CreateFileW(staging.c_str(), GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    BOOL ok = WriteFile(h, payload.data(), static_cast<DWORD>(payload.size()),
                        &written, nullptr);
    CloseHandle(h);
    if (!ok || written != payload.size()) {
        DeleteFileW(staging.c_str());
        return false;
    }
    if (!MoveFileExW(staging.c_str(), target.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileW(staging.c_str());
        return false;
    }
    return true;
}

bool DIDiscordTakeNotification(NotificationSnapshot* output) {
    std::vector<uint8_t> bytes;
    if (!DIBBridgeReadFile(DIDiscordBasePath() + L"notification.tsv",
                           2048, &bytes, true)) return false;
    const std::string raw(bytes.begin(), bytes.end());
    std::vector<std::string> lines;
    size_t pos = 0;
    while (pos < raw.size() && lines.size() < 6) {
        size_t end = raw.find('\n', pos);
        if (end == std::string::npos) end = raw.size();
        std::string line = raw.substr(pos, end - pos);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        lines.push_back(std::move(line));
        pos = end + 1;
    }
    if (lines.size() < 5 || lines[0] != "DISCORDNOTIFY1" ||
        lines[1].empty()) return false;
    static std::string lastId;
    if (lastId == lines[1]) return false;
    lastId = lines[1];
    output->active = true;
    output->app = L"Discord";
    output->title = DIBBridgeUtf8(lines[2]);
    output->body = DIBBridgeUtf8(lines[3]);
    // The notification's optional sixth field is a cached sender avatar.
    // Older agents don't send it; retain the app icon as a fallback.
    if (lines.size() >= 6 && !lines[5].empty())
        output->icon = DIDiscordReadImage(DIBBridgeUtf8(lines[5]));
    if (output->icon.bgra.empty())
        output->icon = FindAppIconByName(L"Discord", 32);
    output->expiresAt = NowSeconds() + 5.0;
    return true;
}

#include "discord_process_loopback.h"

DWORD WINAPI DiscordThreadProc(void*) {
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    ULONGLONG lastStatePoll = 0;
    ULONGLONG lastAudioPoll = 0;
    while (WaitForSingleObject(g_stopEvent, 16) == WAIT_TIMEOUT) {
        bool enabled = true;
        {
            std::lock_guard lock(g_settingsMutex);
            enabled = g_settings.discord;
        }
        if (!enabled) {
            g_discordProcessRunning.store(false, std::memory_order_relaxed);
            g_discordVoiceActive.store(false, std::memory_order_relaxed);
            g_discordAutoExpandUntil.store(0.0, std::memory_order_relaxed);
            DIDiscordIsolatedAudioLevels(false);
            continue;
        }

        const ULONGLONG now = GetTickCount64();
        if (now - lastStatePoll >= 1200) {
            lastStatePoll = now;
            DiscordSnapshot update;
            const bool processRunning = DIDiscordRootProcessId() != 0;
            const bool connected = processRunning && DIDiscordReadSnapshot(&update);
            update.connected = connected;
            DIDiscordReadStatus(&update);
            NotificationSnapshot notice;
            const bool haveNotice = processRunning && DIDiscordTakeNotification(&notice);
            bool voiceChanged = false;
            {
                std::lock_guard lock(g_stateMutex);
                const auto& previous = g_state.discord;
                voiceChanged = connected &&
                    (!previous.connected ||
                     (update.channelId != previous.channelId &&
                      (!update.channelId.empty() || !previous.channelId.empty())) ||
                     (update.channelId.empty() && previous.channelId.empty() &&
                      (update.joinedUnix != previous.joinedUnix ||
                       update.guildName != previous.guildName ||
                       update.channelName != previous.channelName)));
                // Preserve process-isolated audio during metadata refresh.
                update.waveform = previous.waveform;
                update.waveformWrite = previous.waveformWrite;
                g_state.discord = std::move(update);
                if (haveNotice)
                    g_state.notification = std::move(notice);
            }
            g_discordProcessRunning.store(processRunning, std::memory_order_relaxed);
            g_discordVoiceActive.store(connected, std::memory_order_relaxed);
            if (voiceChanged) {
                g_discordAutoExpandUntil.store(NowSeconds() + 5.0,
                                               std::memory_order_relaxed);
                TriggerNudge();
            } else if (!connected) {
                g_discordAutoExpandUntil.store(0.0, std::memory_order_relaxed);
            }
            if (haveNotice) TriggerNudge();
            g_layoutDirty = true;
        }
        if (now - lastAudioPoll >= 16) {
            lastAudioPoll = now;
            bool activeCall = false;
            {
                std::lock_guard lock(g_stateMutex);
                activeCall = g_state.discord.connected && !g_state.discord.deafened;
            }
            // Process-loopback handles capture lifecycle, returning zero when
            // Discord is not on a call. No system-wide metering fallback.
            const auto levels = DIDiscordIsolatedAudioLevels(activeCall);
            if (!activeCall) continue;
            std::lock_guard lock(g_stateMutex);
            auto& voice = g_state.discord;
            // Eight current PCM levels update all bars in the SAME frame.
            // Each bar has its own envelope: no time-shifted ring-buffer
            // indexing and no movement from right to left.
            for (size_t i = 0; i < levels.size(); ++i) {
                const float previous = voice.waveform[i];
                const float level = levels[i];
                // Twice the response rate in continuous-time terms:
                // compose the prior EMA update with itself (not 2x the
                // coefficient, which would exceed 100% on attack).
                voice.waveform[i] = level > previous
                    ? previous * 0.09f + level * 0.91f
                    : previous * 0.7225f + level * 0.2775f;
            }
            ++voice.waveformWrite;
            g_layoutDirty = true;
        }
    }
    DIDiscordIsolatedAudioLevels(false); // Stop WASAPI before COM uninitialization.
    winrt::uninit_apartment();
    return 0;
}
