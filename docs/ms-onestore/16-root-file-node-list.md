# Root File Node List (2.1.14): перечисление object spaces

Root file node list — это «вход» в содержимое файла: он перечисляет object spaces и отмечает, какой из них root.

## 1) Точка входа

Root list MUST начинаться с `FileNodeListFragment`, на который указывает:

- `Header.fcrFileNodeListRoot` (2.3.1)

Далее это обычный file node list, который может быть разбит на фрагменты (2.4.1/2.4.2).

## 2) Разрешённые FileNode в root list (MUST, 2.1.14)

Root file node list MUST содержать только следующие узлы (и никакие другие):

- **one or more** `ObjectSpaceManifestListReferenceFND (FileNodeID=0x008)` — ссылки на object space manifest lists
- **one** `ObjectSpaceManifestRootFND (FileNodeID=0x004)` — какой object space является root
- **zero or one** `FileDataStoreListReferenceFND (FileNodeID=0x090)` — список file data objects (вложений)

Практика:

- в строгом режиме падайте, если встречаете другой `FileNodeID`;
- в tolerant режиме — сохраняйте unknown nodes, но не используйте их для построения модели.

## 3) Алгоритм извлечения object spaces

1. Соберите все `ObjectSpaceManifestListReferenceFND`:
   - `gosid` (ExtendedGUID) = identity object space
   - `ref` (FileNodeChunkReference) = ссылка на object space manifest list
2. Прочитайте единственный `ObjectSpaceManifestRootFND.gosidRoot` и проверьте, что он совпадает с одним из `gosid` из (1).
3. Для каждого `gosid`:
   - откройте object space manifest list по `ref`,
   - примените правила из `docs/ms-onestore/08-file-node-types-manifests.md` (StartFND + last RevisionManifestListReferenceFND).

## 4) Связь с file type

Root list присутствует и в `.one`, и в `.onetoc2`. Различия появляются позже:

- в revision manifests (`Start4` vs `Start6/7`)
- в форматах global id table (2.1.3)

