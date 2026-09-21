-- Заявки августа, по которым в CRM за август нет ни одного лида, и почему.
-- Причины проверяются по порядку: первая подошедшая и считается.
SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM stg_crm l WHERE l.phone = r.phone AND l.created_msk < '2026-08-01')
            THEN 'lead_in_previous_month'
        WHEN EXISTS (SELECT 1 FROM stg_marketing c
                     WHERE c.phone = r.phone AND c.event_type = 'call' AND c.is_missed = 1
                       AND NOT EXISTS (SELECT 1 FROM crm_manual_leads l
                                       WHERE l.phone = c.phone
                                         AND l.created_msk BETWEEN c.created_msk AND datetime(c.created_msk, '+3 hours')))
            THEN 'missed_no_callback'
        WHEN EXISTS (SELECT 1 FROM stg_booking b
                     WHERE b.phone = r.phone
                       AND NOT EXISTS (SELECT 1 FROM stg_crm l WHERE l.external_id = b.booking_id))
            THEN 'lost_webhook'
        ELSE 'other'
    END AS reason,
    count(*) AS requests
FROM requests r
WHERE NOT EXISTS (SELECT 1 FROM stg_crm l
                  WHERE l.phone = r.phone AND l.created_msk >= '2026-08-01' AND l.created_msk < '2026-09-01')
GROUP BY 1;
