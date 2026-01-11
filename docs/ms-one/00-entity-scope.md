# MS-ONE entity scope (v1)

v1 цель: поверх уже реализованного слоя `onestore` поднять минимально полезный граф сущностей для `.one`.

## Поддерживаемые сущности (v1)

- `jcidSectionNode`
- `jcidPageSeriesNode`
- `jcidPageNode`
- `jcidTitleNode`
- `jcidOutlineNode`
- `jcidOutlineElementNode`
- content nodes (частично): `jcidRichTextOENode`
- таблицы (частично): `jcidTableNode`, `jcidTableRowNode`, `jcidTableCellNode`
- metadata nodes (пока как raw): `jcidSectionMetaData` (и др. по мере необходимости)

## Политика деградации

- Неизвестный `JCID` или незнакомый `PropertyID` не приводит к падению в tolerant режиме.
- Узлы с неизвестным `JCID` возвращаются как `UnknownNode` с сохранением `raw_properties`.
