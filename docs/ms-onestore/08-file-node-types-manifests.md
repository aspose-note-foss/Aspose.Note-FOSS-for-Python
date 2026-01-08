# FileNode типы: манифесты object spaces и revisions (2.5.1–2.5.8, 2.5.17–2.5.19)

Здесь — узлы, которые задают «каркас» данных: какие object spaces есть в файле и какие revisions у каждого object space.

## 0) Где они живут

- **Root file node list** (указан `Header.fcrFileNodeListRoot`) содержит, среди прочего:
  - `ObjectSpaceManifestRootFND (0x004)` — кто является root object space
  - набор `ObjectSpaceManifestListReferenceFND (0x008)` — ссылки на object space manifest lists
- **Object space manifest list** — file node list, на который указывает `ObjectSpaceManifestListReferenceFND.ref`
  - должен начинаться с `ObjectSpaceManifestListStartFND (0x00C)`
  - должен содержать один или более `RevisionManifestListReferenceFND (0x010)`; если больше одного — все, кроме последнего, игнорируются
- **Revision manifest list** — file node list, на который указывает `RevisionManifestListReferenceFND.ref`
  - должен начинаться с `RevisionManifestListStartFND (0x014)`
  - далее содержит revision manifests (`RevisionManifestStart* ... RevisionManifestEnd`) и декларации ролей/контекстов

## 1) ObjectSpaceManifestRootFND (0x004) — root object space

Назначение:

- единственный на файл узел, который задаёт identity root object space.

Поля:

- `gosidRoot: ExtendedGUID (20 bytes)`

Инвариант:

- `gosidRoot` должен совпадать с `ObjectSpaceManifestListReferenceFND.gosid` одного из object spaces.

## 2) ObjectSpaceManifestListReferenceFND (0x008, BaseType=2)

Назначение:

- ссылка на file node list, который является object space manifest list.

Поля:

- `ref: FileNodeChunkReference` (указывает на первый `FileNodeListFragment` списка)
- `gosid: ExtendedGUID (20 bytes)` — identity object space

Инварианты:

- `gosid` не равен `{{0},0}` и уникален среди всех `ObjectSpaceManifestListReferenceFND` в файле.

## 3) ObjectSpaceManifestListStartFND (0x00C)

Поля:

- `gosid: ExtendedGUID (20 bytes)` — должен совпасть с `ObjectSpaceManifestListReferenceFND.gosid`, который ссылался на этот список.

## 4) RevisionManifestListReferenceFND (0x010, BaseType=2)

Поля:

- `ref: FileNodeChunkReference` — ссылка на первый `FileNodeListFragment` revision manifest list

Правило списка (2.1.6):

- object space manifest list MUST содержать **одну** «активную» ссылку на revision manifest list: если ссылок больше одной — применяйте только последнюю.

## 5) RevisionManifestListStartFND (0x014)

Поля:

- `gosid: ExtendedGUID (20 bytes)` — identity object space
- `nInstance: u32` — MUST be ignored

## 6) RevisionManifestStart* / RevisionManifestEndFND

### 6.1 Start structures

Варианты, допустимые в начале revision manifest (2.1.9):

- `.one`: `RevisionManifestStart6FND (0x01E)` или `RevisionManifestStart7FND (0x01F)`
- `.onetoc2`: `RevisionManifestStart4FND (0x01B)`

Общие поля:

- `rid: ExtendedGUID (20)` — identity revision; MUST not `{{0},0}`; уникальность зависит от варианта
- `ridDependent: ExtendedGUID (20)` — dependency revision или `{{0},0}`
- `RevisionRole: u32 (4)` — revision role
- `ridDependent` (если не `{{0},0}`) MUST указывать на revision, заданный **предыдущим** `RevisionManifestStart*` в том же revision manifest list (spec 2.5.6/2.5.7/2.5.8).
- Если `ridDependent` задан, `odcsDefault` MUST совпадать с типом шифрования dependency revision.

Инварианты по уникальности `rid`:

- для `.one` (`Start6/Start7`) и `.onetoc2` (`Start4`) значение `rid` MUST быть уникально **в пределах текущего revision manifest list** (спецификация 2.5.6/7/8).

Отличия:

- `Start4` имеет ещё `timeCreation (8)` (ignore) и `odcsDefault (2)` (MUST 0; ignore)
- `Start6` имеет `odcsDefault (2)`:
  - `0x0000` — не зашифровано
  - `0x0002` — зашифровано (property sets MUST be ignored и MUST NOT be altered)
- `Start7` добавляет context (см. PDF 2.5.8): используйте его для label pair (context, role)

### 6.2 Encryption marker

Если object space зашифрован, то **второй** FileNode в revision manifest MUST быть:

- `ObjectDataEncryptionKeyV2FNDX (0x07C)` (см. ниже)

### 6.3 RevisionManifestEndFND (0x01C)

- MUST содержать **нет данных**.
- завершает revision manifest.

## 7) RevisionRoleDeclarationFND (0x05C) и RevisionRoleAndContextDeclarationFND (0x05D)

Эти узлы обновляют «текущую ревизию» для конкретной пары (context, revision role).

### RevisionRoleDeclarationFND (0x05C)

Поля:

- `rid: ExtendedGUID (20)` — к какой revision относится
- `RevisionRole: u32 (4)` — роль; контекст по умолчанию (default context)
- `rid` MUST ссылаться на revision, уже объявленный **раньше** в текущем revision manifest list (spec 2.5.17).

### RevisionRoleAndContextDeclarationFND (0x05D)

Поля:

- `base: RevisionRoleDeclarationFND (24 bytes)` — rid + role
- `gctxid: ExtendedGUID (20)` — context
- `rid` MUST ссылаться на revision, уже объявленный **раньше** в текущем revision manifest list (spec 2.5.18).

Правило 2.1.11:

- для каждой пары (context, role) действует «последнее присваивание»: все предыдущие в списке игнорируются.

## 8) ObjectDataEncryptionKeyV2FNDX (0x07C)

Назначение:

- маркер, что object space encrypted; содержит ссылку на blob с encryption data (но сами данные можно игнорировать на первом этапе).

Поля:

- `ref: FileNodeChunkReference` указывает на структуру:
  - `Header: u64 MUST 0xFB6BA385DAD1A067`
  - `Encryption Data: bytes (variable) MUST be ignored`
  - `Footer: u64 MUST 0x2649294F8E198B3C`

Инварианты:

- если в одном revision manifest object space присутствует этот узел, то **во всех** revision manifests этого object space он должен присутствовать и указывать на идентичные encryption data.

## 9) Практическая модель обхода

Рекомендуемая сборка структуры в памяти:

- `File`:
  - `object_spaces: dict[ExtendedGUID, ObjectSpace]`
- `ObjectSpace`:
  - `manifest_list_ref` -> `object_space_manifest_list`
  - `revision_manifest_list_ref` -> `revision_manifest_list`
- `RevisionManifestList`:
  - линейный проход FileNodes; поддержка «последнего присваивания» ролей/контекстов
  - `revisions: list[RevisionManifest]` (каждая заканчивается `RevisionManifestEndFND`)
