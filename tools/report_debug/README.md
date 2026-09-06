# Отладка уже собранных отчётов

Инструменты вынесены из скриптов проверки `report_trace`. Пути к отчётам и
результатам передаются аргументами; фиксированных 320 айтемов, дат прогона,
учётных данных или путей к стенду в коде нет. Новая нагрузка и подключение к БД
для этих проверок не нужны.

Запускать из корня checkout `pg_diag`. Python-инструменты используют проектное
окружение: `python -m pip install -e '.[dev,browser]'`, для браузерных проверок —
`python -m playwright install chromium`. JS-инструментам нужен Node.js.
Каждая Python-команда поддерживает `--help`. Файлы результатов задаются явно.

| Инструмент | Назначение |
| --- | --- |
| `inventory.py` | Инвентаризация JSON/HTML, SHA256 и проверка сохранности по манифесту |
| `scan_reports.py` | Полнота, форма таблиц, NULL-колонки, интервалы, числа и временные ряды, сумма состояний CPU |
| `reconcile_metrics.py` | Пересчёт графиков из сохранённых snapshots, независимые проверки rate/ratio, ссылок на планы и запросы |
| `evaluate.cjs` | Оценки всех узлов по текущим исходникам, ошибки правил, непривязанные айтемы, расхождения одинаковых направлений |
| `summarize.py` | Матрица оценок, серые узлы с объяснениями, TSV и сравнение с предыдущими оценками |
| `browser_audit.py` | Загрузка HTML, быстрая проверка API навигации, lazy charts, просмотр auto_explain JSON/text/YAML/XML, сравнение с JSON-оценками |
| `navigation.py` | Обычные нажатия мыши: от свёрнутых корней через карточку до каждого айтема; фильтры и Full screen |
| `check_routes.cjs` | Все пунктирные связи: полные, частичные и смешанные раскрытия, карточки разной высоты |
| `browser_routes.js` | Проверка фактически отрисованных SVG-путей; используется `browser_audit.py --links` |
| `refresh_html.py` | Обновление четырёх блоков графа в одном HTML с проверкой неизменности остальных байтов разметки |
| `replay_logs.py` | Повторный прогон сохранённых CSV через local/shell scanner, сравнение счётчиков и полноты |
| `compare_logs.py` | Независимый CSV-подсчёт ошибок, предупреждений и auto_explain в явно заданном окне |

`common.py` содержит общие операции с файлами и встроенными ресурсами графа.
Проверки не изменяют входные отчёты. `refresh_html.py` — отдельная команда
записи; для обновления исходного HTML обязателен новый путь резервной копии.

## Обход каждого айтема и проверка стрелок

```bash
mkdir -p /tmp/pg-diag-debug
.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --expected-items 320 --output /tmp/pg-diag-debug/navigation.json

.venv/bin/python tools/report_debug/browser_audit.py /path/to/report.html \
  --links --animation --output /tmp/pg-diag-debug/browser-links.json

node tools/report_debug/check_routes.cjs \
  /path/to/report.json /tmp/pg-diag-debug/routes.json
```

`--expected-items` необязателен: по умолчанию обходится всё содержимое отчёта.
В протоколе каждого перехода есть путь от корня, ID узла и айтема, проверка
раскрытия раздела, видимости и фокуса заголовка. Это проверка реальных кнопок,
а не только наличия binding или вызова `navigateToItem`.

Для точечного повторения:

```bash
.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --item replication.replication_slots --output /tmp/pg-diag-debug/one-item.json

.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --node network.clients.capacity.sources.outcomes \
  --output /tmp/pg-diag-debug/one-card.json

.venv/bin/python tools/report_debug/browser_audit.py /path/to/report.html \
  --links --animation --node disk.space --node health.replication \
  --output /tmp/pg-diag-debug/two-nodes.json
```

Проверка ссылок проходит обе темы, выбор каждого конца связи, открытые и
закрытые карточки, частичное и полное раскрытие. Проверяются состав связей,
концы линий, маркеры стрелок, конечные координаты и пересечения видимой линии
с кругами и реально видимыми частями карточек. Во время анимации перекрытая
связь может временно исчезнуть; в устойчивом состоянии все уместные связи
должны быть видимыми. `check_routes.cjs` дополнительно проверяет 5520
статических маршрутов для текущих 23 связей, включая карточки до 2400 px.
В JSON также сохраняются все допустимые составы видимых связей с примерами
раскрытий: сейчас 35 наборов причинных стрелок или 39 с учётом Related checks,
включая пустой набор. Учитывается, что раскрытие родителя одновременно
показывает всех его непосредственных детей. Одновременно видны максимум
3 связи; количество геометрических вариантов этим не ограничивается.

## Проверка новой диагностики на нескольких отчётах

```bash
node tools/report_debug/evaluate.cjs /tmp/pg-diag-debug/before.json /path/to/*.json
# После изменения правил:
node tools/report_debug/evaluate.cjs /tmp/pg-diag-debug/after.json /path/to/*.json
.venv/bin/python tools/report_debug/summarize.py /tmp/pg-diag-debug/after.json \
  --before /tmp/pg-diag-debug/before.json --output-dir /tmp/pg-diag-debug/summary

.venv/bin/python tools/report_debug/browser_audit.py '/path/to/**/*.html' \
  --current-source --evaluation /tmp/pg-diag-debug/after.json \
  --output /tmp/pg-diag-debug/browser.json
```

Без `--current-source` проверяются скрипты, уже встроенные в HTML. С флагом
текущие исходники подставляются только в памяти браузера. `--evaluation`
сопоставляет цвета, факты, причины и ограничения с результатом оценки
соседнего JSON. Выходной файл оценки содержит все узлы; его можно сохранять
как baseline перед следующей правкой.

При необходимости `scan_reports.py --secret-file FILE` ищет известный секрет
в JSON и соседнем HTML. FILE содержит один секрет либо JSON с полями
`password`; значения секретов в протокол не попадают. Проверка суммы CPU
требует всех пяти состояний; скрытые нули учитываются только при явном
`zero_series` без пропусков с совпадающим числом наблюдений.

Классификация серых узлов в `summarize.py` — эвристика для разбора. Источником
объяснения остаётся поле `hints`. Найденные scan/reconcile расхождения тоже
требуют разбора: например, агрегированный CPU может превышать 100%, а старый
отчёт может быть собран с предыдущей версией формул.

```bash
.venv/bin/python tools/report_debug/inventory.py '/path/to/*.json' '/path/to/*.html' \
  --output /tmp/pg-diag-debug/manifest.json
.venv/bin/python tools/report_debug/scan_reports.py '/path/to/*.json' \
  --output-dir /tmp/pg-diag-debug/scan
.venv/bin/python tools/report_debug/reconcile_metrics.py '/path/to/*.json' \
  --output /tmp/pg-diag-debug/reconciliation.json
.venv/bin/python tools/report_debug/inventory.py \
  --verify /tmp/pg-diag-debug/manifest.json --output /tmp/pg-diag-debug/preservation.json
```

Для повторного рендера всего отчёта используется штатная команда
`pg-diag render --from-json INPUT.json --out NEW.html`; для проверки схемы —
`pg-diag validate-artifact INPUT.json`. Для обновления только графа:

```bash
.venv/bin/python tools/report_debug/refresh_html.py /path/to/report.html \
  --backup /tmp/pg-diag-debug/report-before.html
# Либо сохранить обновлённую копию:
.venv/bin/python tools/report_debug/refresh_html.py /path/to/report.html \
  --output /tmp/pg-diag-debug/report-current.html
```

## Проверка сохранённых логов

```bash
.venv/bin/python tools/report_debug/replay_logs.py /path/to/report.json /path/to/primary.csv \
  --from '2026-09-05 19:32:12' --to '2026-09-05 19:54:12' \
  --output /tmp/pg-diag-debug/log-replay.json

.venv/bin/python tools/report_debug/compare_logs.py /path/to/report.json /path/to/primary.csv \
  --from '2026-09-05T19:32:12Z' --to '2026-09-05T19:54:12Z' \
  --output /tmp/pg-diag-debug/log-comparison.json
```

`replay_logs.py` принимает время в часовом поясе серверного лога, как scanner.
Независимый `compare_logs.py` требует явные UTC-offsets и нормализует их.
Окно не выводится из последней строки неполного сбора. Сравнивать счётчики
нужно с учётом `coverage`, top-N и списка собранных айтемов. Replay использует
текущие лимиты scanner и полную детализацию auto_explain; уменьшение деталей
не применяется.
Если известен настроенный лимит планов на минуту, `compare_logs.py
--top-per-minute N` также сопоставляет маркеры планов с независимой выборкой
наиболее долгих планов из CSV и сохраняет отсутствующие/лишние точки.

## Происхождение и границы

Сюда перенесены возможности временных `audit.cjs`, `browser_audit.py`,
`click_all_320.py`, `check_navigation_fullscreen.py`, `refresh_html.py`,
`write_audit.py`, `write_navigation_summary.py`, а также проверок
`deep_scan.py`, `reconcile.py`, `raw_compare.py`, `replay_log_sources.py`,
`render_and_browser.py`, `final_checks.py` из `report_trace/review`. Дублирующие проверки
инвентаризации, полноты и браузера объединены в команды выше; итоговые
протоколы хранятся вне исходников. Одноразовое исправление конкретных старых
данных заменено проверкой расхождений без записи в артефакт.

Код выхода 1 у navigation/browser/routes/evaluate/replay/inventory-verify
означает провал проверки. Scan/reconcile/summarize сохраняют кандидатов и
матрицы для ручного разбора. Сбой чтения/парсинга также завершает команду с
ошибкой. Скрипты следует запускать обычным Python, без `-O`, поскольку часть
проверок оформлена как assertions.
