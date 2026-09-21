-- Каналы: что показывал отчёт сквозной аналитики и что получается после сверки.
WITH reported AS (
    SELECT COALESCE(channel, 'unknown') AS channel, count(*) AS reported_leads
    FROM stg_marketing
    WHERE created_at_utc >= '2026-08-01' AND created_at_utc < '2026-09-01'
    GROUP BY 1
),
actual AS (
    SELECT channel, count(*) AS requests, sum(visited) AS visits
    FROM requests
    GROUP BY channel
)
SELECT
    s.channel,
    CAST(s.spend_rub AS INTEGER)                                   AS spend_rub,
    COALESCE(r.reported_leads, 0)                                  AS reported_leads,
    a.requests,
    a.visits,
    ROUND(CAST(s.spend_rub AS REAL) / NULLIF(r.reported_leads, 0)) AS reported_cpl,
    ROUND(CAST(s.spend_rub AS REAL) / NULLIF(a.requests, 0))       AS actual_cpl,
    ROUND(CAST(s.spend_rub AS REAL) / NULLIF(a.visits, 0))         AS cost_per_visit,
    ROUND(100.0 * a.visits / a.requests, 1)                        AS visit_rate_pct
FROM ad_spend s
LEFT JOIN reported r USING (channel)
LEFT JOIN actual a USING (channel)
ORDER BY CAST(s.spend_rub AS INTEGER) DESC, a.requests DESC;
