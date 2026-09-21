"""Сверка заявок из трёх источников: загрузка CSV в SQLite, запросы из sql/, таблицы и графики.

    python reconcile.py        # results/*.csv, results/summary.md, charts/*.png
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DATA, SQL, RESULTS, CHARTS = ROOT / "data", ROOT / "sql", ROOT / "results", ROOT / "charts"

TABLES = ["marketing_events", "crm_leads", "booking_requests", "ad_spend", "utm_mapping", "crm_source_mapping"]
LAYERS = ["01_staging.sql", "02_requests.sql"]  # нормализация и единый журнал обращений
QUERIES = {
    "quality_checks": "10_quality_checks.sql",
    "marketing_waterfall": "11_marketing_waterfall.sql",
    "first_contact": "12_first_contact.sql",
    "crm_waterfall": "13_crm_waterfall.sql",
    "not_in_crm": "14_not_in_crm.sql",
    "channels": "15_channels.sql",
    "daily_widget": "16_daily_widget.sql",
}
CHANNEL_NAMES = {
    "yandex_direct": "Яндекс Директ", "vk_ads": "VK Реклама", "2gis": "2ГИС", "yandex_maps": "Яндекс Карты",
    "seo": "SEO", "referral": "Прямые и рекомендации", "offline": "Пришли сами", "unknown": "Не определён",
}


def connect(data_dir=DATA):
    """Все исходные таблицы — как есть, текстом; приведение типов и форматов — в SQL."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for table in TABLES:
        with open(data_dir / f"{table}.csv", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in header)})")
            conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(header))})", reader)
    for name in LAYERS:
        conn.executescript((SQL / name).read_text(encoding="utf-8"))
    return conn


def query(conn, name):
    rows = conn.execute((SQL / QUERIES[name]).read_text(encoding="utf-8")).fetchall()
    return [dict(row) for row in rows]


def as_dict(rows, key, value):
    return {row[key]: row[value] for row in rows}


def reconcile(conn):
    """Всё, что нужно README и тестам: водопады по источникам, итог, каналы."""
    marketing = as_dict(query(conn, "marketing_waterfall"), "category", "rows")
    first = as_dict(query(conn, "first_contact"), "first_contact", "requests")
    crm = as_dict(query(conn, "crm_waterfall"), "category", "rows")
    not_in_crm = as_dict(query(conn, "not_in_crm"), "reason", "requests")
    total = conn.execute("SELECT count(*) FROM requests").fetchone()[0]

    marketing_steps = [
        ("Отчёт сквозной аналитики", sum(marketing.values())),
        ("Тестовые заявки QA", -marketing.get("test", 0)),
        ("Повторная отправка формы", -marketing.get("double_submit", 0)),
        ("Повторный звонок", -marketing.get("repeat_call", 0)),
        ("Уже обращался другим способом", -marketing.get("other_repeat", 0)),
        ("Ночь на 1 сентября по UTC", -marketing.get("boundary_out", 0)),
        ("Ночь на 1 августа по UTC", first.get("boundary_in", 0)),
        ("Запись через виджет", first.get("widget", 0)),
        ("Пришли в клинику сами", first.get("walk_in", 0)),
    ]
    crm_steps = [
        ("Лиды в CRM", sum(crm.values())),
        ("Тестовые заявки QA", -crm.get("test", 0)),
        ("Повторная доставка вебхука", -crm.get("webhook_retry", 0)),
        ("Повторный лид того же номера", -crm.get("repeat_phone", 0)),
        ("Пропущенный звонок без перезвона", not_in_crm.get("missed_no_callback", 0)),
        ("Запись из виджета не дошла", not_in_crm.get("lost_webhook", 0)),
        ("Лид заведён в июле", not_in_crm.get("lead_in_previous_month", 0)),
        ("Прочее", not_in_crm.get("other", 0)),
    ]
    for title, steps in (("сквозной аналитики", marketing_steps), ("CRM", crm_steps)):
        result = sum(value for _, value in steps)
        if result != total:
            raise AssertionError(f"Водопад {title} не сходится: {result} против {total} заявок")

    booking_rows = conn.execute(
        "SELECT count(*) FROM stg_booking WHERE created_msk >= '2026-08-01' AND created_msk < '2026-09-01'"
    ).fetchone()[0]
    return dict(total=total, marketing_steps=marketing_steps, crm_steps=crm_steps,
                bookings=booking_rows, channels=query(conn, "channels"),
                quality=query(conn, "quality_checks"), daily=query(conn, "daily_widget"))


def save_csv(name, rows):
    with open(RESULTS / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rub(value):
    return "—" if not value else f"{int(value):,}".replace(",", " ") + " ₽"


def summary_markdown(result):
    lines = ["# Результаты сверки: август 2026", "",
             f"Заявок (уникальных номеров, обратившихся в августе по Москве): **{result['total']}**.", "",
             "## Сквозная аналитика → заявки", "", "| Шаг | Строк |", "|---|---:|"]
    lines += [f"| {title} | {value:+d} |" if i else f"| {title} | {value} |"
              for i, (title, value) in enumerate(result["marketing_steps"])]
    lines += [f"| **Заявки** | **{result['total']}** |", "", "## CRM → заявки", "", "| Шаг | Строк |", "|---|---:|"]
    lines += [f"| {title} | {value:+d} |" if i else f"| {title} | {value} |"
              for i, (title, value) in enumerate(result["crm_steps"])]
    lines += [f"| **Заявки** | **{result['total']}** |", "", "## Каналы", "",
              "| Канал | Расход | В отчёте | Заявок | Визитов | CPL по отчёту | CPL фактический | Стоимость визита |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["channels"]:
        lines.append(f"| {CHANNEL_NAMES.get(row['channel'], row['channel'])} | {rub(row['spend_rub']) if row['spend_rub'] else '0 ₽'} | "
                     f"{row['reported_leads']} | {row['requests']} | {row['visits']} | {rub(row['reported_cpl'])} | "
                     f"{rub(row['actual_cpl'])} | {rub(row['cost_per_visit'])} |")
    lines += ["", "## Проверки качества данных", "", "| Проверка | Где | Найдено |", "|---|---|---:|"]
    lines += [f"| {row['check_name']} | {row['scope']} | {row['found']} |" for row in result["quality"]]
    return "\n".join(lines) + "\n"


def draw(result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    ink, muted, plus, minus, total_color = "#1f2933", "#7b8794", "#2f9e44", "#e03131", "#1c7ed6"

    # 1. Водопады двух источников
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharex=True)
    for ax, steps, title in ((axes[0], result["marketing_steps"], "Отчёт сквозной аналитики"),
                             (axes[1], result["crm_steps"], "Лиды в CRM")):
        steps = [s for s in steps if s[1] != 0 or s is steps[0]] + [("Заявки", result["total"])]
        labels, running = [], 0
        for i, (label, value) in enumerate(steps):
            y = len(steps) - 1 - i
            if i == 0 or i == len(steps) - 1:
                left, width, color = 0, value, total_color
                running = value
            else:
                left, width = (running, value) if value > 0 else (running + value, -value)
                color = plus if value > 0 else minus
                running += value
            ax.barh(y, width, left=left, color=color, height=0.62)
            text = f"{value}" if i in (0, len(steps) - 1) else f"{value:+d}"
            ax.text(left + width + 25, y, text, va="center", color=ink, fontsize=9)
            labels.append(label)
        ax.set_yticks(range(len(steps)))
        ax.set_yticklabels(list(reversed(labels)))
        ax.set_title(title, loc="left", fontsize=12, color=ink)
        ax.axvline(result["total"], color=muted, linestyle=":", linewidth=1)
        ax.tick_params(colors=muted)
    axes[1].set_xlim(0, max(result["marketing_steps"][0][1], result["crm_steps"][0][1]) * 1.18)
    fig.suptitle(f"Две системы — две разные цифры, заявок на самом деле {result['total']}", x=0.01, ha="left",
                 fontsize=13, color=ink)
    fig.tight_layout()
    fig.savefig(CHARTS / "waterfall.png", dpi=150)
    plt.close(fig)

    # 2. Стоимость заявки и визита по платным каналам
    paid = [r for r in result["channels"] if r["spend_rub"] > 0]
    names = [CHANNEL_NAMES[r["channel"]] for r in paid]
    x = range(len(paid))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.6))
    width = 0.38
    ax1.bar([i - width / 2 for i in x], [r["reported_cpl"] for r in paid], width, label="по отчёту маркетинга", color="#adb5bd")
    ax1.bar([i + width / 2 for i in x], [r["actual_cpl"] for r in paid], width, label="после сверки", color=total_color)
    ax1.set_title("Стоимость заявки, ₽", loc="left", fontsize=12, color=ink)
    ax2.bar(list(x), [r["cost_per_visit"] for r in paid], 0.6, color="#f08c00")
    ax2.set_title("Стоимость визита в клинику, ₽", loc="left", fontsize=12, color=ink)
    for ax in (ax1, ax2):
        ax.set_xticks(list(x))
        ax.set_xticklabels(names)
        ax.tick_params(colors=muted)
        for bar in ax.patches:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{bar.get_height():,.0f}".replace(",", " "),
                    ha="center", va="bottom", fontsize=8, color=ink)
    ax1.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "channels.png", dpi=150)
    plt.close(fig)

    # 3. Записи через виджет и лиды в CRM по дням
    days = [r["day"][5:] for r in result["daily"]]
    fig, ax = plt.subplots(figsize=(13, 3.8))
    ax.bar(days, [r["bookings"] for r in result["daily"]], color="#ced4da", label="записей через виджет")
    ax.plot(days, [r["crm_leads"] for r in result["daily"]], color=total_color, marker="o", markersize=3,
            label="из них попали в CRM")
    ax.set_title("Сбой вебхуков 14–15 августа: записи были, лидов нет", loc="left", fontsize=12, color=ink)
    ax.tick_params(axis="x", labelrotation=90, labelsize=8, colors=muted)
    ax.tick_params(axis="y", colors=muted)
    ax.set_ylim(0, max(r["bookings"] for r in result["daily"]) * 1.35)
    ax.legend(frameon=False, loc="upper right", ncol=2)
    fig.tight_layout()
    fig.savefig(CHARTS / "widget_outage.png", dpi=150)
    plt.close(fig)


def main():
    RESULTS.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    conn = connect()
    result = reconcile(conn)
    for name in QUERIES:
        save_csv(name, query(conn, name))
    (RESULTS / "summary.md").write_text(summary_markdown(result), encoding="utf-8", newline="\n")
    draw(result)
    print(summary_markdown(result))


if __name__ == "__main__":
    main()
