// WASAPI process-loopback RMS probe for the Discord process tree.
//
// Reads only the Discord.exe process tree through the Windows 10 20348+
// VAD\Process_Loopback interface. Never reads a global endpoint audio meter.
// PCM samples stay in this process, are reduced immediately to an RMS level,
// and are neither recorded nor sent to a network endpoint.
#pragma once

// Old MinGW SDK shipped with Windhawk omits audioclientactivationparams.h.
// The layout is documented in Microsoft's ApplicationLoopback sample.
enum class DIProcessLoopbackMode : int32_t {
    IncludeTargetTree = 0,
    ExcludeTargetTree = 1,
};
struct DIProcessLoopbackActivation {
    DWORD targetPid;
    DIProcessLoopbackMode mode;
};
struct DIProcessAudioActivationParams {
    int32_t type; // AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
    DIProcessLoopbackActivation process;
};
static constexpr wchar_t kDIProcessLoopbackDevice[] = L"VAD\\Process_Loopback";

class DIProcessActivation final : public IActivateAudioInterfaceCompletionHandler {
public:
    DIProcessActivation() {
        ready_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    }
    ~DIProcessActivation() {
        if (ready_) CloseHandle(ready_);
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (IsEqualIID(id, __uuidof(IUnknown)) ||
            IsEqualIID(id, __uuidof(IActivateAudioInterfaceCompletionHandler)) ||
            IsEqualIID(id, __uuidof(IAgileObject))) {
            *out = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override {
        return refs_.fetch_add(1, std::memory_order_relaxed) + 1;
    }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG left = refs_.fetch_sub(1, std::memory_order_acq_rel) - 1;
        if (!left) delete this;
        return left;
    }
    HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* op) override {
        HRESULT activation = E_FAIL;
        ComPtr<IUnknown> unknown;
        const HRESULT hr = op->GetActivateResult(&activation, unknown.GetAddressOf());
        result_ = FAILED(hr) ? hr : activation;
        if (SUCCEEDED(result_) && unknown) {
            result_ = unknown.As(&client_);
        }
        SetEvent(ready_);
        return S_OK;
    }
    HANDLE event() const { return ready_; }
    HRESULT result() const { return result_; }
    ComPtr<IAudioClient> client() const { return client_; }
private:
    std::atomic<ULONG> refs_{1};
    HANDLE ready_ = nullptr;
    HRESULT result_ = E_PENDING;
    ComPtr<IAudioClient> client_;
};

DWORD DIDiscordRootProcessId() {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;
    struct Row { DWORD pid; DWORD parent; };
    std::vector<Row> candidates;
    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    if (Process32FirstW(snapshot, &entry)) {
        do {
            if (_wcsicmp(entry.szExeFile, L"Discord.exe") == 0) {
                candidates.push_back({entry.th32ProcessID, entry.th32ParentProcessID});
            }
        } while (Process32NextW(snapshot, &entry));
    }
    CloseHandle(snapshot);
    if (candidates.empty()) return 0;
    for (const Row& candidate : candidates) {
        bool parentIsDiscord = false;
        for (const Row& other : candidates) {
            if (candidate.parent == other.pid) {
                parentIsDiscord = true;
                break;
            }
        }
        if (!parentIsDiscord) return candidate.pid;
    }
    return candidates.front().pid;
}

class DIDiscordProcessCapture {
public:
    ~DIDiscordProcessCapture() { Stop(); }

    bool Start(DWORD process) {
        Stop();
        if (!process) return false;
        auto* handler = new DIProcessActivation();
        if (!handler->event()) {
            handler->Release();
            return false;
        }

        DIProcessAudioActivationParams params{};
        params.type = 1;
        params.process.targetPid = process;
        params.process.mode = DIProcessLoopbackMode::IncludeTargetTree;

        PROPVARIANT properties{};
        properties.vt = VT_BLOB;
        properties.blob.cbSize = sizeof(params);
        properties.blob.pBlobData = reinterpret_cast<BYTE*>(&params);

        // Resolve dynamically: some Windhawk toolchains do not link mmdevapi
        // import libraries by default, although Windows 11 exports this API.
        using ActivateFunction = HRESULT (WINAPI*)(
            LPCWSTR, REFIID, PROPVARIANT*,
            IActivateAudioInterfaceCompletionHandler*,
            IActivateAudioInterfaceAsyncOperation**);
        static HMODULE mmdevapi = LoadLibraryW(L"mmdevapi.dll");
        const auto activate = mmdevapi
            ? reinterpret_cast<ActivateFunction>(
                  GetProcAddress(mmdevapi, "ActivateAudioInterfaceAsync"))
            : nullptr;
        if (!activate) {
            handler->Release();
            return false;
        }
        ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
        const HRESULT startHr = activate(
            kDIProcessLoopbackDevice, __uuidof(IAudioClient),
            &properties, handler, operation.GetAddressOf());
        if (FAILED(startHr)) {
            handler->Release();
            return false;
        }

        // The async operation owns a COM reference to handler until callback.
        // Do not close its completion event before the callback executes.
        const DWORD wait = WaitForSingleObject(handler->event(), 3000);
        if (wait == WAIT_OBJECT_0 && SUCCEEDED(handler->result())) {
            client_ = handler->client();
        }
        handler->Release();
        if (!client_) return false;

        WAVEFORMATEX format{};
        format.wFormatTag = WAVE_FORMAT_PCM;
        format.nChannels = 2;
        format.nSamplesPerSec = 48000;
        format.wBitsPerSample = 16;
        format.nBlockAlign = 4;
        format.nAvgBytesPerSec = 192000;
        format.cbSize = 0;

        HRESULT hr = client_->Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
            0, 0, &format, nullptr);
        if (SUCCEEDED(hr))
            hr = client_->GetService(IID_PPV_ARGS(&capture_));
        if (SUCCEEDED(hr))
            hr = client_->Start();
        if (FAILED(hr)) {
            Stop();
            return false;
        }
        pid_ = process;
        return true;
    }

    void Stop() {
        if (client_ && pid_) client_->Stop();
        capture_.Reset();
        client_.Reset();
        pid_ = 0;
    }

    DWORD pid() const { return pid_; }

    std::array<float, 8> ReadLevels() {
        std::array<float, 8> levels{};
        if (!capture_) return levels;
        std::array<double, 8> sums{};
        std::array<uint64_t, 8> counts{};
        UINT32 packet = 0;
        HRESULT hr = capture_->GetNextPacketSize(&packet);
        int packets = 0;
        while (SUCCEEDED(hr) && packet && packets++ < 40) {
            BYTE* samples = nullptr;
            UINT32 frames = 0;
            DWORD flags = 0;
            hr = capture_->GetBuffer(&samples, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) break;
            if (samples && !(flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
                const int16_t* pcm = reinterpret_cast<const int16_t*>(samples);
                // Partition EACH packet into eight equal relative windows.
                // Previously 240 frames per bin left the final columns empty
                // when a typical WASAPI poll provided fewer than 1920 frames.
                // The eight bars update as one snapshot; no scrolling history.
                for (uint64_t i = 0; i < frames; ++i) {
                    const size_t bin = static_cast<size_t>(std::min<uint64_t>(
                        sums.size() - 1, i * sums.size() / frames));
                    const double left = pcm[i * 2] / 32768.0;
                    const double right = pcm[i * 2 + 1] / 32768.0;
                    sums[bin] += left * left + right * right;
                    counts[bin] += 2;
                }
            }
            capture_->ReleaseBuffer(frames);
            hr = capture_->GetNextPacketSize(&packet);
        }
        if (FAILED(hr)) {
            Stop();
            return levels;
        }
        // Identical RMS-to-amplitude mapping as the main Media module:
        // PushAudioChunks uses Clamp(sqrt(sum / samples) * 4, 0, 1).
        // Retain eight simultaneous bins rather than Media's scrolling
        // history; each bar represents fresh process-isolated Discord PCM.
        for (size_t i = 0; i < levels.size(); ++i) {
            const double rms = counts[i] ? std::sqrt(sums[i] / counts[i]) : 0.0;
            levels[i] = std::clamp(static_cast<float>(rms * 5.0), 0.0f, 1.0f);
        }
        return levels;
    }
private:
    DWORD pid_ = 0;
    ComPtr<IAudioClient> client_;
    ComPtr<IAudioCaptureClient> capture_;
};

std::array<float, 8> DIDiscordIsolatedAudioLevels(bool inCall) {
    static DIDiscordProcessCapture recorder;
    static ULONGLONG nextPidSearch = 0;
    static ULONGLONG nextCaptureRetry = 0;
    static DWORD targetPid = 0;
    if (!inCall) {
        recorder.Stop();
        targetPid = 0;
        nextPidSearch = 0;
        nextCaptureRetry = 0;
        return {};
    }
    const ULONGLONG now = GetTickCount64();

    if (now >= nextPidSearch || !targetPid) {
        nextPidSearch = now + 4000;
        targetPid = DIDiscordRootProcessId();
    }
    if (!targetPid) {
        recorder.Stop();
        return {};
    }
    if (recorder.pid() != targetPid) {
        // Failed activations can take seconds; don't retry each 35ms tick.
        if (now < nextCaptureRetry) return {};
        if (!recorder.Start(targetPid)) {
            // No fallback to endpoint/session-wide audio.
            nextCaptureRetry = GetTickCount64() + 5000;
            return {};
        }
        nextCaptureRetry = 0;
    }
    return recorder.ReadLevels();
}
