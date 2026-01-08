# FileNode типы: объекты, ревизии, refcount (2.5.13–2.5.16, 2.5.20, 2.5.23–2.5.33)

Эта часть превращает revision manifest в набор объектов, их данных и ссылок.

## 1) ObjectRevisionWithRefCountFNDX (0x041) и ObjectRevisionWithRefCount2FNDX (0x042)

Назначение:

- «ревизия объекта»: объект уже существует, но его данные меняются (новый `ObjectSpaceObjectPropSet`).

### 0x041 (2.5.13)

Поля:

- `ref: FileNodeChunkReference` -> `ObjectSpaceObjectPropSet`
- `oid: CompactID (4)`
- флаги:
  - `fHasOidReferences: 1 bit`
  - `fHasOsidReferences: 1 bit`
  - `cRef: 6 bits` (refcount, маленький)

### 0x042 (2.5.14)

Поля:

- `ref: FileNodeChunkReference` -> `ObjectSpaceObjectPropSet`
- `oid: CompactID (4)`
- флаги:
  - `fHasOidReferences: 1 bit`
  - `fHasOsidReferences: 1 bit`
  - `Reserved: 30 bits` MUST 0
- `cRef: u32` (refcount, большой)

Практика:

- обе структуры дают «последнее состояние» объекта для текущей revision (с учётом dependency).

## 2) RootObjectReference2FNDX (0x059) / RootObjectReference3FND (0x05A)

Назначение:

- определяет root objects данной revision.

0x059:

- `oidRoot: CompactID (4)`
- `RootRole: u32 (4)`

0x05A:

- `oidRoot: ExtendedGUID (20)`
- `RootRole: u32 (4)`

Правила:

- один RootRole — не должен встречаться более одного раза в пределах одной revision.
- revision может иметь несколько root objects с разными RootRole.

## 3) ObjectInfoDependencyOverridesFND (0x084) и ObjectInfoDependencyOverrideData (2.6.10)

Назначение:

- обновляет refcount объектов без изменения их данных.

Поля узла:

- `ref: FileNodeChunkReference` (если не `fcrNil`) -> `ObjectInfoDependencyOverrideData`
- `data: ObjectInfoDependencyOverrideData` (если `ref == fcrNil`)

Ограничение:

- если override data лежит inline в `data`, то общий размер data MUST < 1024, иначе должно быть вынесено по `ref`.

`ObjectInfoDependencyOverrideData`:

- `c8BitOverrides: u32` — число `ObjectInfoDependencyOverride8`
- `c32BitOverrides: u32` — число `ObjectInfoDependencyOverride32`
- `crc: u32` — CRC от refcounts (алгоритм описан в 2.6.10)
- `Overrides1[]` и `Overrides2[]`

На первом этапе можно:

- корректно распарсить массивы;
- CRC проверку включить позже (см. `docs/ms-onestore/13-validation.md`).

## 4) Object declarations (объявления объектов)

Спецификационные жесткие связи с JCID (2.1.5, 2.6.14):

- если `JCID.IsPropertySet == true` (или указан только `JCID.index`), FileNodeID MUST быть одним из: `0x02D`, `0x02E`, `0x0A4`, `0x0A5`, `0x0C4`, `0x0C5`;
- если `JCID.IsReadOnly == true`, FileNodeID MUST быть `0x0C4` или `0x0C5` **и все объявления/ревизии этого объекта MUST содержать идентичные данные**;
- если `JCID.IsFileData == true`, FileNodeID MUST быть `0x072` или `0x073` и все объявления/ревизии этого объекта MUST содержать идентичные данные.

### 4.1 ObjectDeclarationWithRefCountFNDX (0x02D) / ObjectDeclarationWithRefCount2FNDX (0x02E)

Назначение:

- «первичное объявление» объекта и его данных (prop set) + refcount.

Поля:

- `ObjectRef: FileNodeChunkReference` -> `ObjectSpaceObjectPropSet`
- `body: ObjectDeclarationWithRefCountBody (10 bytes)` (2.6.15)
- `cRef: u8` для `0x02D` / `u32` для `0x02E`

### 4.2 ObjectDeclaration2RefCountFND (0x0A4) / ObjectDeclaration2LargeRefCountFND (0x0A5)

Поля:

- `BlobRef: FileNodeChunkReference` -> `ObjectSpaceObjectPropSet`
- `body: ObjectDeclaration2Body (9 bytes)` (2.6.16)
- `cRef: u8` для `0x0A4` / `u32` для `0x0A5`

### 4.3 ReadOnlyObjectDeclaration2* (0x0C4 / 0x0C5)

Назначение:

- объявление read-only объекта + MD5 контроль данных.

Поля:

- `base: ObjectDeclaration2RefCountFND` или `ObjectDeclaration2LargeRefCountFND`
- `md5Hash: 16 bytes` — MD5 от данных `base.BlobRef`

Особенность:

- если referenced data encrypted, нужно:
  - расшифровать,
  - допаддить нулями до 8-байтной границы,
  - затем считать MD5.

На раннем этапе можно:

- парсить `md5Hash` и сохранять,
- валидацию MD5 включить позже.

## 5) ObjectGroupListReferenceFND (0x0B0), ObjectGroupStartFND (0x0B4), DataSignatureGroupDefinitionFND (0x08C)

### ObjectGroupListReferenceFND (0x0B0)

- `ref: FileNodeChunkReference` -> file node list для object group
- `ObjectGroupID: ExtendedGUID (20)` — должен совпадать с `ObjectGroupStartFND.oid` в целевом списке

### ObjectGroupStartFND (0x0B4)

- `oid: ExtendedGUID (20)`

### DataSignatureGroupDefinitionFND (0x08C)

- `DataSignatureGroup: ExtendedGUID (20)`

Правило действия сигнатуры:

- применяется к «следующим объявлениям объектов» до встречи:
  - `ObjectGroupEndFND (0x0B8)` или
  - следующего `DataSignatureGroupDefinitionFND`, или
  - `RevisionManifestEndFND (0x01C)`

Инвариант:

- если у объектов одинаковая identity и одинаковый `DataSignatureGroup != {{0},0}`, их данные должны быть идентичны.
