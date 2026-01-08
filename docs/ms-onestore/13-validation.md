# Валидация и тесты: что проверять и как не сломать парсер

## 1) MUST-проверки, которые стоит включить сразу

- `Header.guidFileFormat` и `FileNodeListHeader.uintMagic` / `FileNodeListFragment.footer`
- `Header.cTransactionsInLog != 0`
- `Header.grfDebugLogFlags == 0`, `fcrDebugLog == fcrZero`, `fcrAllocVerificationFreeChunkList == fcrZero`
- `FileNode.Size` не выходит за границы контейнера
- `FileNode.BaseType == 0` => `CbFormat MUST be 0`, `StpFormat/CbFormat` игнорируются
- `FileNode.Reserved bit == 1` (можно warning, но полезно как маркер корректного bit parsing)
- `FileChunkReference` не выходит за файл (`stp+cb <= file_size`), кроме спец-значений `fcrNil`

## 2) Проверки, которые можно сделать позже (но запланировать)

- CRC:
  - `.one`: RFC3309 CRC32 с init=all1 и финальной инверсией
  - `.onetoc2`: `MsoCrc32Compute` (MS-OSHARED)
- MD5:
  - `HashedChunkDescriptor2FND.guidHash` — MD5 от данных `BlobRef`
  - `ReadOnlyObjectDeclaration2*FND.md5Hash` — MD5 от (возможно расшифрованных) данных
- ObjectInfoDependencyOverrideData.crc — CRC по правилам 2.6.10

## 3) Минимальный набор unit-тестов (без реальных .one файлов)

### Битполя

- `CompactID` распаковка из `u32`
- `FileNode` распаковка `FileNodeID/Size/StpFormat/CbFormat/BaseType`
- `ObjectSpaceObjectStreamHeader` (Count/flags)
- `PropertyID` (id/type/boolValue)
- `JCID` (index + флаги)

### Размеры и границы

- `FileNodeListFragment`: `nextFragment` читается из правильной позиции (по `cb`)
- `FreeChunkListFragment`: `n = (cb-16)/16` и корректная обработка `fcrNil` конца

## 4) Интеграционные проверки на реальных файлах

Когда появятся реальные `.one/.onetoc2`:

- smoke test: `parse(file)` не падает и строит дерево object spaces/revisions
- determinism: повторный парсинг даёт одинаковую структуру (по stable IDs)
- coverage: известные `FileNodeID` не попадают в «unknown handler» (или падают только на редких/неподдержанных расширениях)

## 5) Толерантный режим

Полезно разделить:

- нарушения, которые делают дальнейший парсинг бессмысленным (границы, magic) — error
- нарушения SHOULD / «MUST be ignored» поля — warning

В tolerant режиме:

- сохраняйте сырые bytes для неизвестных/сомнительных узлов;
- не делайте «автовосстановления» (например, угадывать размеры) — лучше остановиться на текущем объекте и продолжить со следующим безопасным якорем (fragment boundary / node size).
