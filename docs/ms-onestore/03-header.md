# Header (2.3.1): чтение заголовка файла

`Header` находится в начале файла и задаёт «точки входа»:

- `fcrFileNodeListRoot` — корень дерева фрагментов file node list
- `fcrTransactionLog` — журнал транзакций (как узнать, сколько узлов «коммитнуто»)
- `fcrFreeChunkList` — список свободных блоков (опционально)
- `fcrHashedChunkList` — hashed chunk list (опционально)

## 1) Парсинг: порядок действий

1. `seek(0)`.
2. Прочитайте поля `Header` последовательно (все little-endian).
3. Проверьте MUST-инварианты:
   - `guidFileFormat` == `{109ADD3F-911B-49F5-A5D0-1791EDC8AED8}`
   - `cTransactionsInLog` MUST NOT be 0
   - `fcrTransactionLog` и `fcrFileNodeListRoot` MUST NOT be `fcrZero`/`fcrNil`
   - legacy-поля MUST иметь фиксированные значения и MUST be ignored (в текущей реализации эти MUST проверяются строго):
     - `guidLegacyFileVersion` MUST быть `{00000000-0000-0000-0000-000000000000}`
     - `fcrLegacyFreeChunkList` MUST быть `fcrZero`
     - `fcrLegacyTransactionLog` MUST быть `fcrNil`
     - `cbLegacyExpectedFileLength` MUST быть `0`
     - `rgbPlaceholder` MUST быть `0`
     - `fcrLegacyFileNodeListRoot` MUST быть `fcrNil`
     - `cbLegacyFreeSpaceInFreeChunkList` MUST быть `0`
     - `fHasNoEmbeddedFileObjects` MUST быть `0`
   - `grfDebugLogFlags` MUST be 0; `fcrDebugLog` и `fcrAllocVerificationFreeChunkList` MUST be `fcrZero` (и игнорируются)
4. Вынесите `guidFileType`:
   - `.one` => `{7B5C52E4-D88C-4DA7-AEB1-5378D02996D3}`
   - `.onetoc2` => `{43FF2FA1-EFD9-4C76-9EE2-10EA5722765F}`
5. Сохраните `cbExpectedFileLength` и сравните с фактической длиной файла (warning если расходится; на повреждённых файлах бывает).

## 2) Важные поля и смысл

Минимум для ридера:

- `guidFileType`, `guidFile`
- `crcName` — CRC **Unicode-имени файла с расширением + завершающий null**, алгоритм как для `.one` (section 2.1.2), даже если файл `.onetoc2` (так в спецификации)
- `fcrHashedChunkList` (можно игнорировать, если вам не нужна MD5-верификация chunks)
- `fcrTransactionLog`, `cTransactionsInLog`
- `fcrFileNodeListRoot`
- `fcrFreeChunkList` (игнорировать для read-only ридера, но читать и уметь пройти полезно)
- `ffvLast/Oldest/Newest...` — фиксированные значения из таблиц спецификации (по типу файла); полезны для валидации/отчёта о несоответствии
- `rgbReserved` MUST быть нулём и MUST be ignored
- `bnCreated`, `bnLastWroteToThisFile`, `bnOldestWritten`, `bnNewestWritten` SHOULD be ignored

Для записи/редактирования:

- `guidFileVersion`, `nFileVersionGeneration`
- `guidDenyReadFileVersion`
- `cbFreeSpaceInFreeChunkList` (SHOULD; можно поддерживать приблизительно)

## 3) API и модель данных

Сделайте `Header.parse(reader) -> Header`.

Для GUID:

- храните `bytes(16)` и форматируйте в string на уровне представления.

Для chunk references:

- сразу нормализуйте в `ChunkRef(stp:int, cb:int, kind=...)` и валидируйте:
  - `0 <= stp <= file_size`
  - `0 <= cb <= file_size`
  - `stp + cb <= file_size` (если `cb != 0` и `stp != all_ones`)

## 4) «Достижимые блоки»

Спецификация: данные вне `Header` и вне блоков, достижимых по ссылкам, должны игнорироваться.

Реализация:

- используйте BFS/DFS по всем chunk references, которые вы встречаете при разборе структур;
- храните `visited[(stp, cb, type)]`, чтобы не уйти в цикл;
- для «структур списков» добавляйте ссылки из `nextFragment`, `ref`, и т.д.

С этим механизмом удобно делать «ленивый парсинг»:

- сначала проходите только структуру/границы;
- затем по запросу пользователя читаете object data.
