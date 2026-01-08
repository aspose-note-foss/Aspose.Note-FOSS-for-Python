# Revision Manifest: правила последовательностей и сборка состояния (2.1.7–2.1.12, 2.1.9)

Revision manifest — линейная последовательность FileNode, которая описывает состояние object space на момент revision.

Этот документ — про «как правильно прочитать последовательность» и собрать итоговое состояние.

## 1) Общие понятия

- **Root objects** (2.1.7): объекты, напрямую указанные в revision; все остальные объекты в revision должны быть достижимы от root objects через object references.
- **Revision** (2.1.8): immutable; определяется identity (ExtendedGUID) и набором объектов+состояний.
- **Revision manifest** (2.1.9): задаёт revision, может иметь dependency revision (`ridDependent`).

## 2) Старт и конец revision manifest

Последовательность MUST:

- начинаться с `RevisionManifestStart*` (зависит от типа файла)
- заканчиваться `RevisionManifestEndFND (0x01C)`

Начало:

- `.one`: `0x01E (Start6)` или `0x01F (Start7)`
- `.onetoc2`: `0x01B (Start4)`

Если object space encrypted:

- второй узел MUST быть `ObjectDataEncryptionKeyV2FNDX (0x07C)`

## 3) Разрешённые содержимое: `.one` (из 2.1.9)

После Start (и опционального 0x07C), последовательность может содержать:

1) **Zero or more object group sequences**, где каждый sequence:

- `0x0B0 (ObjectGroupListReferenceFND)`
- затем **обязательно** `0x084 (ObjectInfoDependencyOverridesFND)`

2) **Zero or one global identification table sequence**:

- `0x022 (GlobalIdTableStart2FND)` (no data)
- `0..N` `0x024 (GlobalIdTableEntryFNDX)`
- `0x028 (GlobalIdTableEndFNDX)` (no data)

Ограничение:

- global id table sequence MUST NOT быть followed by any object group sequences.

3) **Zero or more** узлов из набора:

- `0x05A (RootObjectReference3FND)`
- `0x084 (ObjectInfoDependencyOverridesFND)`

После этого:

- обязательный `0x01C (RevisionManifestEndFND)`.

## 4) Разрешённые содержимое: `.onetoc2` (из 2.1.9)

После Start:

- **Zero or more** `0x059 (RootObjectReference2FNDX)` и/или `0x084 (ObjectInfoDependencyOverridesFND)`
- **Zero or one** global id table sequence:
  - `0x021 (GlobalIdTableStartFNDX)`
  - `0..N` из `0x024/0x025/0x026`
  - `0x028 (GlobalIdTableEndFNDX)`
- **Zero or more** из:
  - `0x08C (DataSignatureGroupDefinitionFND)`
  - `0x02D/0x02E` (ObjectDeclarationWithRefCount*)
  - `0x041/0x042` (ObjectRevisionWithRefCount*)

Требование:

- узлы `0x08C/0x02D/0x02E/0x041/0x042` MUST следовать после global id table sequence.

Завершение:

- обязательный `0x01C`.

## 5) Как собрать состояние revision (практический алгоритм)

### 5.1 Разбор «в один проход»

Во время прохода по FileNode:

1. Держите контекст:
   - `current_global_id_table` (может меняться внутри manifest)
   - `current_data_signature_group` (для 0x08C, действует до стоп-узлов)
2. Собирайте:
   - `root_objects: dict[root_role, object_id]`
   - `object_changes: list[declaration_or_revision]` (с `oid`, `ref`, `jcid`, `refcount`, signature group)
   - `refcount_overrides: list[...]` (0x084)

### 5.2 Dependency revision

Если `ridDependent != {{0},0}`:

- начальное состояние берите из dependency revision,
- затем накладывайте изменения текущего manifest:
  - «последняя запись» по `oid` определяет данные и refcount (если refcount не перекрыт override-узлом).

Практика реализации:

- dependency chain лучше разрешать сверху вниз (топологически):
  - сначала распарсить все revision manifests (без вычисления итогового состояния),
  - затем вычислять состояние, начиная с тех, у кого dependency отсутствует.

### 5.3 Overrides refcount (0x084)

- применяйте overrides после разбора соответствующего объекта/группы;
- учитывайте правило, что `ObjectInfoDependencyOverridesFND` может идти после object group list ref (в `.one`).

## 6) Достижимость и refcount (2.1.5)

Спецификация даёт смысл refcount:

- для non-root объекта — число объектов, которые на него напрямую ссылаются, при условии, что ссылающийся объект достижим от root objects (или сам root).
- для root объекта — refcount = refcount(non-root) + 1.

Практика:

- на первом этапе можно «доверять» refcount из файла и не пересчитывать граф (это ускоряет),
- позже можно добавить валидацию: построить граф по object references из `ObjectSpaceObjectPropSet` и проверить refcount.

