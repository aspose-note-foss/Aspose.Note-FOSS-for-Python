# План реализации Python-библиотеки для формата MS OneStore (.one/.onetoc2)

Цель: реализовать Python-библиотеку для **чтения** (и затем, опционально, записи) формата OneNote Revision Store File Format по [MS-ONESTORE].

В этом плане:
- сначала — «железобетонный» бинарный слой и безопасное чтение,
- затем — сборка FileNodeList/TransactionLog,
- затем — обход object spaces/revisions/objects,
- далее — декодирование PropertySet и вложений,
- параллельно — тесты (unit + интеграционные на файле `SimpleTable.one`).

## 0) Принципы и границы проекта

Полезные “точки входа” в описание формата:
- общий порядок и вехи: [00-roadmap.md](00-roadmap.md)
- базовый ридер и битполя: [01-binary-reader.md](01-binary-reader.md)
- общие типы (GUID/CompactID/строки/fcr): [02-common-types.md](02-common-types.md)
- заголовок и “reachable blocks”: [03-header.md](03-header.md)
- минимальные MUST-проверки и набор тестов: [13-validation.md](13-validation.md)

**Основные принципы**
- Безопасность чтения: ни одного чтения за пределы файла/чанка.
- Детерминизм: повторный парсинг даёт один и тот же результат (по стабильным ID/структурам).
- Два режима: `strict` (падает на MUST-нарушениях) и `tolerant` (warnings + best-effort).
- «Структуры отдельно от смысла»: [MS-ONESTORE] (структурный слой) не обязан сразу понимать семантику [MS-ONE].

**Что считаем “готовым ридером v1”**
- Полный проход от `Header` до object spaces/revisions/objects.
- Возможность извлечь (декодировать) `PropertySet` для объектов.
- Базовая резолюция file data по `<ifndf>`.
- Набор валидаций из [13-validation.md](13-validation.md) (минимум MUST).

**Не-цели первых итераций (чтобы не застрять)**
- Полная интерпретация всех PropertyID по [MS-ONE].
- Полная поддержка encrypted object spaces (пока: распознавать и помечать, данные игнорировать).
- Полная реализация writer (план есть, но делать после стабильного ридера).

## 1) Предлагаемая структура пакета и публичный API

### 1.1 Пакеты/модули
Рекомендуемая структура (под `src/`):
- `onestore/errors.py` — `OneStoreFormatError`, `OneStoreWarning`, `ParseWarning`.
- `onestore/io.py` — `BinaryReader`, `BoundedReader/view`, утилиты битполей.
- `onestore/common_types.py` — `ExtendedGUID`, `CompactID`, GUID helpers, `StringInStorageBuffer`.
- `onestore/chunk_refs.py` — `FileChunkReference32/64/64x32`, `FileNodeChunkReference` (+ decode по форматам).
- `onestore/crc.py` — CRC для `.one` (RFC3309) и `.onetoc2` (MsoCrc32Compute; сейчас не реализован) + тестовые вектора.
- `onestore/header.py` — `Header`.
- `onestore/txn_log.py` — `TransactionLogFragment`, `TransactionEntry`, `CommittedListState`.
- `onestore/file_node_list.py` — `FileNodeListHeader`, `FileNodeListFragment`, сборка списков по цепочке `nextFragment`.
- `onestore/file_node_core.py` — `FileNodeHeader`, `FileNode`, общий парсер.
- `onestore/file_node_types.py` — маршрутизация `FileNodeID -> typed` структуры, неизвестные узлы.
- `onestore/object_data.py` — `ObjectSpaceObjectPropSet`, потоки ссылок, `JCID`, `PropertyID`, `PropertySet`, контейнеры (2.6.8/2.6.9), декодер.
- `onestore/object_space.py` / `onestore/summary.py` — высокоуровневая модель: object spaces, revisions, объекты и сводки.
- `onestore/validate.py` — валидации MUST/SHOULD (разделить на уровни).

### 1.2 Публичный API (минимальный)
- `onestore.open(path, *, strict=True) -> OneStoreFile`
- `OneStoreFile.header`
- `OneStoreFile.object_spaces` (dict по `ExtendedGUID`)
- `ObjectSpace.revisions` (dict/list)
- `Revision.root_objects` (root_role -> object_id)
- `Revision.get_object(oid) -> ObjectState`
- `ObjectState.prop_set` (декодированные свойства + raw)
- `OneStoreFile.get_file_data(reference) -> bytes|None` (для `<ifndf>`)

### 1.3 Контекст парсинга
Ввести `ParseContext`:
- `strict: bool`
- `warnings: list[ParseWarning]`
- `file_size: int`
- `path: str|None`
- (опционально) `limits`: максимальная глубина/кол-во узлов для защиты от мусора.

## 2) Тестовая стратегия (обязательная часть)

### 2.1 Инструменты
- `unittest` (stdlib) как основной раннер.
- Snapshot-тесты (на ваш выбор):
  - либо `unittest` + собственная JSON-схема “summary” (предпочтительно, без доп. зависимостей),
  - либо сторонние snapshot-библиотеки (если ок доп. зависимости).

### 2.2 Два уровня тестов
1) **Unit**: байтовые “мини-файлы” через `struct.pack`, проверяют битполя/размеры/границы.
2) **Integration**: читают реальный файл `SimpleTable.one` и проверяют инварианты + snapshot сводки.

### 2.3 Фикстуры на `SimpleTable.one`
- В `unittest` вместо фикстур — общий helper/утилита для поиска `SimpleTable.one` в корне репозитория.
- Для повторного использования bytes — кешировать в `setUpClass`/модульной переменной.

### 2.4 Snapshot “summary” (ключ к стабильным интеграционным тестам)
Так как заранее неизвестны точные значения (кол-во объектов/ревизий/свойств), план такой:
- Добавить утилиту `tools/dump_simpletable_summary.py`, которая:
  - парсит `SimpleTable.one`,
  - возвращает JSON с **устойчивыми** данными: GUID/OSID/RID, counts, перечни FileNodeID встреченных типов, размеры чанков.
- Сохранить эталон в `tests/snapshots/simpletable_summary.json`.
- Интеграционные тесты сравнивают текущее значение summary с эталоном.

Рекомендация: добавлять поля в summary только когда они стабильно поддержаны (иначе snapshot будет постоянно меняться).

## 3) Пошаговые итерации реализации

Каждый шаг содержит: **что сделать**, **критерии готовности**, **тесты**.

### Шаг 1 — Каркас проекта + базовая инфраструктура
**Сделать**
- Завести пакет `onestore` (src-layout), настроить `pyproject.toml`.
- Настроить запуск тестов через `unittest` (VS Code + `python -m unittest discover`).
- Принять соглашение об исключениях и warnings.

**Готово, если**
- `python -m unittest discover -s tests -p "test_*.py"` запускается.
- Можно импортировать `onestore`.

**Тесты**
- `test_imports_smoke`.

### Шаг 2 — `BinaryReader` и bounded views
См. [01-binary-reader.md](01-binary-reader.md).

**Сделать**
- `BinaryReader` (cursor-based): `read_u8/u16/u32/u64`, `read_bytes(n)`, `seek/tell`.
- `BoundedReader/view(offset, size)` — читает только внутри диапазона.
- Унифицированные проверки границ с исключением `OneStoreFormatError(offset=...)`.
- Хелпер для битполей: `read_u32_bits(widths)`/`unpack_bits(value, widths)`.

**Готово, если**
- Любая попытка выйти за пределы вызывает предсказуемую ошибку с offset.

**Тесты (unit)**
- чтение примитивов little-endian,
- view не даёт выйти за пределы,
- битполя распаковываются в нужном порядке.

### Шаг 3 — Common types: GUID/ExtendedGUID/CompactID/строки/chunk refs
См. [02-common-types.md](02-common-types.md).

**Сделать**
- `ExtendedGUID` (guid bytes16 + n u32).
- `CompactID` (n + guidIndex).
- `StringInStorageBuffer` (u32 cch + UTF-16LE bytes).
- `FileChunkReference*` (32/64/64x32), `fcrNil/fcrZero`.
- `FileNodeChunkReference` декодер по StpFormat/CbFormat (включая умножение на 8 для compressed).

**Готово, если**
- Все базовые типы парсятся автономно.

**Тесты (unit)**
- CompactID unpack,
- UTF-16LE строки (в т.ч. с `\u0000` на конце),
- fcrNil/fcrZero,
- все варианты StpFormat/CbFormat на наборе примеров.

### Шаг 4 — `Header` + базовые MUST-проверки
См. [03-header.md](03-header.md) и [13-validation.md](13-validation.md).

**Сделать**
- `Header.parse(reader, ctx)`.
- Валидации: `guidFileFormat`, `cTransactionsInLog != 0`, обязательные fcr, legacy/debug поля.
- Нормализация ссылок + проверка `stp+cb <= file_size` (кроме nil/zero).

**Готово, если**
- `Header` читается на `SimpleTable.one`.

**Тесты**
- unit: негативные кейсы (неверный guidFileFormat, out-of-bounds fcr).
- integration (`SimpleTable.one`):
  - парсится header,
  - `guidFileType` соответствует `.one`,
  - `fcrFileNodeListRoot`/`fcrTransactionLog` валидны.

### Шаг 5 — Transaction Log: “сколько узлов коммитнуто”
См. [05-transaction-log.md](05-transaction-log.md).

**Сделать**
- Парсер `TransactionLogFragment` по цепочке `nextFragment`.
- Разбиение на транзакции по sentinel (`srcID==1`).
- Ограничение по `Header.cTransactionsInLog`.
- Результат: `last_count_by_list_id: dict[int, int]`.

**Готово, если**
- Для `SimpleTable.one` получается непустой `last_count_by_list_id`.

**Тесты**
- unit: поток entries с 2 транзакциями, игнор хвоста.
- integration: лог читается, `cTransactionsInLog` транзакций учитываются.

### Шаг 6 — FileNodeListFragment + сборка логических списков
См. [06-file-node-list.md](06-file-node-list.md).

**Сделать**
- Парсер `FileNodeListFragment` в режиме “читать границы + извлекать file nodes stream как bytes/итератор”.
- Учёт позиции `nextFragment` по `cb` фрагмента.
- Склейка фрагментов в логический список по `(FileNodeListID, nFragmentSequence)`.
- Применение лимита `last_count_by_list_id[list_id]`.

**Готово, если**
- Можно собрать root file node list и пройти её узлы.

**Тесты**
- unit: синтетический фрагмент с padding, nextFragment на фиксированной позиции.
- integration: логический список собирается по цепочке `nextFragment`, начиная от `Header.fcrFileNodeListRoot`.

### Шаг 7 — FileNode core: заголовок/размер/base_type/dispatch
См. [07-file-node-core.md](07-file-node-core.md).

**Сделать**
- `FileNodeHeader` bit-unpack.
- Общий `parse_filenode(reader, ctx, container_limit)`.
- `BaseType` обработка (0 без ref; 1/2 с FileNodeChunkReference).
- Реестр парсеров `FileNodeID -> handler`, unknown handler сохраняет raw.

**Готово, если**
- Поток `FileNode` из root list парсится в список узлов.

**Тесты**
- unit: unpack битполей + `Size` контроль.
- integration: в root list нет out-of-bounds и корректно читаются node sizes.

### Шаг 8 — Root File Node List: object spaces + file data store list
См. [16-root-file-node-list.md](16-root-file-node-list.md) и [08-file-node-types-manifests.md](08-file-node-types-manifests.md).

**Сделать**
- Реализовать FileNode типы для root list:
  - `0x008 ObjectSpaceManifestListReferenceFND` (BaseType=2),
  - `0x004 ObjectSpaceManifestRootFND`,
  - `0x090 FileDataStoreListReferenceFND`.
- Строгое ограничение “root list содержит только эти типы” (strict mode).
- Построить `OneStoreFile.object_spaces` со ссылками на manifest lists.

**Готово, если**
- На `SimpleTable.one` извлекаются object spaces и root OSID.

**Тесты (integration)**
- root list содержит только разрешённые FileNodeID,
- `gosidRoot` совпадает с одним из `gosid`.

### Шаг 9 — ObjectSpace manifest list + Revision manifest list ссылки
См. [08-file-node-types-manifests.md](08-file-node-types-manifests.md).

**Сделать**
- Типы:
  - `0x00C ObjectSpaceManifestListStartFND`,
  - `0x010 RevisionManifestListReferenceFND` (BaseType=2),
  - `0x014 RevisionManifestListStartFND`.
- Правило “если ссылок больше одной — использовать последнюю”.
- Построить модель: `ObjectSpace.revision_manifest_list_ref`.

**Готово, если**
- На `SimpleTable.one` для каждого object space находится revision manifest list.

**Тесты (integration)**
- для каждого object space manifest list присутствует StartFND,
- выбирается последняя `RevisionManifestListReferenceFND`.

### Шаг 10 — Revision manifests: Start/End + role/context declarations
См. [08-file-node-types-manifests.md](08-file-node-types-manifests.md) и [17-revision-manifest-parsing.md](17-revision-manifest-parsing.md).

**Сделать**
- Реализовать:
  - `RevisionManifestStart6FND (0x01E)` и `Start7FND (0x01F)` для `.one`,
  - `RevisionManifestEndFND (0x01C)`,
  - `RevisionRoleDeclarationFND (0x05C)`,
  - `RevisionRoleAndContextDeclarationFND (0x05D)`,
  - `ObjectDataEncryptionKeyV2FNDX (0x07C)` (как маркер; данные можно игнорировать).
- Линейный парсер revision manifest list, который выделяет границы каждого manifest.
- Контекст “последнее присваивание” для (context, role).

**Готово, если**
- Можно перечислить revisions для object space и их зависимости `ridDependent`.

**Тесты**
- unit: последовательность Start..End обязана быть корректной.
- integration: на `SimpleTable.one` находится хотя бы один revision manifest, и все они заканчиваются End.

### Шаг 11 — Global Identification Table (scope-aware)
См. [09-file-node-types-global-id-table.md](09-file-node-types-global-id-table.md).

**Сделать**
- Типы `.one`:
  - `0x022 GlobalIdTableStart2FND` (no data),
  - `0x024 GlobalIdTableEntryFNDX`,
  - `0x028 GlobalIdTableEndFNDX`.
- Контекстная область действия таблицы (сброс на End/Start/RevisionEnd).
- Пометка: для `.onetoc2` поддержать 0x021/0x025/0x026 позже.

**Готово, если**
- CompactID начинают резолвиться в ExtendedGUID в пределах revision manifest.

**Тесты**
- unit: простая таблица + пару CompactID.
- integration: на `SimpleTable.one` встречается таблица (если есть) и применяется без ошибок.

### Шаг 12 — Object declarations/revisions + root objects + overrides
См. [10-file-node-types-objects.md](10-file-node-types-objects.md).

**Сделать**
- Реализовать ключевые узлы:
  - `0x02D/0x02E` ObjectDeclarationWithRefCount*,
  - `0x041/0x042` ObjectRevisionWithRefCount*,
  - `0x05A` RootObjectReference3FND,
  - `0x084` ObjectInfoDependencyOverridesFND (+ парсинг override data inline/ref).
- Построить “сырой” список изменений объектов в каждом revision manifest.
- Реализовать построение итогового состояния revision с учётом dependency (топологический порядок).

**Готово, если**
- Можно получить `Revision.root_objects` и список объектов, изменённых в revision.

**Тесты (integration)**
- root objects присутствуют (или явно пусто, если так в файле),
- dependency цепочки разрешаются без циклов.

### Шаг 13 — ObjectSpaceObjectPropSet + PropertySet + декодирование значений
См. [12-object-data.md](12-object-data.md) и [18-property-containers.md](18-property-containers.md).

**Сделать**
- Парсер `ObjectSpaceObjectPropSet`:
  - потоки `OIDs/OSIDs/ContextIDs` с корректными флагами header.
- Парсер `JCID`, `PropertyID`, `PropertySet`.
- Контейнеры:
  - `prtFourBytesOfLengthFollowedByData` (2.6.8),
  - `prtArrayOfPropertyValues` (2.6.9) (как массив вложенных PropertySet).
- Декодер `PropertySet` в “typed-ish” значения:
  - фиксированные типы 1/2/4/8,
  - blobs,
  - ссылки через OIDs/OSIDs/ContextIDs,
  - дочерние property sets.

**Готово, если**
- Для объектов из `SimpleTable.one` можно извлечь набор свойств (как минимум raw + структурно корректно).

**Тесты**
- unit: property set с миксом типов + проверка смещений чтения.
- integration: хотя бы один объект успешно декодируется; декодер детерминирован.

### Шаг 14 — FileDataStore и резолюция `<ifndf>`
См. [11-file-node-types-file-data.md](11-file-node-types-file-data.md).

**Сделать**
- Реализовать `0x094 FileDataStoreObjectReferenceFND` и парсер `FileDataStoreObject`.
- Построить индекс `guidReference -> (stp,cb)`.
- Реализовать разбор строк `<ifndf>{GUID}</ifndf>` и возврат bytes.
- Для `<file>` возвращать метаданные (путь/имя), без обязательной загрузки внешнего файла.

**Готово, если**
- Если в `SimpleTable.one` есть `<ifndf>`, можно извлечь bytes вложения.

**Тесты (integration)**
- если file data store list присутствует — все `guidReference` уникальны,
- извлечение по `<ifndf>` работает (для выбранного примера из snapshot).

### Шаг 15 — Hashed chunk list (MD5) + дополнительная валидация
См. [15-hashed-chunk-list.md](15-hashed-chunk-list.md) и [13-validation.md](13-validation.md).

**Сделать**
- Парсить `Header.fcrHashedChunkList` и список `0x0C2 HashedChunkDescriptor2FND`.
- (Опционально) валидировать MD5 содержимого blob.
- Добавить валидации уровней:
  - Level 1: границы/магии/инварианты,
  - Level 2: CRC/MD5 (по флагу).

**Готово, если**
- Парсер не падает при наличии/отсутствии hashed chunk list.

**Тесты (integration)**
- если список есть — хотя бы 1 элемент; MD5 совпадает (если включили).

### Шаг 16 — Snapshot-тесты на `SimpleTable.one` как регрессия
**Сделать**
- Реализовать `tools/dump_simpletable_summary.py`.
- Зафиксировать `tests/snapshots/simpletable_summary.json`.

**Summary-рекомендации (поля)**
- header: `guidFileType`, `cTransactionsInLog`, наличие fcr*.
- root list: список object spaces (OSID), root OSID.
- по каждому OSID: count revision manifests, список RID, dependency RID.
- counts: количество объектов (unique OID) по каждому revision.
- статистика FileNodeID: set/частоты.
- file data store: count объектов и перечень guidReference.

**Готово, если**
- `python -m unittest -v tests.test_integration_simpletable` стабильно проходит и ловит регрессии.

## 4) Опциональный этап: Writer (после стабилизации ридера)

Реализовывать только после шагов 1–16.

### Шаг W1 — Append-only writer skeleton
См. [19-writer-basics.md](19-writer-basics.md).
- Аллокатор: append-only (без free list на первом этапе).
- Запись Transaction Log + инкремент `cTransactionsInLog`.

### Шаг W2 — Минимальные операции
См. [20-writer-structures.md](20-writer-structures.md).
- Добавить новый `ObjectSpaceObjectPropSet` blob.
- Добавить `ObjectRevisionWithRefCount*` в revision manifest list.
- Коммит транзакции.

## 5) Рекомендуемый порядок реализации (коротко)
1) IO + types + Header
2) TransactionLog + FileNodeListFragment
3) FileNode core + root list
4) manifests + revision parsing + GID table
5) objects + prop sets
6) file data + hashed chunks + validation
7) snapshot/regression
8) writer (опционально)
