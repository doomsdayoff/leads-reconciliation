"""Проверка метода: SQL видит только «грязные» CSV, генератор знает правду о каждом человеке.

Если нормализация телефонов, перевод часовых поясов или сопоставление источников
где-то ошибаются, числа разойдутся с эталоном.
"""
import filecmp
import json

import pytest

import generate_data
import reconcile


@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    truth = generate_data.main(data_dir)
    conn = reconcile.connect(data_dir)
    return data_dir, truth, conn


def by_key(rows, key, value):
    return {row[key]: row[value] for row in rows}


def test_total_and_first_touch_channels(fresh):
    _, truth, conn = fresh
    assert conn.execute("SELECT count(*) FROM requests").fetchone()[0] == truth["unique_requests"]
    channels = by_key(conn.execute("SELECT channel, count(*) AS n FROM requests GROUP BY channel").fetchall(),
                      "channel", "n")
    assert channels == truth["unique_by_first_touch_channel"]


def test_marketing_dashboard_breakdown(fresh):
    _, truth, conn = fresh
    sql = by_key(reconcile.query(conn, "marketing_waterfall"), "category", "rows")
    expected = {k: v for k, v in truth["marketing"].items() if k != "raw" and v}
    assert sql == expected
    assert sum(sql.values()) == truth["marketing"]["raw"]


def test_where_first_contacts_happened(fresh):
    _, truth, conn = fresh
    sql = by_key(reconcile.query(conn, "first_contact"), "first_contact", "requests")
    assert sql == truth["first_contact_not_in_marketing_dashboard"]


def test_crm_breakdown(fresh):
    _, truth, conn = fresh
    sql = by_key(reconcile.query(conn, "crm_waterfall"), "category", "rows")
    assert sql == {k: v for k, v in truth["crm"].items() if k != "raw"}
    assert sum(sql.values()) == truth["crm"]["raw"]


def test_requests_missing_in_crm(fresh):
    _, truth, conn = fresh
    sql = by_key(reconcile.query(conn, "not_in_crm"), "reason", "requests")
    assert sql == {k: v for k, v in truth["not_in_crm"].items() if v}


def test_lost_webhooks_are_found(fresh):
    _, truth, conn = fresh
    checks = by_key(reconcile.query(conn, "quality_checks"), "check_name", "found")
    assert checks["Запись из виджета не дошла до CRM"] == truth["lost_webhook_bookings"]


def test_waterfalls_balance(fresh):
    _, truth, conn = fresh
    result = reconcile.reconcile(conn)  # бросает исключение, если водопад не сходится с итогом
    assert result["total"] == truth["unique_requests"]


def test_phones_arrive_in_many_formats_and_all_normalize(fresh):
    data_dir, _, conn = fresh
    raw = {row["phone"][:3] for row in conn.execute("SELECT phone FROM crm_leads").fetchall()}
    assert len(raw) >= 5, "в данных должны быть разные форматы, иначе проверка нормализации ничего не значит"
    checks = by_key(reconcile.query(conn, "quality_checks"), "check_name", "found")
    assert checks["Телефон не приводится к 11 цифрам"] == 0


def test_committed_data_matches_generator(fresh):
    """Данные в репозитории — ровно то, что выдаёт генератор: README не расходится с кодом."""
    data_dir, truth, _ = fresh
    for path in data_dir.iterdir():
        assert filecmp.cmp(path, reconcile.DATA / path.name, shallow=False), path.name
    assert json.loads((reconcile.DATA / "_truth.json").read_text(encoding="utf-8")) == truth
