# Контейнеры значений свойств: 2.6.8 и 2.6.9

Эти структуры лежат внутри `PropertySet.rgData` и используются для переменных/иерархических значений.

## 1) prtFourBytesOfLengthFollowedByData (2.6.8)

Назначение:

- хранит blob произвольной длины для свойства типа `0x7 (FourBytesOfLengthFollowedByData)`.

Структура:

- `cb: u32` — длина `Data` в байтах, MUST < `0x40000000`
- `Data: bytes[cb]`

Итого размер контейнера = `cb + 4`.

Реализация при чтении `PropertySet.rgData`:

1. прочитать `cb`
2. проверить верхнюю границу (`cb < 0x40000000`) и что `cb` не выходит за границы `rgData`
3. прочитать `Data`

Вывод:

- возвращайте как `bytes` (без интерпретации); смысл зависит от `PropertyID.id` (см. `[MS-ONE]`).

## 2) prtArrayOfPropertyValues (2.6.9)

Назначение:

- хранит массив значений одного типа (в текущей версии spec — массив вложенных property sets).

Структура:

- `cProperties: u32` — число элементов
- `prid: PropertyID (4)` — опционально:
  - MUST NOT present, если `cProperties == 0`
  - MUST present, если `cProperties > 0`
  - `PropertyID.type MUST be 0x11 ("PropertySet")`
  - `PropertyID.id` и `PropertyID.boolValue` игнорируются
- `Data: bytes` — последовательность `cProperties` элементов, каждый элемент имеет размер, заданный `prid.type`

Практика:

- поскольку `prid.type` обязана быть `0x11`, `Data` — это `cProperties` подряд идущих `PropertySet` структур.

Алгоритм парсинга:

1. прочитать `cProperties`
2. если `cProperties == 0`: вернуть пустой список
3. иначе прочитать `prid` и проверить `prid.type == 0x11`
4. затем в цикле `cProperties` раз вызвать парсер `PropertySet` из `docs/ms-onestore/12-object-data.md`

Важно про границы:

- `prtArrayOfPropertyValues` живёт внутри `rgData`, поэтому парсер должен работать в «лимитированном» reader/view, чтобы не уйти за пределы массива.

