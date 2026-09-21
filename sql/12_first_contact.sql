-- Где случилось первое обращение каждой заявки: в отчёт сквозной аналитики попадает только часть.
SELECT
    CASE
        WHEN first_kind IN ('form', 'call') AND substr(first_contact_at_utc, 1, 7) = '2026-08' THEN 'marketing'
        WHEN first_kind IN ('form', 'call')                                                   THEN 'boundary_in'
        WHEN first_kind = 'widget'                                                            THEN 'widget'
        ELSE 'walk_in'
    END AS first_contact,
    count(*) AS requests
FROM requests
GROUP BY 1;
