# Transaction Log (2.3.3): как выбрать «коммитнутые» FileNode

Важная идея формата: **файловые узлы добавляются, но не удаляются и не модифицируются**, а актуальная «версия» определяется транзакционным журналом и счётчиком `Header.cTransactionsInLog`.

## Концепция

Транзакция состоит из:

- добавленных/изменённых file node lists (на уровне «в список добавили новые FileNode»)
- записей `TransactionEntry` для каждой затронутой file node list
- коммита: увеличение `Header.cTransactionsInLog`

Правило MUST:

- `TransactionEntry` для транзакций с номером **больше** `Header.cTransactionsInLog` игнорируются,
- и **FileNode**, добавленные ими, тоже игнорируются.

## TransactionLogFragment (2.3.3.1)

Структура:

- `sizeTable[]` — массив `TransactionEntry` подряд
- `nextFragment: FileChunkReference64x32` — может быть «undefined» если это фрагмент, содержащий последнюю транзакцию

Практическая реализация:

- читайте фрагменты последовательно по `nextFragment`, но прекращайте, как только по количеству прочитанных «sentinel entries» (см. ниже) вы достигли `Header.cTransactionsInLog`; если текущий фрагмент содержит последнюю транзакцию (`cTransactionsInLog` достигнут), `nextFragment` MUST be ignored (spec 2.3.3.1).

## TransactionEntry (2.3.3.2)

Поля:

- `srcID: u32`
- `TransactionEntrySwitch: u32`

Интерпретация:

- `srcID == 0x00000001` — sentinel конец транзакции; `TransactionEntrySwitch` SHOULD быть CRC всех `TransactionEntry` текущей транзакции
- иначе `TransactionEntrySwitch` MUST быть «новое количество FileNode в file node list `srcID`» после применения транзакции; такая запись MUST добавлять ≥1 `FileNode` в список

## Как применить Transaction Log на практике

Соберите `last_count_by_list_id: dict[int, int]`:

1. Пройдите `TransactionEntry` по фрагментам в порядке хранения.
2. Разбейте поток на транзакции по sentinel (`srcID==1`).
3. Считайте транзакцию валидной, если это одна из первых `Header.cTransactionsInLog`.
4. Для каждой записи внутри транзакции (где `srcID!=1`):
   - `last_count_by_list_id[srcID] = TransactionEntrySwitch`

Дальше при чтении `FileNodeListFragment`:

- считайте узлы до тех пор, пока:
  - не встретили `ChunkTerminatorFND`, или
  - не дошли до `last_count_by_list_id[list_id]` (это наиболее важно, т.к. терминатор может быть не в последнем фрагменте)

## Минимальные тесты

- поток `TransactionEntry` с 2 транзакциями и sentinel: корректно считает `last_count_by_list_id`
- транзакций в файле больше, чем `cTransactionsInLog`: хвост игнорируется
