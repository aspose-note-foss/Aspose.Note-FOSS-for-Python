# Hashed Chunk List и HashedChunkDescriptor2FND (2.3.4 / 2.3.4.1)

Hashed chunk list — опциональный file node list, который содержит `HashedChunkDescriptor2FND (FileNodeID=0x0C2)`. Его основная цель — дать MD5 для blob-данных.

## 1) Где находится

Точка входа:

- `Header.fcrHashedChunkList: FileChunkReference64x32`

Если `fcrHashedChunkList` равно `fcrZero` или `fcrNil`, hashed chunk list отсутствует.

## 2) Структура списка

Hashed chunk list — обычный file node list (см. `docs/ms-onestore/06-file-node-list.md`), но логически он должен содержать только узлы:

- `HashedChunkDescriptor2FND (0x0C2)` (BaseType=1)

## 3) HashedChunkDescriptor2FND (0x0C2)

Поля:

- `BlobRef: FileNodeChunkReference` -> **MUST** `ObjectSpaceObjectPropSet` (spec 2.3.4.1 не допускает других целей)
- `guidHash: 16 bytes` — MD5 от данных по `BlobRef` ([RFC1321])

Реализация:

1. Прочитайте `BlobRef` через `FileNodeChunkReference` (формат задаётся заголовком FileNode).
2. Сохраните `guidHash` как `bytes(16)`.
3. (опционально) Для валидации:
   - прочитайте blob по `(BlobRef.stp, BlobRef.cb)`,
   - посчитайте `md5(blob_bytes)`,
   - сравните с `guidHash`.

## 4) Как использовать в ридере

Практичный подход:

- при первом проходе файла соберите индекс: `hash_by_blob_ref[(stp,cb)] = md5`.
- при чтении объектов (объявлений/ревизий) можно сверять данные на лету, если совпадает `(stp,cb)`.

Важно:

- hashed chunk list не обязателен; не делайте его наличие обязательным условием парсинга.
