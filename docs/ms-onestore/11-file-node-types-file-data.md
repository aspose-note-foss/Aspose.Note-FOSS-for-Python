# FileNode типы: FileDataStore и file data declarations (2.5.21–2.5.22, 2.5.27–2.5.28, 2.6.13)

Эта часть нужна, чтобы извлекать бинарные вложения (например, картинки, вложенные файлы).

## 1) FileDataStoreListReferenceFND (0x090)

Назначение:

- указывает на file node list, содержащий ссылки на file data objects.

Поля:

- `ref: FileNodeChunkReference` -> первый `FileNodeListFragment` списка

Инвариант:

- целевой list MUST содержать **только** узлы `FileDataStoreObjectReferenceFND (0x094)`.

## 2) FileDataStoreObjectReferenceFND (0x094)

Поля:

- `ref: FileNodeChunkReference` -> `FileDataStoreObject` (2.6.13)
- `guidReference: GUID (16)` — identity file data object, MUST быть уникален среди ссылок

Рекомендация:

- построить индекс `guidReference -> FileDataStoreObjectRef`.

## 3) FileDataStoreObject (2.6.13)

Поля:

- `guidHeader: GUID (16)` MUST = `{BDE316E7-2665-4511-A4C4-8D4D0B7A9EAC}`
- `cbLength: u64` — длина полезных данных `FileData` без padding
- `unused: u32` MUST 0 (ignore)
- `reserved: u64` MUST 0 (ignore)
- `FileData: bytes (cbLength)` + padding до 8-байтной границы
- `guidFooter: GUID (16)` MUST = `{71FBA722-0F79-4A0B-BB13-899256426B24}`

Парсинг:

1. Войдите в `view(stp, cb)` по `ref` из `FileDataStoreObjectReferenceFND`.
2. Проверьте `guidHeader`.
3. Прочитайте `cbLength`, затем `unused`, `reserved`.
4. Прочитайте `FileData` ровно `cbLength`.
5. Пропустите padding (0..7 байт) до позиции `guidFooter` и проверьте `guidFooter`.

## 4) File data object declarations: 0x072 / 0x073

Это **объекты**, которые ссылаются на file data (через строку-указатель).

### ObjectDeclarationFileData3RefCountFND (0x072)

Поля:

- `oid: CompactID (4)`
- `jcid: JCID (4)`
- `cRef: u8`
- `FileDataReference: StringInStorageBuffer`
- `Extension: StringInStorageBuffer` (расширение с точкой)

### ObjectDeclarationFileData3LargeRefCountFND (0x073)

То же, но:

- `cRef: u32`

### FileDataReference.StringData: префиксы

Строка должна начинаться с одного из:

- `<file>` — файл в папке `onefiles`:
  - остаток SHOULD быть именем файла (включая расширение),
  - имя (без расширения) MUST быть UUID в строковой форме,
  - расширение MUST быть `onebin`
- `<ifndf>` — ссылка на `FileDataStoreObject`:
  - остаток — строковый GUID в фигурных скобках,
  - должен соответствовать одному из `FileDataStoreObjectReferenceFND.guidReference`
- `<invfdo>` — невалидная ссылка; далее MUST быть пустая строка

Практическая резолюция:

- для `<ifndf>`: найдите `guidReference` в индексе и извлеките `FileDataStoreObject.FileData`
- для `<file>`: это внешний файл; на первом этапе можно вернуть путь/имя и оставить резолюцию «на пользователя»

