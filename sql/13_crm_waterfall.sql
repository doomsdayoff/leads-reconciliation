-- Как лиды CRM за август (по Москве) превращаются в число заявок.
WITH numbered AS (
    SELECT l.*,
           CASE WHEN external_id IS NULL THEN 1
                ELSE ROW_NUMBER() OVER (PARTITION BY external_id ORDER BY created_msk) END AS delivery_n
    FROM stg_crm l
),
august AS (
    SELECT n.*, phone IN (SELECT phone FROM test_phones) AS is_test
    FROM numbered n
    WHERE created_msk >= '2026-08-01' AND created_msk < '2026-09-01'
),
ranked AS (
    SELECT a.*, ROW_NUMBER() OVER (PARTITION BY phone ORDER BY created_msk) AS phone_n
    FROM august a
    WHERE NOT is_test AND delivery_n = 1
)
SELECT 'test' AS category, count(*) AS rows FROM august WHERE is_test
UNION ALL
SELECT 'webhook_retry', count(*) FROM august WHERE NOT is_test AND delivery_n > 1
UNION ALL
SELECT 'repeat_phone', count(*) FROM ranked WHERE phone_n > 1
UNION ALL
SELECT 'first', count(*) FROM ranked WHERE phone_n = 1;
