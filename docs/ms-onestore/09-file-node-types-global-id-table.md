# Global Identification Table и CompactID (2.1.3, 2.5.9–2.5.12)

Global ID Table нужна для разрешения `CompactID.guidIndex -> GUID`.

Ключевой момент: таблица действует **контекстно** — на «последующие FileNode» до следующего маркера конца области действия.

## 1) Область действия таблицы (2.1.3)

Таблица применяется к FileNode, которые идут сразу после неё, пока не встретится один из FileNodeID:

- `0x01C` (RevisionManifestEndFND)
- `0x021` (GlobalIdTableStartFNDX)
- `0x022` (GlobalIdTableStart2FND)

Практика:

- при парсинге revision manifest держите `current_gid_table` в контексте;
- сбрасывайте/заменяйте его при встрече Start.

## 2) Варианты для `.one` и `.onetoc2`

`.one`:

- `0x022` GlobalIdTableStart2FND — MUST contain no data
- `0x024` GlobalIdTableEntryFNDX — 0..N
- `0x028` GlobalIdTableEndFNDX — MUST contain no data

`.onetoc2`:

- `0x021` GlobalIdTableStartFNDX (2.5.9) — содержит `Reserved` (1 byte) MUST 0
- далее 0..N из:
  - `0x024` GlobalIdTableEntryFNDX
  - `0x025` GlobalIdTableEntry2FNDX
  - `0x026` GlobalIdTableEntry3FNDX
- `0x028` GlobalIdTableEndFNDX — MUST contain no data

## 3) GlobalIdTableEntryFNDX (0x024)

Поля:

- `index: u32` (MUST < 0xFFFFFF, уникальный)
- `guid: GUID (16 bytes)` (MUST not all-zero, уникальный)

Реализация:

- храните `index -> guid` в dict/array.
- удобно держать `max_index` и/или sparse map (индексы не обязаны быть плотными).

## 4) GlobalIdTableEntry2FNDX (0x025) — map from dependency revision

Поля:

- `iIndexMapFrom: u32` — индекс GUID в global id table dependency revision
- `iIndexMapTo: u32` — индекс в текущей таблице

Реализация:

- требует доступа к global id table dependency revision (то есть к уже построенной revision dependency цепочке).
- практично: сначала сохранить «операции построения», а разрешать их после того, как dependency revision доступна.

## 5) GlobalIdTableEntry3FNDX (0x026) — range copy from dependency revision

Поля:

- `iIndexCopyFromStart: u32`
- `cEntriesToCopy: u32`
- `iIndexCopyToStart: u32`

Реализация:

- для `k in 0..cEntriesToCopy-1`:
  - `to = iIndexCopyToStart + k`
  - `from = iIndexCopyFromStart + k`
  - `table[to] = dependency_table[from]`

Проверки:

- все индексы «from-range» должны существовать в dependency table
- все `to` должны быть < 0xFFFFFF и уникальны

## 6) Разрешение CompactID в ExtendedGUID

`CompactID` = `(n, guidIndex)`:

- `guid = global_id_table[guidIndex]`
- `ExtendedGUID = { guid, n }`

Ошибки:

- если `guidIndex` отсутствует в таблице, это или повреждение, или вы применяете неправильную область действия таблицы.

