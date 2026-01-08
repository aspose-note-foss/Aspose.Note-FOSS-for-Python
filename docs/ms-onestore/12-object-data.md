# Данные объектов: ObjectSpaceObjectPropSet и PropertySet (2.6.1–2.6.9, 2.6.14–2.6.16)

Это «сердце» данных OneNote: свойства и ссылки на другие объекты/контексты.

## 1) JCID (2.6.14)

JCID — 4 байта (можно считать как `u32`), но логически:

- `index: u16` — тип объекта
- флаги (по битам):
  - `IsBinary`
  - `IsPropertySet`
  - `IsGraphNode` (ignore)
  - `IsFileData`
  - `IsReadOnly`
  - `Reserved` (11 bits) MUST 0

Инвариант:

- если `IsFileData == true`, остальные `IsBinary/IsPropertySet/IsGraphNode/IsReadOnly` MUST быть false.

## 2) ObjectDeclaration bodies

### ObjectDeclarationWithRefCountBody (2.6.15)

Поля (битовые, 10 байт):

- `oid: CompactID (4)`
- битполя, включающие:
  - `jci` (10 bits): MUST be `0x01` (это `JCID.index` в этой структуре)
  - `odcs` (4 bits): MUST 0 (encryption marker для этих тел — всегда 0)
  - `fHasOidReferences` (1 bit)
  - `fHasOsidReferences` (1 bit) MUST 0
  - резервные биты MUST 0

### ObjectDeclaration2Body (2.6.16)

- `oid: CompactID (4)`
- `jcid: JCID (4)`
- `fHasOidReferences: 1 bit`
- `fHasOsidReferences: 1 bit` (включая context refs)
- `fReserved2: 6 bits` MUST 0

## 3) ObjectSpaceObjectPropSet (2.6.1)

 Структура:

 - `OIDs: ObjectSpaceObjectStreamOfOIDs` (2.6.2)
 - `OSIDs: ObjectSpaceObjectStreamOfOSIDs` (2.6.3) — опционально
 - `ContextIDs: ObjectSpaceObjectStreamOfContextIDs` (2.6.4) — опционально
 - `body: PropertySet` (2.6.7)
 - `padding: 0..7 bytes` (MUST be 0) до кратности 8

 Спецификационные ограничения ссылок (2.1.5):

 - ссылки в `OIDs` (объекты того же object space) MUST NOT образовывать цикл;
 - ссылки в `OSIDs` (на другие object spaces) MUST NOT идти на свой же object space, MUST NOT образовывать цикл и указывают на ревизию object space с default context и revision role `0x00000001`;
 - ссылки в `ContextIDs` (контексты того же object space) указывают на ревизию этого контекста с revision role `0x00000001`; такие ссылки могут образовывать цикл.

 Ключевая идея:

 - `PropertySet` содержит свойства, некоторые из которых являются ссылками (ObjectID/OSID/ContextID и массивы).
 - сами значения этих ссылок лежат не в `rgData`, а в потоках `OIDs.body`, `OSIDs.body`, `ContextIDs.body`.

## 4) Потоки ссылок (2.6.2–2.6.5)

### ObjectSpaceObjectStreamHeader (2.6.5)

4 байта, битовые поля:

- `Count: 24 bits` — число `CompactID` в `body`
- `Reserved: 6 bits` MUST 0
- `ExtendedStreamsPresent: 1 bit`
- `OsidStreamNotPresent: 1 bit`

### ObjectSpaceObjectStreamOfOIDs (2.6.2)

- `header: ObjectSpaceObjectStreamHeader (4)`
- `body: CompactID[header.Count]`

Инварианты:

- если `OSIDs` присутствует, `header.OsidStreamNotPresent` MUST быть false, иначе true
- если `ContextIDs` присутствует, `header.ExtendedStreamsPresent` MUST быть true, иначе false

### ObjectSpaceObjectStreamOfOSIDs (2.6.3)

- header + `CompactID[]`
- `header.OsidStreamNotPresent` MUST быть false
- `header.ExtendedStreamsPresent` MUST быть true, **если** за OSIDs следует `ContextIDs` stream (то есть если у prop set есть ссылки на контексты); иначе MUST be false

### ObjectSpaceObjectStreamOfContextIDs (2.6.4)

- header + `CompactID[]`
- `header.OsidStreamNotPresent` MUST be false и `header.ExtendedStreamsPresent` MUST be false (по тексту структуры)

Практика реализации:

- парсите все три потока (если присутствуют) в списки `compact_ids`.
- не пытайтесь «разрешать» их в GUID на этом уровне: это зависит от текущей global id table и контекста revision.

## 5) PropertyID (2.6.6) и PropertySet (2.6.7)

### PropertyID

4 байта (битовые поля):

- `id: 26 bits` (семантика в `[MS-ONE]` 2.1.12)
- `type: 5 bits` — формат данных
- `boolValue: 1 bit` (валидно только если `type == 0x2`)

`type` определяет, где лежит значение:

- `0x1` NoData — нет данных
- `0x2` Bool — значение в `boolValue`
- `0x3..0x6` — фиксированный размер (1/2/4/8 байт) в `PropertySet.rgData`
- `0x7` — `prtFourBytesOfLengthFollowedByData` в `rgData`
- `0x8/0x9` — ObjectIDs в `OIDs.body` (для массива длина хранится в `rgData` как `u32`)
- `0xA/0xB` — ObjectSpaceIDs в `OSIDs.body` (аналогично)
- `0xC/0xD` — ContextIDs в `ContextIDs.body` (аналогично)
- `0x10` — `prtArrayOfPropertyValues` в `rgData`
- `0x11` — дочерний `PropertySet` в `rgData`

### PropertySet

Поля:

- `cProperties: u16`
- `rgPrids: PropertyID[cProperties]`
- `rgData: bytes` — конкатенация данных всех свойств, длина = сумма размеров по `type`

## 6) Связка rgData и потоков ссылок (важнейший алгоритм)

При построении «объектной модели» полезно делать декодер:

1. Пройдите `rgPrids` по порядку.
2. Для каждого `PropertyID`:
   - если `type` — «ссылка», то:
     - берите следующий `CompactID` (или `N` штук) из соответствующего потока (`OIDs/OSIDs/ContextIDs`)
     - для массива сначала возьмите `N` из `rgData` как `u32`
   - иначе возьмите данные из `rgData` согласно `type`
3. Сохраняйте декодированные свойства как `list[PropertyValue]` с полями:
   - `prop_id`, `prop_type`, `value`, `raw_offset` (для отладки)

Главное: порядок в потоках соответствует порядку свойств в `rgPrids`.
