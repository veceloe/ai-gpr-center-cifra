# Data Model (Phase 1)

Сущности выведены из `spec.md` (Key Entities) и структуры реестра заказчика. Хранилище — SQLite; типы указаны логически.

## Схема связей

```
CompanyProfile 1──* Assessment
Source 1──* Item
Item   1──* Summary          (версии: машинная и пользовательские)
Item   1──* Assessment       (история оценок)
Item   *──1 Story            (кластер дублей, необязателен)
Item   *──1 Act              (материал как основание события досье, необязателен)
Act    1──* ActEvent         (хронология)
Act    1──* Assessment       (история оценок досье)
Item   1──* Revision         (журнал правок)
Digest *──* Item             (через DigestItem)
```

## Source — источник

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| type | enum | `rss` · `web` · `telegram` · `manual` |
| url | str | адрес ленты, страницы или канала |
| title | str | отображаемое название |
| category | enum | `media` · `regulator` · `telegram` — категория из кейса |
| is_active | bool | отключение без удаления (FR-004) |
| poll_interval_min | int | 15 по умолчанию, 60 для регуляторов |
| last_polled_at | datetime | |
| last_error | str? | фиксация ошибки без остановки сбора (FR-008) |

## Item — материал

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| source_id | FK Source | |
| url | str unique | ключ дедупликации по URL (FR-007) |
| title | str | |
| raw_text | text | извлечённый текст |
| content_hash | str | обнаружение изменения текста по тому же URL |
| published_at | datetime? | |
| published_at_is_approx | bool | дата не найдена, использована дата сбора |
| collected_at | datetime | |
| processed_at | datetime? | для замера времени обработки (FR-080) |
| item_type | enum | `news` · `act` (FR-013) |
| topic | enum | `regulatory` · `reputation` · `competitors` · `trends` (FR-014) |
| is_partial_text | bool | текст закрыт подпиской, обработан анонс |
| is_relevant | bool | результат оценки релевантности профилю (FR-018) |
| is_hidden | bool | скрыт пользователем, обратимо (FR-045) |
| story_id | FK Story? | кластер дублей |
| act_id | FK Act? | связь с досье (FR-036) |
| user_note | text? | рабочая пометка (FR-044) |
| tags | str[] | |

## Summary — саммари с заземлением

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| item_id | FK Item | |
| text | text | итоговое саммари, 3–5 предложений |
| claims | json | список `{statement, quote, char_start, char_end, quote_found, entailed, reject_reason}` — вердикты обеих ступеней заземления (FR-012, FR-090, FR-092, FR-025) |
| entities | json | `{who, what, when, consequences}` (FR-011) |
| author | enum | `ai` · `human` |
| model | str? | идентификатор модели |
| prompt_version | str? | версия промпта (FR-019) |
| created_at | datetime | |
| is_current | bool | текущая отображаемая версия |

Пользовательская правка создаёт новую запись с `author=human`, не удаляя машинную (FR-042).

## Assessment — оценка

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| item_id | FK Item? | оценка новости |
| act_id | FK Act? | оценка досье |
| profile_id | FK CompanyProfile | под каким профилем оценивалось (FR-051) |
| scheme | enum | `npa_k1_k6` · `news_h1_h4` |
| scores | json | `{"К1": 3, "К2": 2, ...}` — целые 0–3 |
| rationales | json | обоснование на каждый критерий |
| index_value | float | вычислено кодом (FR-016) |
| category | enum | Незначительное · Низкое · Среднее · Высокое · Критическое (или Фон · На заметку · Актуально · Горячая тема) |
| escalation_flags | str[] | сработавшие флаги (FR-017) |
| final_category | enum | категория после применения флагов |
| author | enum | `ai` · `human` |
| model | str? | |
| prompt_version | str? | |
| created_at | datetime | |
| is_current | bool | |

Правка одного балла человеком создаёт новую запись с `author=human` и пересчитанным индексом (FR-041). История сохраняется — на ней измеряется точность (FR-081).

## Act — досье НПА

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| act_identifier | str | «ФЗ № 243-ФЗ», «Законопроект № 1215252-8» — ключ связывания |
| doc_type | str | федеральный закон · постановление · проект приказа · указ · концепция · поручение |
| stage | enum | `announcement` · `draft_discussion` · `submitted` · `readings` · `adopted` · `in_force` (FR-032) |
| source_url | str | СОЗД или regulation.gov.ru |
| essence | text | суть и содержание |
| is_tracked | bool | взят на отслеживание (FR-030) |
| is_archived | bool | архивирован после вступления в силу (FR-037) |
| effective_from | date? | дата вступления в силу |
| created_at / updated_at | datetime | |

## ActEvent — хронология досье

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| act_id | FK Act | |
| event_type | enum | `stage_change` · `new_version` · `feedback` · `hearing` · `other` (FR-033) |
| occurred_at | date | |
| description | text | |
| source_item_id | FK Item? | материал-основание |
| version_label | str? | обозначение версии документа |
| document_url | str? | |

Смена стадии порождает событие и инициирует переоценку (FR-034). История оценок досье в `Assessment` даёт динамику влияния (FR-035).

## Story — кластер дублей

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| canonical_title | str | |
| fact_summary | text | сообщаемый факт |
| first_seen_at | datetime | |
| item_count | int | |
| was_split_by_user | bool | пользователь разъединил кластер (FR-062) |

## CompanyProfile — профиль компании

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| name | str | |
| industry | text | |
| products | str[] | |
| regimes | str[] | налоговые режимы, аккредитации, реестры |
| risk_areas | str[] | повышают К4, К5, флаги |
| growth_areas | str[] | повышают К3 при положительном знаке |
| competitors | str[] | |
| noise_markers | str[] | явные признаки шума |
| is_active | bool | активный профиль (FR-052) |

Источник содержания — `docs/company-profile.md`.

## Digest — дайджест

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| recipient | str | руководитель или подразделение |
| created_at | datetime | |
| title | str | |

`DigestItem`: `digest_id`, `item_id`, `position`, `is_excluded` (FR-071).

## Revision — журнал правок

| Поле | Тип | Описание |
|---|---|---|
| id | int PK | |
| entity_type | str | `item` · `summary` · `assessment` |
| entity_id | int | |
| field | str | |
| old_value | json | |
| new_value | json | |
| author | str | |
| created_at | datetime | |

Основание для FR-043 (не перезаписывать отредактированное) и FR-081 (измерение точности по расхождениям машина/человек).

## Инварианты

1. У `Item` в каждый момент ровно одна `Summary` и одна `Assessment` с `is_current = true`.
2. `Assessment.index_value` всегда согласован со `scores` и текущим `config/scoring.yaml`; запись не создаётся моделью напрямую.
3. Каждый балл в `scores` — целое число от 0 до 3.
4. В итоговое саммари попадают только утверждения с `quote_found = true` И `entailed = true`. Отбракованные сохраняются в `claims` с причиной — они нужны для измерения доли отбраковки по причинам (FR-092).
5. `Item.url` уникален; повторное поступление обновляет `content_hash` и при изменении создаёт новую версию текста.
6. Поле, у которого есть запись в `Revision` с `author != ai`, не перезаписывается автоматической переобработкой.
7. `Act` в состоянии `is_archived = true` не участвует в переоценке, но сохраняет хронологию и историю оценок.
