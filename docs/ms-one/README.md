# [MS-ONE] (entities) — план реализации парсера поверх `onestore`

Этот раздел описывает план реализации чтения сущностей OneNote из спецификации **[MS-ONE]** (см. `ms-one_spec_structure.txt`) на Python, используя уже готовый слой чтения контейнера **[MS-ONESTORE]** (`src/onestore/*`) и документацию в `docs/ms-onestore/*`.

- Основной план: `docs/ms-one/python-implementation-plan.md`

## Текущее состояние реализации

Базовый слой MS-ONE уже реализован:

- Пакет MS-ONE: `src/ms_one/`
- Внутреннее зеркалирование для `aspose.note`: `src/aspose/note/_internal/ms_one/`

См. также:

- Скоуп сущностей v1: `docs/ms-one/00-entity-scope.md`
- MS-ONESTORE (низкоуровневый контейнер): `docs/ms-onestore/README.md`

