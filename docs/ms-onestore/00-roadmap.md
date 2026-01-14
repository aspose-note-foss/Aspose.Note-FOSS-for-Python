# Дорожная карта реализации [MS-ONESTORE] на Python

Ниже — последовательность шагов, которая позволяет «не утонуть» в формате и получать работоспособность итеративно.

## Итерация 0: каркас проекта

1. Спроектируйте пакеты (пример):
   - `onestore/io.py` — `BinaryReader`, ошибки, границы, чтение битполей.
   - `onestore/common_types.py` — `ExtendedGUID`, `CompactID`, `JCID`, строки.
   - `onestore/chunk_refs.py` — `FileChunkReference*`.
   - `onestore/header.py` — `Header`.
   - `onestore/file_node_list.py` — `FileNodeListFragment` и сборка логического списка через цепочку `nextFragment`.
   - `onestore/file_node_core.py` — `FileNode` (битовые поля) и `FileNodeChunkReference`.
   - `onestore/file_node_types.py` — маршрутизация `FileNodeID -> TypedFileNode`.
   - `onestore/object_space.py` / `onestore/summary.py` / `onestore/object_data.py` — object spaces, revisions, objects, property sets.
2. Введите единый тип исключений: `OneStoreFormatError` (с полем `offset`).
3. Сразу решите стратегию:
   - «строгий режим» (падает на нарушении MUST)
   - «толерантный режим» (пишет warnings, но возвращает частичные данные)

## Итерация 1: чтение заголовка и доступ к блокам

Готово, если:
- `Header` читается и валидируется по magic GUID/константам;
- chunk references (`fcr...`) приводятся к `(stp, cb)` и проверяются на выход за файл;
- вы умеете читать «достижимые блоки» от указателей в `Header` (и игнорировать недостижимое).

См. `docs/ms-onestore/03-header.md`.

## Итерация 2: FileNodeListFragment + Transaction Log

Готово, если:
- вы можете собрать root file node list от `Header.fcrFileNodeListRoot` и читать фрагменты по цепочке `nextFragment`;
- вы умеете восстановить **логические** file node lists (склеить фрагменты по `FileNodeListID`);
- вы применяете ограничение из `Transaction Log`: количество узлов в списке = значение из последней транзакции, которая его модифицировала;
- вы корректно обрабатываете `ChunkTerminatorFND` и `nextFragment`.

См. `docs/ms-onestore/05-transaction-log.md`, `docs/ms-onestore/06-file-node-list.md`.

## Итерация 3: FileNode core + базовые FileNode типы

Готово, если:
- вы парсите `FileNode` битовые поля (FileNodeID/Size/StpFormat/CbFormat/BaseType/Reserved);
- вы умеете прочитать `FileNodeChunkReference` в зависимости от StpFormat/CbFormat;
- вы умеете маршрутизировать `fnd` по `FileNodeID` на парсер конкретного типа.

См. `docs/ms-onestore/07-file-node-core.md`.

## Итерация 4: манифесты object spaces и revisions

Готово, если:
- вы строите «скелет» дерева: object spaces -> revision manifest lists -> revision manifests;
- вы поддерживаете все варианты `RevisionManifestStart*` и связанные декларации ролей/контекстов;
- вы корректно обрабатываете `GlobalIdTable` области действия.

См. `docs/ms-onestore/08-file-node-types-manifests.md`, `docs/ms-onestore/09-file-node-types-global-id-table.md`.

## Итерация 5: объекты, данные объектов, PropertySet

Готово, если:
- вы собираете объявления/ревизии объектов, refcount и root objects;
- вы читаете `ObjectSpaceObjectPropSet` (OIDs/OSIDs/ContextIDs + `PropertySet`);
- вы корректно «распаковываете» свойства-ссылки (ObjectID/OSID/ContextID и их массивы).

См. `docs/ms-onestore/10-file-node-types-objects.md`, `docs/ms-onestore/12-object-data.md`.

## Итерация 6: FileDataStore и бинарные вложения

Готово, если:
- вы читаете список file data store references;
- вы разрешаете `<ifndf>` ссылки на `FileDataStoreObject` и умеете извлечь `FileData`.

См. `docs/ms-onestore/11-file-node-types-file-data.md`.

## Итерация 7: валидация и совместимость

Готово, если:
- CRC/MD5 проверки реализованы (по возможности);
- добавлены минимальные тесты на распаковку битполей и корректные размеры структур;
- парсер стабильно работает на наборе реальных файлов (хотя бы «прочитать дерево» без извлечения всего содержимого).

См. `docs/ms-onestore/13-validation.md`.

