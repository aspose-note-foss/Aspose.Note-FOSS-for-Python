# [MS-ONESTORE] — инструкции по реализации на Python

Цель: пошагово реализовать **чтение** (и затем запись) OneNote Revision Store File Format (`.one`, `.onetoc2`) по спецификации [[MS-ONESTORE].pdf]([MS-ONESTORE].pdf) (v20250520).

Этот набор Markdown-файлов — не «пересказ», а **план внедрения**: что именно читать, какие проверки делать, какие структуры/узлы строить, и как связать всё в рабочий парсер.

Примечание по отображению: файлы в UTF-8; если в терминале видны «кракозябры», откройте их в редакторе с UTF-8 (или выводите через Python, где явно задан `encoding='utf-8'`).

## Как читать эти инструкции

Рекомендуемый порядок (сначала база, затем FileNode, затем высокоуровневые сущности):

1. `docs/ms-onestore/00-roadmap.md` — общий план реализации и вехи готовности.
2. `docs/ms-onestore/01-binary-reader.md` — базовый бинарный ридер, битовые поля, безопасное чтение.
3. `docs/ms-onestore/02-common-types.md` — `ExtendedGUID`, `CompactID`, строки, chunk references (`fcr*`).
4. `docs/ms-onestore/03-header.md` — заголовок файла, ключевые указатели на деревья/журналы.
5. `docs/ms-onestore/04-free-chunk-list.md` — список свободных блоков (нужно для записи/валидации).
6. `docs/ms-onestore/05-transaction-log.md` — транзакционный журнал; как определить «коммитнутую» версию списков.
7. `docs/ms-onestore/06-file-node-list.md` — фрагменты списков FileNode и их склейка.
8. `docs/ms-onestore/07-file-node-core.md` — общий парсер `FileNode` (битовые поля) и `FileNodeChunkReference`.
9. `docs/ms-onestore/08-file-node-types-manifests.md` — манифесты object space / revisions и «каркас» обхода.
10. `docs/ms-onestore/09-file-node-types-global-id-table.md` — глобальная таблица GUID и сопоставление `CompactID -> GUID`.
11. `docs/ms-onestore/10-file-node-types-objects.md` — объявления/ревизии объектов, refcount, root object.
12. `docs/ms-onestore/11-file-node-types-file-data.md` — FileDataStore и file data declarations.
13. `docs/ms-onestore/12-object-data.md` — `ObjectSpaceObjectPropSet`, потоки ссылок, `PropertySet`.
14. `docs/ms-onestore/15-hashed-chunk-list.md` — hashed chunk list и MD5-верификация blob-данных.
15. `docs/ms-onestore/16-root-file-node-list.md` — требования к root file node list и извлечение object spaces.
16. `docs/ms-onestore/17-revision-manifest-parsing.md` — правила последовательностей в revision manifest и сборка состояния.
17. `docs/ms-onestore/18-property-containers.md` — `prtFourBytesOfLengthFollowedByData` и `prtArrayOfPropertyValues`.
18. `docs/ms-onestore/19-writer-basics.md` — основы записи: append-only, аллокация и коммит транзакции.
19. `docs/ms-onestore/20-writer-structures.md` — как записывать ключевые структуры (lists, manifests, objects).
20. `docs/ms-onestore/13-validation.md` — инварианты/проверки и минимальный набор тестов.
21. `docs/ms-onestore/14-fsshttp.md` — (опционально) передача через FSSHTTP.

## Что считать «полной поддержкой»

Минимальный «полный» ридер обычно означает:

- чтение `Header` + обход всех достижимых блоков;
- корректная сборка всех `FileNodeListFragment` в логические списки;
- применение `Transaction Log` (игнорирование незакоммиченных добавлений);
- парсинг всех `FileNode` типов из разделов 2.5/2.6;
- восстановление object spaces, revisions, root objects и объектов;
- корректное чтение `PropertySet` и ссылочных потоков (OIDs/OSIDs/ContextIDs);
- базовая валидация (`CRC`, `MD5` где требуется).

Для записи/редактирования добавьте:

- поддержку `Free Chunk List`, обновление `Transaction Log`, корректное формирование фрагментов;
- пересчёт `cTransactionsInLog`, `guidFileVersion`, `nFileVersionGeneration`, `guidDenyReadFileVersion`;
- соблюдение ограничений read-only объектов и правил `DataSignatureGroupDefinitionFND`.
