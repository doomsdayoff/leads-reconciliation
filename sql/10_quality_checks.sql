-- Проверки качества данных: каждая строка — одна проверка и число найденных записей.
SELECT 'Телефон не приводится к 11 цифрам' AS check_name, count(*) AS found, 'все источники' AS scope
FROM (SELECT phone FROM stg_marketing UNION ALL SELECT phone FROM stg_booking UNION ALL SELECT phone FROM stg_crm)
WHERE length(phone) <> 11 OR phone GLOB '*[^0-9]*'
UNION ALL
SELECT 'Тестовые заявки QA', count(*), 'сквозная аналитика'
FROM stg_marketing WHERE is_test_utm OR phone IN (SELECT phone FROM test_phones)
UNION ALL
SELECT 'Тестовые заявки QA', count(*), 'CRM'
FROM stg_crm WHERE phone IN (SELECT phone FROM test_phones)
UNION ALL
SELECT 'Повторная доставка вебхука: external_id уже встречался', count(*), 'CRM'
FROM (SELECT ROW_NUMBER() OVER (PARTITION BY external_id ORDER BY created_msk) AS n
      FROM stg_crm WHERE external_id IS NOT NULL)
WHERE n > 1
UNION ALL
SELECT 'Запись из виджета не дошла до CRM', count(*), 'сервис записи'
FROM stg_booking b
WHERE NOT EXISTS (SELECT 1 FROM stg_crm l WHERE l.external_id = b.booking_id)
UNION ALL
SELECT 'Пропущенный звонок без перезвона за 3 часа', count(*), 'коллтрекинг'
FROM stg_marketing c
WHERE c.event_type = 'call' AND c.is_missed = 1
  AND NOT EXISTS (SELECT 1 FROM crm_manual_leads l
                  WHERE l.phone = c.phone
                    AND l.created_msk BETWEEN c.created_msk AND datetime(c.created_msk, '+3 hours'))
UNION ALL
SELECT 'Ручная метка источника не из справочника', count(*), 'CRM'
FROM stg_crm
WHERE created_by = 'admin' AND label_channel IS NULL
UNION ALL
SELECT 'Метка в CRM расходится с коллтрекингом', count(*), 'CRM'
FROM crm_manual_leads l
JOIN stg_marketing c ON c.event_type = 'call' AND c.phone = l.phone
                    AND c.created_msk BETWEEN datetime(l.created_msk, '-3 hours') AND l.created_msk
WHERE l.label_channel IS NOT NULL AND l.label_channel <> c.channel
UNION ALL
SELECT 'Событие в разных месяцах по UTC и по Москве', count(*), 'сквозная аналитика'
FROM stg_marketing
WHERE substr(created_at_utc, 1, 7) <> substr(created_msk, 1, 7);
