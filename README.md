# САПР-001 — IoT-контроллер вентиляции по CO₂

Курсовой проект по САПР для одной комнаты. ESP32 читает SCD41, управляет вытяжным вентилятором и проверяет вращение по тахометру. Телеметрия совместима с API AirCheck.

## Комплект

[Чертежи, схемы и перечни в редактируемых форматах, PDF и PNG](<Комплект проекта/Чертежи/README.md>)

| Материал | Содержимое |
|---|---|
| [Функциональная схема](hardware/SAPR-001-functional.drawio) | Измерение, силовая ветвь, управление, обратная связь |
| [Проект KiCad](hardware/SAPR-001-E3.kicad_pro) · [PDF схемы](hardware/SAPR-001-E3.pdf) | Принципиальная схема Э3 и локальная библиотека |
| [Перечень элементов](hardware/bom.csv) · [Подключения](hardware/connections.csv) | Компоненты, распиновка, питание и защита |
| [Монтажные 3D-модели DWG](Комплект%20проекта/Чертежи/Редактируемые/3D/README.md) · [Сборка корпуса DWG](outputs/SAPR-001-assembly.dwg) · [Чертежи PDF](outputs/SAPR-001-drawings.pdf) | Корпус 115 × 80 × 33 мм, внутренний монтаж и демонстрационная сборка с вентилятором |
| [ПЭ3](hardware/SAPR-001-PE3.pdf) · [Спецификация](outputs/SAPR-001-specification.pdf) | Перечень элементов Э3 и комплектность сборки |
| [Ревизия и критерии](tests/review-R02.md) · [Протокол цифровой приёмки](tests/acceptance.md) | Результаты инженерной проверки R02 и условия стендовой проверки |
| [Соответствие теме и ВКР](tests/scope-and-aircheck.md) | Границы проекта, совместимость API и связь регулирования с воздухообменом |

Проект рассчитан на монтаж из готовых модулей. Питание, защиту и порядок первого включения описывает [электрическая часть](hardware/design.md). Координаты опор и отверстий указаны в [документации корпуса](outputs/README.md). Физическую посадку и работу собранного оборудования проверяют при изготовлении первого образца.

## Алгоритм

- Вентилятор включается при CO₂ от **1000 ppm** и выключается ниже **800 ppm** после минимум **5 минут** работы. Между порогами состояние сохраняется.
- Ошибка датчика или возраст последнего достоверного измерения **15 секунд** выключают вентилятор. Последнее измерение сохраняет собственное время.
- Отсутствие подтверждённых оборотов в диапазоне **200–2500 об/мин** в течение **5 секунд** при включённом выходе выключает вентилятор и фиксирует отказ до перезапуска. Запрос включения и обороты передаются отдельно.
- Сетевой обмен работает в отдельной задаче. После восстановления связи отправляется свежий снимок.

Назначения выводов и интервалы сведены в [профиль](hardware/profile.json). Обработчик слов SCD41 адаптирован из [прошивки AirCheck на ревизии 206310c](https://github.com/Garun-mp4/air_check_system/tree/206310cd90ad6bce6674cb274b1d3e9faa26afbb/firmware/esp32/src).

## Сборка ESP32 на Windows

Нужны Python 3.12 и PowerShell. Скрипт переносит исходники во временный ASCII-путь и сохраняет артефакты в `build/esp32`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build-esp32.ps1
```

Прошивка одна для автономной и сетевой работы. При пустой NVS силовой выход заблокирован. Для работы с платой подготовить копию [шаблона настроек](hardware/device-settings.example.json) вне репозитория. Указать SSID, пароль WPA2, адрес HTTPS сервера без пути, токен, файл доверенного корневого сертификата и при необходимости `ntp_server`. По умолчанию для времени используется `pool.ntp.org`. Для автономной работы секцию `connection` удалить целиком. На стороне AirCheck нужен приём `real` для `DEVICE_ID=sapr-room-01`.

```powershell
.\.venv\Scripts\python.exe scripts/provision.py --config 'C:\sapr-private\device.json' --out 'C:\sapr-private\sapr-nvs.bin'
```

Скрипт формирует приватный образ NVS объёмом 24 КиБ. Плата программируется отдельно. Образ записывают в раздел NVS со смещением `0x9000` на выделенной плате САПР. Запись заменяет содержимое этого раздела. Сначала используют `commissioned: false`, а после [проверки монтажа](hardware/design.md#контроль-перед-подключением-нагрузки) формируют новый образ с `commissioned: true`. Силовой выход также требует успешной инициализации I²C и счётчика тахометра.

## Демонстрация

Для симулятора нужен компилятор C++17. На Windows используется Ubuntu в WSL.

```powershell
wsl -d Ubuntu -- sh scripts/build-host.sh
python scripts/demo.py --wsl
```

Сценарий 700 → 1050 → 900 → 750 ppm проверяет включение, подтверждение оборотов, удержание и остановку после выдержки. Время модели ускорено. Отказы датчика и тахометра прогоняются отдельно. C++-ядро и формат телеметрии общие с прошивкой.

### Проверка с AirCheck

Нужны локальный репозиторий AirCheck, Node.js, npm и PostgreSQL в Ubuntu WSL. Скрипт запускает копию ревизии `206310c` на `127.0.0.1:3130`. У неё отдельная база на порту 55432. По умолчанию берётся PostgreSQL 18. Другую установленную версию можно передать через `-PostgresVersion`.

В первом окне из папки курсового выполнить команду и указать локальную папку репозитория AirCheck.

```powershell
pwsh -NoProfile -File scripts/aircheck-stand.ps1 -Action Start -AirCheckRepository 'ПОЛНЫЙ_ПУТЬ_К_ПАПКЕ_ВКР\Проект'
```

Во втором окне запустить:

```powershell
wsl -d Ubuntu -- sh scripts/build-host.sh
.\scripts\aircheck-stand.ps1 -Action Demo
```

Сценарий отправляет кадры `data_source=simulator` и сверяет их с [сырым снимком AirCheck](http://127.0.0.1:3130/api/v1/telemetry). Три отсутствующих датчика передаются как `unknown` со значениями `null`. Для остановки сервера нажать Ctrl+C в первом окне.

## Сверка материалов

Выполнить из корня проекта с KiCad 9 и Python после создания каталога `build`.

```powershell
wsl -d Ubuntu -- kicad-cli sch erc --exit-code-violations -o build/electrical-erc.rpt hardware/SAPR-001-E3.kicad_sch
wsl -d Ubuntu -- kicad-cli sch export netlist --format kicadxml -o build/electrical-netlist.xml hardware/SAPR-001-E3.kicad_sch
python scripts/check-profile.py build/electrical-netlist.xml
```

Для повторного выпуска печатных листов нужны ReportLab и шрифт ГОСТ типа Б (`GOST_BU.ttf`). На настроенной машине запустить `python scripts/electrical_docs.py` и `python scripts/drawings.py`. Исходник Э3 открывается в KiCad с рамкой `hardware/SAPR-001-ESKD.kicad_wks`. Для печати PDF выбрать масштаб 100%. DWG сохранён в AC1032 в миллиметрах. [Аудит CAD](outputs/cad-audit.json)

## Выпуск Э3, версия 03

После генерации рамки и ПЭ3 из каталога проекта экспортировать Э3 из KiCad 9.0.8. Шрифт `GOST Type BU` должен быть доступен среде, где работает KiCad. Второй скрипт удаляет JavaScript экспорта и восстанавливает поиск по кириллице без изменения печатной графики. [Ревизия Э3 и критерии приёмки](tests/review-E3-R03.md)

```powershell
.\.venv\Scripts\python.exe -m pip install pypdf==7.1.1
wsl -d Ubuntu -- kicad-cli sch export pdf --black-and-white --exclude-pdf-property-popups --exclude-pdf-hierarchical-links --default-font 'GOST Type BU' --drawing-sheet hardware/SAPR-001-ESKD.kicad_wks -o build/e3-raw.pdf hardware/SAPR-001-E3.kicad_sch
.\.venv\Scripts\python.exe scripts/finalize-e3-pdf.py build/e3-raw.pdf hardware/SAPR-001-E3.pdf
```
