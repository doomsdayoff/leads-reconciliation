-- Как отчёт сквозной аналитики (строки за август по UTC) превращается в число заявок.
WITH dashboard AS (
    SELECT * FROM stg_marketing
    WHERE created_at_utc >= '2026-08-01' AND created_at_utc < '2026-09-01'
),
classified AS (
    SELECT
        CASE
            WHEN d.is_test_utm OR d.phone IN (SELECT phone FROM test_phones) THEN 'test'
            WHEN d.created_msk >= '2026-09-01'                              THEN 'boundary_out'
            WHEN a.n_in_month = 1                                           THEN 'first'
            WHEN d.event_type = 'form' AND a.prev_kind = 'form'
                 AND (julianday(a.contact_at) - julianday(a.prev_at)) * 1440 <= 10
                                                                            THEN 'double_submit'
            WHEN d.event_type = 'call' AND a.calls_before > 0               THEN 'repeat_call'
            ELSE 'other_repeat'
        END AS category
    FROM dashboard d
    LEFT JOIN august_contacts a ON a.ref = d.event_id
)
SELECT category, count(*) AS rows
FROM classified
GROUP BY category;
