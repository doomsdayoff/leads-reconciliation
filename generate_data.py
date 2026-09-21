"""Синтетические данные для кейса: заявки сети стоматологических клиник за август 2026.

Сначала генерируются реальные обращения людей, затем они «проходят» через три системы
так, как это бывает в жизни: с дублями, потерями, разными часовыми поясами и форматами
телефона. Генератор знает, кто есть кто, и по этому знанию считает эталон
(data/_truth.json) — теми же определениями, что описаны в README.

Анализ (reconcile.py и sql/) эталон не читает: он видит только CSV, как аналитик в жизни.
Тесты сравнивают результат SQL с эталоном.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260901
DATA = Path(__file__).parent / "data"
MSK = timedelta(hours=3)

MONTH_START = datetime(2026, 8, 1)  # границы месяца — по Москве
MONTH_END = datetime(2026, 9, 1)
PERIOD_START = datetime(2026, 7, 29)  # данные с запасом вокруг границ
PERIOD_END = datetime(2026, 9, 3)

# Каналы: доля людей, способы обращения, UTM, доля дошедших до визита
CHANNELS = {
    "yandex_direct": dict(share=0.30, methods={"form": 0.58, "call": 0.30, "widget": 0.12}, utm=("yandex", "cpc"), visit=0.17),
    "vk_ads":        dict(share=0.13, methods={"form": 0.62, "call": 0.25, "widget": 0.13}, utm=("vk", "cpc"), visit=0.11),
    "2gis":          dict(share=0.12, methods={"form": 0.08, "call": 0.70, "widget": 0.22}, utm=("2gis", "referral"), visit=0.34),
    "yandex_maps":   dict(share=0.11, methods={"form": 0.05, "call": 0.65, "widget": 0.30}, utm=("yandex_maps", "organic"), visit=0.36),
    "seo":           dict(share=0.16, methods={"form": 0.30, "call": 0.35, "widget": 0.35}, utm=("google", "organic"), visit=0.27),
    "referral":      dict(share=0.12, methods={"form": 0.05, "call": 0.70, "widget": 0.25}, utm=("(direct)", "(none)"), visit=0.46),
    "offline":       dict(share=0.06, methods={"walk_in": 1.0}, utm=None, visit=0.52),
}
PEOPLE = 3400

# Дефекты сбора данных
DOUBLE_SUBMIT = {"yandex_direct": 0.24}  # на посадочной Директа кнопка «отправить» отвечает с задержкой
DOUBLE_SUBMIT_DEFAULT = 0.03
WEBHOOK_RETRY = 0.04                     # CRM отвечает по таймауту → повторная доставка того же события
REPEAT_CALL = 0.18                       # перезванивают сами в течение недели
MISSED_CALL = 0.10                       # короткий пропущенный звонок
CALLBACK = 0.55                          # доля пропущенных, кому перезвонили
SECOND_METHOD = 0.08                     # позже обратились другим способом
OUTAGE = (datetime(2026, 8, 14, 9, 0), datetime(2026, 8, 15, 19, 0))  # вебхуки виджета не доходили, МСК
TEST_EVENTS = 26
DOUBLE_SUBMIT_WINDOW = timedelta(minutes=10)

SPEND = {"yandex_direct": 420_000, "vk_ads": 180_000, "2gis": 65_000, "yandex_maps": 48_000,
         "seo": 90_000, "referral": 0, "offline": 0}

# Ручные метки источника в CRM: администратор спрашивает «откуда узнали?» и пишет как придётся
LABELS = {
    "yandex_direct": ["Яндекс", "яндекс директ", "Я.Директ", "ЯД", "контекст", "реклама в яндексе"],
    "vk_ads": ["ВК", "вконтакте", "VK", "таргет вк", "реклама вк"],
    "2gis": ["2гис", "2ГИС", "дубльгис", "2 гис"],
    "yandex_maps": ["Яндекс карты", "карты", "яндекс.карты", "Я.Карты"],
    "seo": ["сайт", "нашли в интернете", "гугл", "поиск"],
    "referral": ["сарафан", "по рекомендации", "друзья", "знакомые", "повторный пациент"],
    "offline": ["пришёл сам", "с улицы", "вывеска", "проходил мимо"],
}
NOISE_LABELS = ["", "не помню", "другое", "реклама"]


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.marketing, self.crm, self.bookings = [], [], []
        self.ids = {"mk": 0, "bk": 0, "crm": 0}
        self.contacts = []   # (person, kind, msk, channel, source_row_id) — реальные обращения людей
        self.crm_meta = {}   # lead_id -> (person, is_retry)
        self.missed_no_callback = set()   # person
        self.lost_webhook = set()         # booking_id

    def next_id(self, prefix):
        self.ids[prefix] += 1
        return f"{prefix}-{self.ids[prefix]:06d}"

    def phone(self, digits):
        rng = self.rng
        a, b, c, d = digits[:3], digits[3:6], digits[6:8], digits[8:]
        return rng.choice([f"+7 ({a}) {b}-{c}-{d}", f"8{digits}", f"+7{digits}", digits,
                           f"8 {a} {b} {c} {d}", f"7-{a}-{b}-{c}-{d}", f"8({a}){b}{c}{d}"])

    def crm_lead(self, person, msk, digits, label, external_id, by, status, is_retry=False):
        lead_id = self.next_id("crm")
        self.crm.append(dict(lead_id=lead_id, created_at=local(msk), phone=self.phone(digits),
                             source_label=label, external_id=external_id, created_by=by, status=status))
        self.crm_meta[lead_id] = (person, is_retry)

    def manual_label(self, channel):
        roll = self.rng.random()
        if roll < 0.62:
            return self.rng.choice(LABELS[channel])
        if roll < 0.85:  # записан не тот источник
            return self.rng.choice(LABELS[self.rng.choice([c for c in LABELS if c not in (channel, "offline")])])
        return self.rng.choice(NOISE_LABELS)

    def form(self, person, channel, msk, digits, status):
        rng = self.rng
        utm_source, utm_medium = CHANNELS[channel]["utm"]
        submits = 1
        if rng.random() < DOUBLE_SUBMIT.get(channel, DOUBLE_SUBMIT_DEFAULT):
            submits += rng.choice([1, 1, 2])
        moment = msk
        for n in range(submits):
            if n:
                moment += timedelta(minutes=rng.randint(1, 5), seconds=rng.randrange(60))
            event_id = self.next_id("mk")
            self.marketing.append(dict(event_id=event_id, event_type="form", created_at_utc=utc(moment),
                                       phone=self.phone(digits), utm_source=utm_source, utm_medium=utm_medium,
                                       call_duration_sec="", is_missed=0))
            self.contacts.append((person, "form", moment, channel, event_id))
            # Каждая отправка формы — отдельный вебхук и отдельный лид
            self.integration_lead(person, moment, digits, "Сайт: форма", event_id, status if n == 0 else "new")

    def widget(self, person, channel, msk, digits, status):
        utm_source, utm_medium = CHANNELS[channel]["utm"]
        booking_id = self.next_id("bk")
        self.bookings.append(dict(booking_id=booking_id, created_at_utc=utc(msk), phone=self.phone(digits),
                                  clinic=self.rng.choice(["Центральная", "Северная", "Приморская"]),
                                  utm_source=utm_source, utm_medium=utm_medium,
                                  status=self.rng.choice(["new", "confirmed", "confirmed", "cancelled"])))
        self.contacts.append((person, "widget", msk, channel, booking_id))
        if OUTAGE[0] <= msk < OUTAGE[1]:
            self.lost_webhook.add(booking_id)
            return
        self.integration_lead(person, msk, digits, "Виджет записи", booking_id, status)

    def integration_lead(self, person, moment, digits, label, external_id, status):
        lead_time = moment + timedelta(seconds=self.rng.randint(1, 3))
        self.crm_lead(person, lead_time, digits, label, external_id, "integration", status)
        if self.rng.random() < WEBHOOK_RETRY:
            self.crm_lead(person, lead_time + timedelta(seconds=self.rng.randint(20, 90)), digits, label,
                          external_id, "integration", "new", is_retry=True)

    def call(self, person, channel, msk, digits, status, allow_repeat=True):
        rng = self.rng
        utm_source, utm_medium = CHANNELS[channel]["utm"]
        missed = rng.random() < MISSED_CALL
        event_id = self.next_id("mk")
        self.marketing.append(dict(event_id=event_id, event_type="call", created_at_utc=utc(msk),
                                   phone=f"+7{digits}", utm_source=utm_source, utm_medium=utm_medium,
                                   call_duration_sec=rng.randint(0, 9) if missed else rng.randint(35, 600),
                                   is_missed=int(missed)))
        self.contacts.append((person, "call", msk, channel, event_id))
        if missed and rng.random() >= CALLBACK:
            self.missed_no_callback.add(person)
        else:
            delay = timedelta(minutes=rng.randint(10, 120) if missed else rng.randint(1, 10))
            self.crm_lead(person, msk + delay, digits, self.manual_label(channel), "", "admin", status)
        if allow_repeat and rng.random() < REPEAT_CALL:
            for _ in range(rng.choice([1, 1, 2])):
                again = msk + timedelta(days=rng.randint(1, 6))
                again = again.replace(hour=rng.randint(9, 19), minute=rng.randrange(60))
                event_id = self.next_id("mk")
                self.marketing.append(dict(event_id=event_id, event_type="call", created_at_utc=utc(again),
                                           phone=f"+7{digits}", utm_source=utm_source, utm_medium=utm_medium,
                                           call_duration_sec=rng.randint(35, 400), is_missed=0))
                self.contacts.append((person, "call", again, channel, event_id))


def utc(msk):
    return (msk - MSK).strftime("%Y-%m-%d %H:%M:%S")


def local(msk):
    return msk.strftime("%Y-%m-%d %H:%M:%S")


def in_month(msk):
    return MONTH_START <= msk < MONTH_END


def random_moment(rng, kind):
    day = PERIOD_START + timedelta(days=rng.randrange((PERIOD_END - PERIOD_START).days))
    if kind in ("call", "walk_in"):
        hours = {h: (3 if 10 <= h <= 18 else 1) for h in range(9, 20)}
    else:
        hours = {h: (4 if 19 <= h <= 22 else 2 if 9 <= h <= 18 else 1) for h in range(24)}
    hour = rng.choices(list(hours), weights=list(hours.values()))[0]
    minute = rng.randrange(60)
    if hour == 23:
        minute = rng.randrange(40)  # повторные отправки и копии в CRM не должны уехать в следующие сутки
    return day + timedelta(hours=hour, minutes=minute, seconds=rng.randrange(60))


def generate():
    world = World(SEED)
    rng = world.rng
    people = {}
    used = set()
    for person in range(PEOPLE):
        channel = rng.choices(list(CHANNELS), weights=[c["share"] for c in CHANNELS.values()])[0]
        spec = CHANNELS[channel]
        method = rng.choices(list(spec["methods"]), weights=list(spec["methods"].values()))[0]
        msk = random_moment(rng, method)
        while True:
            digits = "9" + "".join(rng.choice("0123456789") for _ in range(9))
            if digits not in used and not digits.startswith("99900"):
                used.add(digits)
                break
        people[person] = dict(phone="7" + digits, channel=channel)
        status = "visited" if rng.random() < spec["visit"] else rng.choice(["in_work", "booked", "lost", "lost"])

        if method == "form":
            world.form(person, channel, msk, digits, status)
        elif method == "widget":
            world.widget(person, channel, msk, digits, status)
        elif method == "call":
            world.call(person, channel, msk, digits, status)
        else:
            world.crm_lead(person, msk, digits, rng.choice(LABELS["offline"]), "", "admin", status)
            world.contacts.append((person, "walk_in", msk, channel, None))

        if method != "walk_in" and rng.random() < SECOND_METHOD:
            later = (msk + timedelta(days=rng.randint(1, 5))).replace(hour=rng.randint(10, 18))
            if method == "call":
                (world.form if rng.random() < 0.5 else world.widget)(person, channel, later, digits, "new")
            else:
                world.call(person, channel, later, digits, "new", allow_repeat=False)

    for _ in range(TEST_EVENTS):
        msk = datetime(2026, 8, 3) + timedelta(days=rng.randrange(27), hours=rng.randint(10, 17), minutes=rng.randrange(60))
        digits = rng.choice(["9990000000", "9990000001", "9000000000"])
        event_id = world.next_id("mk")
        world.marketing.append(dict(event_id=event_id, event_type="form", created_at_utc=utc(msk), phone=world.phone(digits),
                                    utm_source="test", utm_medium="qa", call_duration_sec="", is_missed=0))
        world.crm_lead(-1, msk + timedelta(seconds=2), digits, "Сайт: форма", event_id, "integration", "new")

    return world, people


def compute_truth(world, people):
    """Эталон по определениям из README, посчитанный по «истинным» личностям, а не по телефонам."""
    august = [c for c in world.contacts if in_month(c[2])]
    first = {}
    for person, kind, msk, channel, ref in sorted(august, key=lambda c: c[2]):
        first.setdefault(person, (kind, msk, ref))

    by_channel = {}
    for person in first:
        channel = people[person]["channel"]
        by_channel[channel] = by_channel.get(channel, 0) + 1

    # Сквозная аналитика: строки, попавшие в август по UTC
    contacts_by_ref = {c[4]: c for c in world.contacts if c[4]}
    person_contacts = {}
    for c in sorted(world.contacts, key=lambda c: c[2]):
        person_contacts.setdefault(c[0], []).append(c)
    mk = dict(raw=0, test=0, boundary_out=0, double_submit=0, repeat_call=0, other_repeat=0, first=0)
    for row in world.marketing:
        if not row["created_at_utc"].startswith("2026-08"):
            continue
        mk["raw"] += 1
        if row["utm_source"] == "test":
            mk["test"] += 1
            continue
        person, kind, msk, _, ref = contacts_by_ref[row["event_id"]]
        if not in_month(msk):
            mk["boundary_out"] += 1
        elif first[person][2] == ref:
            mk["first"] += 1
        else:
            earlier = [c for c in person_contacts[person] if MONTH_START <= c[2] < msk]
            previous = earlier[-1]
            if kind == "form" and previous[1] == "form" and msk - previous[2] <= DOUBLE_SUBMIT_WINDOW:
                mk["double_submit"] += 1
            elif kind == "call" and any(c[1] == "call" for c in earlier):
                mk["repeat_call"] += 1
            else:
                mk["other_repeat"] += 1
    first_kinds = {}
    for person, (kind, msk, ref) in first.items():
        seen_by_marketing = kind in ("form", "call") and utc(msk).startswith("2026-08")
        key = "marketing" if seen_by_marketing else (
            "boundary_in" if kind in ("form", "call") else "widget" if kind == "widget" else "walk_in")
        first_kinds[key] = first_kinds.get(key, 0) + 1

    # CRM: лиды, созданные в августе по Москве
    crm = dict(raw=0, test=0, webhook_retry=0, repeat_phone=0, first=0)
    in_crm = set()
    for row in world.crm:
        if not row["created_at"].startswith("2026-08"):
            continue
        crm["raw"] += 1
        person, is_retry = world.crm_meta[row["lead_id"]]
        if person == -1:
            crm["test"] += 1
        elif is_retry:
            crm["webhook_retry"] += 1
        elif person in in_crm:
            crm["repeat_phone"] += 1
        else:
            in_crm.add(person)
            crm["first"] += 1
    # Почему у заявки нет лида в CRM за август — правила применяются по порядку
    earlier_lead = {world.crm_meta[r["lead_id"]][0] for r in world.crm if r["created_at"] < "2026-08"}
    reasons = dict(lead_in_previous_month=0, missed_no_callback=0, lost_webhook=0, other=0)
    for person in first:
        if person in in_crm:
            continue
        if person in earlier_lead:
            reasons["lead_in_previous_month"] += 1
        elif person in world.missed_no_callback:
            reasons["missed_no_callback"] += 1
        elif any(c[4] in world.lost_webhook for c in person_contacts[person]):
            reasons["lost_webhook"] += 1
        else:
            reasons["other"] += 1
    lost_in_august = sum(1 for b in world.lost_webhook if in_month(contacts_by_ref[b][2]))

    return dict(
        unique_requests=len(first),
        unique_by_first_touch_channel=dict(sorted(by_channel.items())),
        marketing=mk,
        first_contact_not_in_marketing_dashboard=first_kinds,
        crm=crm,
        not_in_crm=reasons,
        lost_webhook_bookings=lost_in_august,
    )


def write(data_dir, name, rows):
    with open(data_dir / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(data_dir=DATA):
    world, people = generate()
    data_dir.mkdir(exist_ok=True)
    world.marketing.sort(key=lambda r: r["created_at_utc"])
    world.crm.sort(key=lambda r: r["created_at"])
    world.bookings.sort(key=lambda r: r["created_at_utc"])
    write(data_dir, "marketing_events.csv", world.marketing)
    write(data_dir, "crm_leads.csv", world.crm)
    write(data_dir, "booking_requests.csv", world.bookings)
    write(data_dir, "ad_spend.csv", [dict(month="2026-08", channel=c, spend_rub=s) for c, s in SPEND.items()])
    write(data_dir, "utm_mapping.csv", [dict(utm_source=c["utm"][0], utm_medium=c["utm"][1], channel=name)
                              for name, c in CHANNELS.items() if c["utm"]])
    write(data_dir, "crm_source_mapping.csv", [dict(source_label=label, channel=ch)
                                     for ch, variants in LABELS.items() for label in variants])
    truth = compute_truth(world, people)
    (data_dir / "_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return truth


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
