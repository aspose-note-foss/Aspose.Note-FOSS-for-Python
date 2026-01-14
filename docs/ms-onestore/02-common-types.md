# Общие типы: GUID, строки и chunk references

Эти структуры используются почти везде; сделайте их первыми, с хорошими тестами.

## ExtendedGUID (2.2.1)

Бинарный формат:

- `guid` — 16 байт (GUID по [MS-DTYP])
- `n` — `u32` (в спецификации: «MUST be zero when guid==0»)

Примечание по текущей реализации:

- парсер читает поля структурно и не валидирует инвариант `guid==0 => n==0` на этом уровне.

Python-модель:

- храните `guid: bytes` (16) и `n: int`
- добавьте `as_tuple()` / `as_str()` (строковое представление — удобство, не парсерный критерий)

## CompactID (2.2.2)

Бинарный формат: 4 байта, упакованные битами:

- `n` — 8 бит
- `guidIndex` — 24 бита (индекс в global identification table)

Реализация:

- читайте `u32`, извлекайте `n = value & 0xFF`, `guidIndex = value >> 8`
- разрешение в `ExtendedGUID` требует текущей global id table (см. `docs/ms-onestore/09-file-node-types-global-id-table.md`)

## StringInStorageBuffer (2.2.3)

Бинарный формат:

- `cch` — `u32` (кол-во UTF-16 код-юнитов/«символов»)
- `StringData` — `cch` * 2 байта, `UTF-16LE`

Практика:

- `cch` может включать завершающий `\\u0000` (в некоторых местах явно упоминается «null character at the end» для CRC имени файла); не «обрезайте» нуль автоматически на уровне бинарного парсинга — лучше вернуть строку как есть + отдельный helper для «trim trailing null».

## File Chunk Reference (2.2.4)

Любая ссылка на блок файла — это `(stp, cb)`:

- `stp` — смещение от начала файла в байтах
- `cb` — размер блока в байтах

Спец-значения:

- `fcrNil`: все биты `stp` = 1, все биты `cb` = 0
- `fcrZero`: все биты `stp` = 0 и `cb` = 0

### FileChunkReference32 (2.2.4.1)

- `stp: u32`, `cb: u32`

### FileChunkReference64 (2.2.4.3)

- `stp: u64`, `cb: u64`

### FileChunkReference64x32 (2.2.4.4)

- `stp: u64`, `cb: u32`

### FileNodeChunkReference (2.2.4.2)

Размер/формат **зависят от** `FileNode.StpFormat` и `FileNode.CbFormat`:

StpFormat:

- `0`: 8 bytes, uncompressed
- `1`: 4 bytes, uncompressed
- `2`: 2 bytes, compressed (умножить на 8)
- `3`: 4 bytes, compressed (умножить на 8)

CbFormat:

- `0`: 4 bytes, uncompressed
- `1`: 8 bytes, uncompressed
- `2`: 1 byte, compressed (умножить на 8)
- `3`: 2 bytes, compressed (умножить на 8)

Реализация:

- в парсере `FileNode` сначала извлеките эти поля из заголовка;
- потом вызовите `parse_filenode_chunk_ref(reader, stp_format, cb_format)`;
- храните и «сырое значение», и «распакованное» (после умножения на 8) — удобно для отладки.

## CRC (2.1.2)

В формате два разных CRC алгоритма в зависимости от типа файла:

- `.one`: CRC по [RFC3309], полином `0x04C11DB7`, регистр init = all 1s, в конце инверсия
- `.onetoc2`: `MsoCrc32Compute` по [MS-OSHARED] 2.4.3.2

Практическая рекомендация:

- реализуйте CRC как отдельный модуль с тестами на фиксированных векторах;
- для `.one` текущая реализация использует `binascii.crc32()` и это совпадает с ожидаемыми значениями для CRC32 в формате.

