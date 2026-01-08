# (Опционально) Передача через FSSHTTP (2.7–2.8)

Если ваша цель — поддержка файлов, полученных через протокол синхронизации, вам понадобится раздел 2.7 (и, реже, 2.8).

## 1) Что можно отложить

Для «локального» чтения `.one/.onetoc2` FSSHTTP не нужен. Его имеет смысл делать после того, как:

- готов парсер обычного файла;
- у вас есть модель object spaces/revisions/objects.

## 2) Header Cell derivation (2.7.2)

Спецификация описывает derivation `Cell Manifest Current Revision Extended GUID` из `Header`:

1. `eguid1 = { guid=Header.guidFile, n=Header.crcName }`
2. `eguid2 = { guid=Header.guidAncestor, n=Header.ffvLastCodeThatWroteToThisFile }`
3. `current = eguid1 XOR eguid2 XOR {{F5367D2F-F167-4830-A9C3-68F8336A2A09}, 0}`

Практика:

- реализуйте XOR для ExtendedGUID как XOR всех 16 байт GUID и XOR `n` как `u32`.

## 3) Storage Manifest (2.7.1)

По типу файла выбираются schema GUID:

- `.one` => `{1F937CB4-B26F-445F-B9F8-17E20160E461}`
- `.onetoc2` => `{E4DBFD38-E5C7-408B-A8A1-0E7B421E1F5F}`

Далее идут root context/cell пары (см. PDF) — это уже интеграция с `[MS-FSSHTTP]` и `[MS-FSSHTTPB]`.

