-- Приведение трёх источников к общему виду.
-- Телефон → 7XXXXXXXXXX: убираем разделители, ведущую 8 меняем на 7, к 10 цифрам добавляем 7.
-- Время → Москва: сквозная аналитика и сервис записи пишут UTC, CRM — московское время.
-- Слой материализуется в таблицы с индексами: дальше по нему много коррелированных подзапросов.

CREATE TABLE test_phones (phone TEXT PRIMARY KEY);
INSERT INTO test_phones VALUES ('79990000000'), ('79990000001'), ('79000000000');  -- номера QA

CREATE TABLE stg_marketing AS
SELECT
    event_id,
    event_type,
    created_at_utc,
    datetime(created_at_utc, '+3 hours')              AS created_msk,
    CASE WHEN length(d) = 11 AND d LIKE '8%' THEN '7' || substr(d, 2)
         WHEN length(d) = 10 THEN '7' || d
         ELSE d END                                   AS phone,
    m.channel,
    CAST(NULLIF(call_duration_sec, '') AS INTEGER)    AS call_duration_sec,
    CAST(is_missed AS INTEGER)                        AS is_missed,
    utm_source = 'test'                               AS is_test_utm
FROM (
    SELECT *, replace(replace(replace(replace(replace(phone, ' ', ''), '-', ''), '(', ''), ')', ''), '+', '') AS d
    FROM marketing_events
) e
LEFT JOIN utm_mapping m USING (utm_source, utm_medium);

CREATE TABLE stg_booking AS
SELECT
    booking_id,
    created_at_utc,
    datetime(created_at_utc, '+3 hours')              AS created_msk,
    CASE WHEN length(d) = 11 AND d LIKE '8%' THEN '7' || substr(d, 2)
         WHEN length(d) = 10 THEN '7' || d
         ELSE d END                                   AS phone,
    m.channel,
    status
FROM (
    SELECT *, replace(replace(replace(replace(replace(phone, ' ', ''), '-', ''), '(', ''), ')', ''), '+', '') AS d
    FROM booking_requests
) b
LEFT JOIN utm_mapping m USING (utm_source, utm_medium);

CREATE TABLE stg_crm AS
SELECT
    lead_id,
    created_at                                        AS created_msk,
    CASE WHEN length(d) = 11 AND d LIKE '8%' THEN '7' || substr(d, 2)
         WHEN length(d) = 10 THEN '7' || d
         ELSE d END                                   AS phone,
    trim(l.source_label)                              AS source_label,
    s.channel                                         AS label_channel,
    NULLIF(external_id, '')                           AS external_id,
    created_by,
    status
FROM (
    SELECT *, replace(replace(replace(replace(replace(phone, ' ', ''), '-', ''), '(', ''), ')', ''), '+', '') AS d
    FROM crm_leads
) l
LEFT JOIN crm_source_mapping s ON s.source_label = trim(l.source_label);

CREATE INDEX ix_marketing_phone ON stg_marketing (phone, event_type, created_msk);
CREATE INDEX ix_booking_phone ON stg_booking (phone);
CREATE INDEX ix_crm_phone ON stg_crm (phone, created_msk);
CREATE INDEX ix_crm_external ON stg_crm (external_id);
