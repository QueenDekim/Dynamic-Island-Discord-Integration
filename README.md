# Dynamic Island — Discord Integration

Discord Desktop OAuth2, уведомления и голосовой канал в Dynamic Island for Windows Enhanced.

**Основной проект:** https://github.com/QueenDekim/Dynamic-Island-for-Windows-Enhanced
**Этот submodule:** https://github.com/QueenDekim/Dynamic-Island-Discord-Integration

## Состав

- agent/ — Windows-агент на Python: Discord Desktop RPC, OAuth, DPAPI, статус звонка и уведомления.
- backend/ — OAuth2-сервер FastAPI в Docker.
- windhawk/discord_bridge.h — чтение состояния/уведомлений и интеграция с Windhawk.
- windhawk/discord_process_loopback.h — WASAPI Process Loopback только для дерева Discord.exe.
- windhawk/test_process_loopback.cpp — самостоятельный тест изолированного аудиозахвата.

Необходимо Discord Desktop-приложение. **Бот не используется**, пользовательский Discord-токен не извлекается.

## Discord Developer Portal

Application ID: 1559606305025556480

Redirect URI: https://ddii.dekimdev.ru/oauth/callback

Требуемые разрешения: rpc, rpc.voice.read, identify; для уведомлений также rpc.notifications.read. Некоторые RPC scopes требуют согласования с Discord. Обычный OAuth2 identify/guilds не даёт доступ к реальному составу звонка.

## Backend (Docker)

Создайте backend/.env из backend/.env.example и заполните фактические DISCORD_CLIENT_SECRET и BRIDGE_API_KEY. Секреты никогда не коммитьте.

~~~powershell
cd backend
docker compose up -d --build
~~~

Публикуется 0.0.0.0:18080 -> 8080, чтобы обратный прокси на отдельном сервере мог подключаться к Docker-хосту. Разрешайте доступ к TCP/18080 только с IP реверс-прокси. Публичный HTTPS-домен: https://ddii.dekimdev.ru

Проверка: GET https://ddii.dekimdev.ru/health.

## Windows-агент

Скопируйте agent/config.example.json в agent/config.json. Установите bridge_api_key равным ключу в backend/.env. Оба этих рабочих файла исключены из Git.

~~~powershell
cd agent
python diagnose_rpc.py
python agent.py
~~~

Для автозапуска в текущей учётной записи Windows:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_autostart.ps1
~~~

Вкладка Discord внутри общего острова показывает Log in, затем Log out после входа. OAuth2-токены хранятся локально под защитой Windows DPAPI. Результат RPC авторизации не выводится в C++ мод как токен.

## Визуализация входящего звука

Источник — WASAPI Process Loopback на дереве процессов Discord.exe. Мод не захватывает общий звук Windows. Измеряется RMS-уровень звука и затем PCM-данные немедленно отбрасываются (без записи или передачи на сервер). На компактной капсуле восемь столбцов откликаются одновременно.

Для голоса используется шумовой порог RMS 0.0006 и повышенная нелинейная чувствительность:

~~~text
visual_level = sqrt(clamp((rms - 0.0006) * 120, 0, 1))
~~~

Атака/затухание согласованы с медиамодулем. При отсутствии захвата Discord визуализация остаётся в покое, а не переключается на системный аудиомикс. Для Process Loopback требуется совместимая версия Windows (Windows 10 build 20348+ / Windows 11).

## Windhawk

**Исходник всего мода хранится в основном репозитории**, а не здесь.

~~~powershell
git clone --recurse-submodules https://github.com/QueenDekim/Dynamic-Island-for-Windows-Enhanced.git
cd Dynamic-Island-for-Windows-Enhanced
python scripts/build.py
~~~

Вставьте dist/mod.wh.cpp в редактор Windhawk и скомпилируйте.

## Тесты

~~~powershell
python agent/test_controller.py
python agent/test_voice_state.py
python agent/test_auth_store.py
~~~

Отдельный тест WASAPI: windhawk/test_process_loopback.cpp. Проверка захвата под реальный голосовой разговор проводится после компиляции Windhawk.

**Безопасность:** не публикуйте .env, agent/config.json, токены DPAPI, журналы запросов с кодами авторизации или локальные файлы состояния.
