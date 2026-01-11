# Python implementation plan: MS-ONE entities reader (поверх MS-ONESTORE)

## Цель

Реализовать слой чтения **сущностей [MS-ONE]** (Section/Page/Outline/… и связанных типов) из `.one/.onetoc2`, опираясь на уже реализованное чтение **контейнера [MS-ONESTORE]** (`src/onestore/*`).

Входные источники:

- `ms-one_spec_structure.txt` — outline + extracted text из `[MS-ONE].pdf` (список JCID, PropertyID, структуры и взаимные ссылки).
- `docs/ms-onestore/*` и `src/onestore/*` — уже готовая реализация чтения OneStore: header → file node lists → object spaces/revisions → object data/property sets → file data store.

Выход (v1):

- API, которое позволяет получить:
  - объектную модель (минимально: Section → PageSeries → Page → Outline → OutlineElement → content nodes),
  - метаданные (названия, цвета, timestamps, IDs),
  - доступ к embedded-file/file-data (через `FileDataStore`).

Нефункциональные требования (как у `onestore`):

- детерминированность вывода (стабильный порядок),
- строгий/толерантный режим (`ParseContext(strict=...)` совместимый),
- понятные ошибки на MUST-нарушениях.

## Архитектура (слои)

1) **onestore (уже есть):** дешифровка контейнера [MS-ONESTORE], включая:
   - объектные пространства (object spaces),
   - ревизии (revision manifests),
   - глобальную таблицу GUID (Global ID Table),
   - чтение `ObjectSpaceObjectPropSet` и `DecodedPropertySet`,
   - чтение `FileDataStoreObject`.

2) **MS-ONE graph extraction (новое):**
   - выбор “актуальной” ревизии object space (обычно последняя коммитнутая),
   - построение индекса `OID -> object (JCID + DecodedPropertySet + raw refs)` для ревизии,
   - резолв `CompactID -> ExtendedGUID` через effective GID table ревизии.

3) **MS-ONE entities (новое):**
   - маппинг JCID index → тип сущности ([MS-ONE] раздел 2.2.*),
   - маппинг PropertyID value → семантика/тип значения ([MS-ONE] раздел 2.1.12 и таблицы PropertyID),
   - построение графа сущностей через properties вида `*ChildNodes*`, `ObjectSpace*`, `*MetaData*`, `*Manifest*`.

## План по файлам

Ниже план в разрезе файлов, которые нужно добавить/изменить.

### `docs/ms-one/00-entity-scope.md` (новый)

Зачем:
- зафиксировать “что именно читаем” в v1 (минимальный набор сущностей и свойств), чтобы не расползтись по всей спецификации сразу.

Что сделать:
- перечислить поддерживаемые сущности (JCID) для v1:
  - `jcidSectionNode`, `jcidPageSeriesNode`, `jcidPageNode`, `jcidOutlineNode`, `jcidOutlineElementNode`,
  - content nodes: `jcidRichTextOENode`, `jcidImageNode`, `jcidTableNode`, `jcidTableRowNode`, `jcidTableCellNode`,
  - metadata nodes: `jcidPageMetaData`, `jcidSectionMetaData`, `jcidPageManifestNode`,
  - опционально: conflict/version history (если встретится в `SimpleTable.one`, иначе deferred).
- описать политику деградации: unknown JCID/property → сохраняем как “unknown node” с raw properties.

Готово когда:
- есть список v1-целей + явно отмечено, что отложено.

### `tools/ms_one/extract_spec_ids.py` (новый, опционально но желательно)

Зачем:
- не поддерживать вручную большой список `PropertyID value` и `JCID` значений из `ms-one_spec_structure.txt`.

Что сделать:
- парсер `ms-one_spec_structure.txt`, который извлекает:
  - таблицу `jcid* <hex>` (пример: строки около “`jcidPageNode 0x0006000B …`”),
  - строки вида `<Name> 0x????????` из таблиц “Structure PropertyID value”.
- сохранить результат в:
  - `src/ms_one/_spec_ids_generated.py` (генерируемый модуль) или `docs/ms-one/spec-ids.json` (данные) + небольшой рантайм-лоадер.
- добавить “regen” инструкции в `docs/ms-one/README.md`.

Готово когда:
- можно воспроизвести генерацию без ручной правки значений.

### `src/ms_one/__init__.py` (новый)

Зачем:
- публичный API уровня MS-ONE, аналогично `src/onestore/__init__.py`.

Что сделать:
- экспортировать:
  - модели сущностей (dataclasses),
  - функции парсинга верхнего уровня: условно `parse_section_file(data)`, `parse_notebook_toc(data)` (если понадобится),
  - базовые типы ошибок.

Готово когда:
- `tests/test_imports_smoke.py` можно расширить импортом `ms_one` без побочных эффектов.

### `src/ms_one/errors.py` (новый)

Зачем:
- отделить ошибки семантического слоя MS-ONE от низкоуровневых OneStore ошибок.

Что сделать:
- `MSOneFormatError(Exception)` (с `offset`/`oid`/`osid` полями по необходимости),
- `MSOneWarning` (если нужен tolerant режим, можно просто прокидывать `ParseContext.warn`).

Готово когда:
- ошибки из MS-ONE слоя легко отличимы от `OneStoreFormatError`.

### `src/ms_one/spec_ids.py` (новый; возможно генерируемый)

Зачем:
- единое место для констант:
  - JCID index значений для “известных сущностей”,
  - PropertyID value (полный u32) для ключевых свойств (`ElementChildNodesOfSection`, `SectionDisplayName`, …).

Что сделать:
- если есть генератор — подключить `from ._spec_ids_generated import ...`,
- иначе вручную зафиксировать минимальный набор для v1 (на базе `ms-one_spec_structure.txt`).

Готово когда:
- код entity layer не содержит “магических 0x…” в логике (кроме тестов/временной диагностики).

### `src/ms_one/compact_id.py` (новый)

Зачем:
- утилиты для резолва `CompactID -> ExtendedGUID` на базе effective GID table ревизии.

Что сделать:
- определить тип “таблица GUID” в удобном виде (например `dict[int, bytes]` как в `onestore.object_space`),
- реализовать:
  - `resolve_compact_id(compact_id, gid_table) -> ExtendedGUID`,
  - `resolve_oid_tuple(tuple[CompactID], gid_table) -> tuple[ExtendedGUID]`.
- продумать поведение при отсутствующем индексе (strict: error, tolerant: warning + zero GUID).

Готово когда:
- все связи в MS-ONE графе можно выражать в ExtendedGUID (без протекания CompactID наружу).

### `src/ms_one/property_access.py` (новый)

Зачем:
- удобный, типобезопасный доступ к свойствам `DecodedPropertySet` по “полным” PropertyID u32 из [MS-ONE].

Что сделать:
- хелперы:
  - `get_prop(pset, property_id_u32) -> DecodedProperty | None`,
  - `require_prop(pset, property_id_u32, *, msg=...)`,
  - `get_bool/get_u32/get_bytes/get_oid_array/...` поверх значений, которые возвращает `onestore.decode_property_set`.
- нормализовать сравнение:
  - либо по `PropertyID.raw`,
  - либо по паре `(prop_id, prop_type, bool_value)` — но проще по `raw` из таблиц [MS-ONE].

Готово когда:
- entity-парсеры не содержат ручного “пробега по списку properties”.

### `src/ms_one/types.py` (новый)

Зачем:
- декодирование MS-ONE “встроенных” типов из `bytes` контейнеров (`type=0x07` / `FourBytesOfLengthFollowedByData`).

Что сделать (минимум v1):
- функции чтения из `bytes` (через `onestore.BinaryReader`):
  - `GuidInAtom`, `WzInAtom` (UTF-16LE строка), `Color/COLORREF`, `Time32` (если встречается),
  - массивы (`ArrayOfUINT8s`, `ArrayOfUINT32s`, `ArrayOfGuids`) когда они реально нужны.
- договориться, какие типы возвращаем наружу (например `uuid.UUID`, `str`, `(r,g,b,a)` или int).

Готово когда:
- ключевые строковые/цветовые/Guid поля из Section/Page MetaData читаются без “сырого bytes” в API.

### `src/ms_one/object_index.py` (новый)

Зачем:
- получить в пределах одной ревизии object space быстрый доступ:
  - `OID -> объект (JCID + DecodedPropertySet + ref streams)`.

Что сделать:
- на вход: `data` файла + выбранный `ObjectSpaceResolvedIdsSummary`/`RevisionResolvedIdsSummary` из `onestore.parse_object_spaces_with_resolved_ids`,
- пройти object group lists и inline changes ревизии (см. `onestore.object_space` manifest summary) и собрать:
  - список объявленных/изменённых объектов,
  - для каждого — найти ссылку на `ObjectSpaceObjectPropSet` и распарсить/декодировать свойства (через `onestore.parse_object_space_object_prop_set_from_ref` + `decode_property_set`).
- хранить:
  - `objects_by_oid: dict[ExtendedGUID, ObjectRecord]`,
  - `objects_by_jcid: dict[int, list[ExtendedGUID]]` (для поиска root/meta объектов).

Готово когда:
- можно быстро “поднять” любой OID referenced в `*ChildNodes*` свойствах.

### `src/ms_one/entities/base.py` (новый)

Зачем:
- общий формат “узла графа” + возможность хранить unknown/неподдержанные ноды.

Что сделать:
- `@dataclass`:
  - `NodeId` (OID + object space id если нужно),
  - `BaseNode` (jcid_index, oid, raw_properties),
  - `UnknownNode(BaseNode)`.

Готово когда:
- entity layer может вернуть дерево даже при частично неизвестных узлах.

### `src/ms_one/entities/structure.py` (новый)

Зачем:
- модели “структурных” сущностей MS-ONE.

Что сделать (v1):
- `Section`, `PageSeries`, `Page`, `Outline`, `OutlineElement`,
- content nodes: `RichText`, `Image`, `Table`, `TableRow`, `TableCell`,
- metadata nodes: `PageMetaData`, `SectionMetaData`, `PageManifest`.

Готово когда:
- модели покрывают навигацию Section→Pages→Outline→Content.

### `src/ms_one/entities/parsers.py` (новый)

Зачем:
- код преобразования `ObjectRecord` (JCID+properties) → конкретный dataclass сущности.

Что сделать:
- функции `parse_*_node(record, index, gid_table, ctx) -> Entity`,
- чтение ссылок/детей через свойства:
  - `ElementChildNodesOfSection`, `ElementChildNodesOfPage`, `ElementChildNodesOfOutline`, `ElementChildNodesOfOutlineElement`,
  - `ContentChildNodesOfOutlineElement`, `ContentChildNodesOfPageManifest`, `ChildGraphSpaceElementNodes` и т.п. по мере необходимости.
- везде использовать `property_access.py` и `types.py`.

Готово когда:
- можно построить дерево сущностей без ручных “if/else” по месту.

### `src/ms_one/reader.py` (новый)

Зачем:
- единая точка входа: `bytes -> MS-ONE Document`.

Что сделать:
- энд-ту-энд пайплайн:
  1) `onestore.parse_object_spaces_with_revisions` / `...with_resolved_ids` (выбрать, что удобнее для v1),
  2) выбрать object space(ы) верхнего уровня (SectionObjectSpace / TOC) по root objects/JCID,
  3) выбрать ревизию (обычно последняя в списке; если нужно — учитывать `rid_dependent`),
  4) построить `ObjectIndex`,
  5) распарсить корневые сущности и собрать дерево.
- предусмотреть параметр: `strict/tolerant`.

Готово когда:
- `parse_section_file(SimpleTable.one)` возвращает Section-модель с именем/страницами/контентом (хотя бы частично).

### `tests/test_ms_one_simpletable.py` (новый)

Зачем:
- зафиксировать “минимально работающий” уровень MS-ONE поверх уже существующей интеграции `SimpleTable.one`.

Что сделать:
- тесты, которые проверяют:
  - парсер не падает на `SimpleTable.one`,
  - извлекаются базовые сущности (есть Section, хотя бы 1 Page),
  - ключевые строки не пустые (например `SectionDisplayName`, заголовок страницы — если доступен),
  - детерминированность (повторный парсинг даёт тот же JSON-дамп ключевых полей).
- при необходимости добавить `tests/snapshots/ms_one_simpletable.json`.

Готово когда:
- тест стабилен и не завязан на “полную” реализацию всех типов.

### `pyproject.toml` / `tests/test_imports_smoke.py` (возможные изменения)

Зачем:
- включить `ms_one` как пакет и гарантировать импорт.

Что сделать:
- убедиться, что `src/ms_one` попадает в импорты тестов так же, как `onestore`.

Готово когда:
- `pytest` проходит локально (без сетевых зависимостей).

## Порядок работ (milestones)

1) Скелет `ms_one` + базовые утилиты (`spec_ids`, `compact_id`, `property_access`).
2) `ObjectIndex` для одной ревизии object space (минимум: поднять объекты по OID и декодировать их PropertySet).
3) Парсеры сущностей “по дереву” (Section/Page/Outline/OutlineElement) + unknown nodes.
4) Декодирование наиболее нужных типов (`WzInAtom`, GUID, Color) для человекочитаемого вывода.
5) Интеграционные тесты на `SimpleTable.one` + снапшоты.

## Замечания по спецификации

- Источник идентификаторов:
  - JCID: таблица `jcid*` (см. около строк “`jcidPageNode 0x0006000B …`” в `ms-one_spec_structure.txt`).
  - PropertyID: таблицы “Structure PropertyID value” (пример: `SectionDisplayName 0x1C00349B`, `ElementChildNodesOfSection 0x24001C20`).
- Многие связи в MS-ONE выражены через свойства типа “OID array” (`PropertyID.type == 0x09`), которые `onestore.decode_property_set` уже возвращает как `tuple[CompactID, ...]`.

