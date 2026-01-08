# FileNode (2.4.3): общий парсер узлов

`FileNode` — основной «атом» данных: заголовок + поле `fnd` (data/ref/mixed).

## Заголовок FileNode (битовые поля)

В начале `FileNode` — 4-байтовое слово, упакованное битами:

- `FileNodeID` — 10 bits (тип узла)
- `Size` — 13 bits (размер узла в байтах, включая заголовок)
- `StpFormat` — 2 bits (A)
- `CbFormat` — 2 bits (B)
- `BaseType` — 4 bits (C)
- `Reserved` — 1 bit (D) MUST be 1 (но игнорируется)

Важные правила из спецификации:

- если `BaseType == 0`, то `StpFormat` MUST be ignored, а `CbFormat` MUST be 0 и MUST be ignored;
  (это позволяет ловить повреждения/мусор в заголовке при строгой валидации).

Реализация:

1. Прочитайте `u32` (`hdr`).
2. Извлеките поля (важно: один раз и одинаково для всех):
   - используйте таблицу битовых ширин в порядке, как описано в спецификации;
   - храните `(file_node_id, size, stp_format, cb_format, base_type)`.
3. Проверьте `size >= 4` и что `size` не ведёт за границы контейнера, в котором вы читаете.

## BaseType: как интерпретировать `fnd`

BaseType:

- `0`: `fnd` НЕ содержит `FileNodeChunkReference`
- `1`: `fnd` начинается с `FileNodeChunkReference` на «данные»
- `2`: `fnd` начинается с `FileNodeChunkReference` на «file node list»

Практика:

- ваш парсер конкретного типа (`FileNodeID -> parser`) должен получать:
  - `base_type`
  - (опционально) уже распарсенный `FileNodeChunkReference`
  - оставшиеся байты `payload`

## Общий алгоритм `parse_filenode(reader) -> FileNode`

1. `start = tell()`
2. `hdr = read_u32()`, распарсить битовые поля.
3. `payload_size = Size - 4`
4. `payload = read_bytes(payload_size)` (или `view` поверх payload)
5. Вызвать `parse_fnd(FileNodeID, payload_reader, base_type, stp_format, cb_format)`:
   - если `base_type in (1,2)`: сначала прочитать `FileNodeChunkReference` с форматом из `stp_format/cb_format`
   - затем прочитать оставшуюся часть специфичной структуры
6. `assert tell() == start + Size`

## Маршрутизация по FileNodeID

Сделайте таблицу `FileNodeID -> parser` и централизованный «unknown handler»:

- для неизвестного `FileNodeID`:
  - сохраняйте сырые байты `fnd` (на будущее),
  - не падайте в tolerant режиме,
  - но фиксируйте warning.

Это поможет позже расширять поддержку без поломки существующего чтения.
