-- Единый журнал обращений и «заявки» по определению из README:
-- заявка — номер телефона, обратившийся хотя бы раз за август по Москве; канал — канал первого обращения.

-- Ручной лид в CRM — это копия звонка, если за 3 часа до него с этого номера был звонок.
-- Иначе это обращение, которого нет в других системах: человек пришёл в клинику сам.
CREATE TABLE crm_manual_leads AS
SELECT
    l.*,
    EXISTS (
        SELECT 1 FROM stg_marketing c
        WHERE c.event_type = 'call'
          AND c.phone = l.phone
          AND c.created_msk BETWEEN datetime(l.created_msk, '-3 hours') AND l.created_msk
    ) AS is_call_copy
FROM stg_crm l
WHERE l.created_by = 'admin';

CREATE TABLE contacts AS
SELECT phone, created_msk AS contact_at, created_at_utc AS contact_at_utc,
       event_type AS kind, channel, 'marketing' AS source, event_id AS ref, is_missed
FROM stg_marketing
WHERE NOT is_test_utm AND phone NOT IN (SELECT phone FROM test_phones)
UNION ALL
SELECT phone, created_msk, created_at_utc, 'widget', channel, 'booking', booking_id, 0
FROM stg_booking
UNION ALL
SELECT phone, created_msk, NULL, 'walk_in', label_channel, 'crm', lead_id, 0
FROM crm_manual_leads
WHERE NOT is_call_copy AND phone NOT IN (SELECT phone FROM test_phones);

CREATE INDEX ix_manual_phone ON crm_manual_leads (phone, created_msk);

CREATE TABLE august_contacts AS
SELECT
    c.*,
    ROW_NUMBER() OVER w                              AS n_in_month,
    LAG(kind) OVER w                                 AS prev_kind,
    LAG(contact_at) OVER w                           AS prev_at,
    COALESCE(SUM(kind = 'call') OVER (PARTITION BY phone ORDER BY contact_at
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS calls_before
FROM contacts c
WHERE contact_at >= '2026-08-01' AND contact_at < '2026-09-01'
WINDOW w AS (PARTITION BY phone ORDER BY contact_at);

CREATE INDEX ix_august_ref ON august_contacts (ref);

CREATE TABLE requests AS
SELECT
    phone,
    contact_at      AS first_contact_at,
    contact_at_utc  AS first_contact_at_utc,
    kind            AS first_kind,
    COALESCE(channel, 'unknown') AS channel,
    source          AS first_source,
    EXISTS (SELECT 1 FROM stg_crm l
            WHERE l.phone = r.phone AND l.status = 'visited'
              AND l.created_msk >= '2026-08-01' AND l.created_msk < '2026-09-01') AS visited
FROM august_contacts r
WHERE n_in_month = 1;

CREATE INDEX ix_requests_phone ON requests (phone);
