# Запись структур: что и куда добавлять (минимальный writer)

Этот файл дополняет `docs/ms-onestore/19-writer-basics.md` и описывает «минимальный набор действий», чтобы вносить изменения без полной реализации всех оптимизаций (defrag, hashed chunks и т.д.).

## 1) Что считать «изменением» файла

Практически любые изменения содержимого (объекты/свойства/вложенные данные) требуют:

- дописать новые структуры (append)
- записать транзакцию
- обновить `Header.*Version*` поля

## 2) Добавление/обновление объекта (property set object)

Чтобы изменить состояние объекта в revision:

1. Сформируйте новый `ObjectSpaceObjectPropSet` (2.6.1) с новым `PropertySet`.
2. Запишите его в новый blob (chunk).
3. Добавьте в соответствующий revision manifest один из узлов:
   - `ObjectRevisionWithRefCountFNDX (0x041)` или `ObjectRevisionWithRefCount2FNDX (0x042)` — если объект уже существует;
   - или соответствующий `ObjectDeclaration*` — если объект вводится впервые.
4. Убедитесь, что `JCID` объекта не меняется при ревизии.
5. Зафиксируйте изменения транзакцией (обновив file node list, в котором лежит revision manifest).

## 3) Добавление root object

Внутри revision manifest добавьте:

- `.one`: `RootObjectReference3FND (0x05A)`
- `.onetoc2`: `RootObjectReference2FNDX (0x059)`

с новым `RootRole` (не дублировать существующий).

## 4) Добавление file data (вложений)

1. Запишите `FileDataStoreObject` (2.6.13) с бинарным `FileData`.
2. Добавьте `FileDataStoreObjectReferenceFND (0x094)` в file node list, на который указывает `FileDataStoreListReferenceFND (0x090)` из root list.
3. Создайте/обновите объект типа file data:
   - `ObjectDeclarationFileData3RefCountFND (0x072)` или `0x073`
   - `FileDataReference` с `<ifndf>{GUID}</ifndf>` на `guidReference` из (2)

## 5) Обновление RevisionManifestList

Если вы создаёте новую revision:

1. В revision manifest list добавьте новый revision manifest (Start* ... End).
2. Добавьте/обновите ассоциации ролей/контекстов:
   - `RevisionRoleDeclarationFND (0x05C)` или `RevisionRoleAndContextDeclarationFND (0x05D)`
3. Помните правило: для каждой пары (context, role) действует последнее присваивание.

## 6) Global ID Table при записи

На первом этапе проще:

- не пытаться оптимально переиспользовать dependency mapping (`0x025/0x026`);
- формировать «полную» таблицу через `0x024` (index+guid) там, где она нужна;
- строго соблюдать область действия таблицы (см. `docs/ms-onestore/09-file-node-types-global-id-table.md`).

