-- По дням: записи через виджет и лиды, которые из них появились в CRM.
WITH days AS (
    SELECT date(created_msk) AS day, count(*) AS bookings
    FROM stg_booking
    WHERE created_msk >= '2026-08-01' AND created_msk < '2026-09-01'
    GROUP BY 1
),
delivered AS (
    SELECT date(b.created_msk) AS day, count(DISTINCT b.booking_id) AS crm_leads
    FROM stg_booking b
    JOIN stg_crm l ON l.external_id = b.booking_id
    WHERE b.created_msk >= '2026-08-01' AND b.created_msk < '2026-09-01'
    GROUP BY 1
)
SELECT d.day, d.bookings, COALESCE(v.crm_leads, 0) AS crm_leads
FROM days d
LEFT JOIN delivered v USING (day)
ORDER BY d.day;
