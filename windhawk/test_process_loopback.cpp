// Local diagnostics: no audio file or sample payload is ever persisted.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <objidl.h>
#include <tlhelp32.h>
#include <wrl/client.h>
#include <atomic>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>
using Microsoft::WRL::ComPtr;
#include "discord_process_loopback.h"

int main() {
    HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    if(FAILED(hr)){printf("COM_INIT_FAIL=%08lx\n",(long)hr);return 1;}
    DWORD root=DIDiscordRootProcessId();
    printf("DISCORD_ROOT_FOUND=%d\n", root!=0);
    DIDiscordProcessCapture capture;
    bool started=capture.Start(root);
    printf("PROCESS_LOOPBACK_STARTED=%d\n", started);
    if(started){
        float maximum=0;
        for(int i=0;i<30;++i){
            Sleep(70);
            maximum=std::max(maximum,capture.ReadRms());
        }
        printf("CAPTURE_READ_COMPLETE=1\n");
        printf("OBSERVED_DISCORD_AUDIO_PEAK=%.4f\n",maximum);
    }
    capture.Stop();
    CoUninitialize();
    return started?0:2;
}
