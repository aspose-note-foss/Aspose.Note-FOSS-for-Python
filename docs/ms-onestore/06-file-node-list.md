# FileNodeListFragment / FileNodeListHeader (2.4.1 / 2.4.2)

File node list физически разбит на фрагменты, а все фрагменты в файле образуют дерево, корень которого указан в `Header.fcrFileNodeListRoot`.

## FileNodeListHeader (2.4.2)

Поля:

- `uintMagic: u64` MUST = `0xA4567AB1F5F7F4C4`
- `FileNodeListID: u32` MUST >= `0x10`
- `nFragmentSequence: u32` (первый фрагмент = 0, далее 1,2,3...)

Инварианты:

- `(FileNodeListID, nFragmentSequence)` уникальна в файле
- все фрагменты одного списка имеют одинаковый `FileNodeListID`

## FileNodeListFragment (2.4.1)

Поля (логически):

- `header: FileNodeListHeader` (16 байт)
- `rgFileNodes: bytes` — поток `FileNode` подряд (переменный)
- `padding: bytes` — игнорировать
- `nextFragment: FileChunkReference64x32` (12 байт)
- `footer: u64` MUST = `0x8BC215C38233BA4B`

Критически важное правило:

Положение `nextFragment` вычисляется **от размера фрагмента**, который приходит из chunk reference (тот, кто на фрагмент ссылается).

Практический парсинг фрагмента:

1. Откройте `view(stp, cb)` где `(stp, cb)` — ссылка на фрагмент.
2. Прочитайте `header` (16 байт) и валидируйте magic.
3. Далее считывайте `FileNode` последовательно:
   - пока не встретили `ChunkTerminatorFND (0x0FF)`, или
   - пока до позиции `nextFragment` осталось меньше 4 байт, или
   - пока не достигли лимита `last_count_by_list_id[FileNodeListID]` (если известен)
   - `ChunkTerminatorFND` MUST содержать **нет данных** и MUST NOT присутствовать в **последнем** фрагменте списка (спецификация 2.4.3).
   - если встретили `ChunkTerminatorFND`, то `nextFragment` MUST быть валидным `FileChunkReference64x32` на следующий `FileNodeListFragment` (spec 2.4.1)
   - если остановились из‑за лимита `last_count_by_list_id[...]`, `nextFragment` MUST be ignored (spec 2.4.1).
4. После окончания `rgFileNodes`:
   - пропустите `padding` (bytes между окончанием узлов и позицией `nextFragment`)
5. Прочитайте `nextFragment` (12 байт) и `footer` (8 байт) по их фиксированным позициям.

Обработка `nextFragment`:

- если это **последний фрагмент списка**, `nextFragment` MUST быть `fcrNil`
- иначе `nextFragment` должен указывать на следующий `FileNodeListFragment`, и `nextFragment.cb` должен включать `header` и `footer` следующего фрагмента

## Дерево фрагментов и сборка логических списков

Стратегия:

- сначала обходите дерево фрагментов от `Header.fcrFileNodeListRoot` и сохраняйте все фрагменты в `fragments_by_id[list_id][seq] = fragment_ref`.
- потом для каждого `list_id` выстраивайте цепочку `seq = 0..N` и считывайте содержимое по порядку.

Это разделяет:

- структуру хранения (дерево)
- логическую структуру (список)
