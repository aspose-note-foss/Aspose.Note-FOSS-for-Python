# MS-ONE entity scope (v1)

v1 цель: поверх уже реализованного слоя `onestore` поднять минимально полезный граф сущностей для `.one`.

## Поддерживаемые сущности (v1)

- `jcidSectionNode`
- `jcidPageSeriesNode`
- `jcidPageNode`
- `jcidTitleNode`
- `jcidOutlineNode`
- `jcidOutlineElementNode`
- content nodes:
	- `jcidRichTextOENode`
	- `jcidNumberListNode` (маркер списка для `OutlineElement`)
	- `jcidImageNode`
	- `jcidEmbeddedFileNode`
	- таблицы: `jcidTableNode`, `jcidTableRowNode`, `jcidTableCellNode`
- metadata nodes:
	- `jcidSectionMetaData` (как raw)
	- `jcidPageMetaData` (как raw; в v1 используется как best-effort «Page leaf» для некоторых файлов)
	- `jcidPageManifestNode`

## Политика деградации

- Неизвестный `JCID` или незнакомый `PropertyID` не приводит к падению в tolerant режиме.
- Узлы с неизвестным `JCID` возвращаются как `UnknownNode` с сохранением `raw_properties`.
- Всякий раз, когда возможно, сохраняем детерминированный порядок детей и делаем best-effort извлечение данных (строки/списки/теги), не блокируя построение дерева.
