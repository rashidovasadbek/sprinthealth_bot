# -*- coding: utf-8 -*-
"""Barcha SQL shu yerda.

farm_botda SQL handlerlar ichida sochilib yotardi (main.py, admin_panel.py,
api.py) — bir jadval o'zgarsa qayerlarni tuzatish kerakligi noma'lum edi.
Handlerlar bu modulning funksiyalarini chaqiradi, o'zi SQL yozmaydi.
"""
from datetime import date
from decimal import Decimal

from db.pool import get_pool


# ============================================================
#  KOMPANIYA
# ============================================================

async def get_company(code: str):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM company WHERE code = $1", code)


COMPANY_FIELDS = {"name", "address", "account_no", "bank_name", "inn", "mfo", "director"}


async def update_company_field(company_id: int, field: str, value: str) -> None:
    # Ustun nomi so'rovga to'g'ridan-to'g'ri qo'shiladi — shuning uchun
    # faqat oldindan ma'lum ro'yxatdan bo'lishi shart.
    if field not in COMPANY_FIELDS:
        raise ValueError(f"Ruxsat etilmagan ustun: {field}")
    async with get_pool().acquire() as conn:
        await conn.execute(f"UPDATE company SET {field} = $1 WHERE id = $2", value, company_id)


# ============================================================
#  VILOYATLAR
# ============================================================

async def get_regions():
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM region WHERE active ORDER BY sort_order, name"
        )


async def get_region(region_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM region WHERE id = $1", region_id)


# ============================================================
#  FOYDALANUVCHILAR
# ============================================================

async def get_user(telegram_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM app_user WHERE telegram_id = $1", telegram_id
        )


async def list_users(role: str | None = None):
    async with get_pool().acquire() as conn:
        if role:
            return await conn.fetch(
                "SELECT * FROM app_user WHERE role = $1 ORDER BY active DESC, full_name",
                role,
            )
        return await conn.fetch(
            "SELECT * FROM app_user ORDER BY active DESC, role, full_name"
        )


async def list_managers():
    """Aptekaga biriktirish uchun — faqat faol menejer va adminlar."""
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            """SELECT * FROM app_user
               WHERE active AND role IN ('manager', 'admin')
               ORDER BY full_name"""
        )


async def add_user(telegram_id: int, full_name: str, role: str, phone: str | None = None):
    """Qo'shadi yoki mavjudini qayta faollashtiradi (ID unique)."""
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(
            """INSERT INTO app_user (telegram_id, full_name, role, phone)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (telegram_id) DO UPDATE
                   SET full_name = EXCLUDED.full_name,
                       role      = EXCLUDED.role,
                       phone     = COALESCE(EXCLUDED.phone, app_user.phone),
                       active    = TRUE
               RETURNING *""",
            telegram_id, full_name, role, phone,
        )


async def set_user_active(user_id: int, active: bool) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE app_user SET active = $1 WHERE id = $2", active, user_id)


USER_ROLES = ("admin", "buxgalter", "manager")


async def set_user_role(user_id: int, role: str) -> None:
    if role not in USER_ROLES:
        raise ValueError(f"Noma'lum rol: {role}")
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE app_user SET role = $1 WHERE id = $2", role, user_id)


async def get_user_by_id(user_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM app_user WHERE id = $1", user_id)


async def count_admins() -> int:
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM app_user WHERE role = 'admin' AND active"
        )


async def ensure_bootstrap_admin(telegram_id: int, full_name: str = "Bosh admin") -> bool:
    """Bazada faol admin bo'lmasa — birinchisini yaratadi.

    Bot birinchi marta ishga tushganda hech kim admin panelga kira olmasligi
    muammosini yechadi. Admin bor bo'lsa hech narsa qilmaydi.
    """
    if await count_admins() > 0:
        return False
    await add_user(telegram_id, full_name, "admin")
    return True


# ============================================================
#  DORILAR
# ============================================================

async def get_drugs(only_active: bool = True):
    async with get_pool().acquire() as conn:
        if only_active:
            return await conn.fetch(
                "SELECT * FROM drug WHERE active ORDER BY sort_order, name"
            )
        return await conn.fetch("SELECT * FROM drug ORDER BY active DESC, sort_order, name")


async def get_drug(drug_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM drug WHERE id = $1", drug_id)


async def add_drug(name: str, unit: str, price_no_nds: Decimal,
                   nds_rate: int = 12, box_capacity: int | None = None):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(
            """INSERT INTO drug (name, unit, price_no_nds, nds_rate, box_capacity)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            name, unit, price_no_nds, nds_rate, box_capacity,
        )


DRUG_FIELDS = {"name", "unit", "price_no_nds", "nds_rate", "box_capacity", "sort_order"}


async def update_drug_field(drug_id: int, field: str, value) -> None:
    if field not in DRUG_FIELDS:
        raise ValueError(f"Ruxsat etilmagan ustun: {field}")
    async with get_pool().acquire() as conn:
        await conn.execute(f"UPDATE drug SET {field} = $1 WHERE id = $2", value, drug_id)


async def set_drug_active(drug_id: int, active: bool) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE drug SET active = $1 WHERE id = $2", active, drug_id)


# ============================================================
#  APTEKALAR VA SHARTNOMALAR
# ============================================================

PHARMACY_SELECT = """
    SELECT p.*, r.name AS region_name, r.code AS region_code,
           u.full_name AS manager_name,
           c.id AS contract_id, c.contract_no, c.contract_date
    FROM pharmacy p
    JOIN region r ON p.region_id = r.id
    LEFT JOIN app_user u ON p.manager_user_id = u.id
    LEFT JOIN contract c ON c.pharmacy_id = p.id AND c.company_id = $1
"""


async def search_pharmacies(company_id: int, query: str, limit: int = 30):
    """Nom, INN yoki shartnoma raqami bo'yicha qidiruv.

    Nomda xato bo'lsa ham topadi (pg_trgm similarity).
    Shartnoma raqami start_bron xabarida va'da qilingan, lekin
    so'rovda yo'q edi — "N01/90/02" deb yozilsa hech narsa chiqmasdi.
    """
    async with get_pool().acquire() as conn:
        if not query:
            return await conn.fetch(
                PHARMACY_SELECT + " WHERE p.active ORDER BY p.created_at DESC LIMIT $2",
                company_id, limit,
            )
        return await conn.fetch(
            PHARMACY_SELECT + """
            WHERE p.active
              AND (p.inn = $2
                   OR p.name ILIKE '%' || $2 || '%'
                   OR c.contract_no ILIKE '%' || $2 || '%'
                   OR similarity(lower(p.name), lower($2)) > 0.3)
            ORDER BY similarity(lower(p.name), lower($2)) DESC, p.name
            LIMIT $3""",
            company_id, query, limit,
        )


async def get_pharmacy(company_id: int, pharmacy_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(
            PHARMACY_SELECT + " WHERE p.id = $2", company_id, pharmacy_id
        )


async def find_pharmacies_by_inn(inn: str):
    async with get_pool().acquire() as conn:
        return await conn.fetch("SELECT * FROM pharmacy WHERE inn = $1", inn)


async def create_pharmacy_with_contract(
    company_id: int,
    name: str,
    inn: str,
    region_id: int,
    manager_user_id: int | None,
    phone: str | None,
    account_code: str,
    contract_date: date | None = None,
):
    """Apteka + shartnomani bitta tranzaksiyada yaratadi.

    Shartnoma raqami N{A}/{B}/{C} — masalan N01/90/02:
      A — counter jadvalidan, UPDATE ... RETURNING bilan (atomar).
          farm_botdagi MAX(seq_no)+1 usuli ikki admin bir vaqtda
          qo'shganda bir xil raqam berardi — bu yerda mumkin emas.
          Kamida ikki xonagacha nol bilan to'ldiriladi (1 -> 01),
          99 dan oshsa tabiiy o'sadi (100 -> N100).
      B — viloyat kodi (region.code)
      C — kompaniyaning sho't kodi (bu botda '02')
    """
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            region = await conn.fetchrow("SELECT code FROM region WHERE id = $1", region_id)
            if not region:
                raise ValueError("Viloyat topilmadi")

            pharmacy_id = await conn.fetchval(
                """INSERT INTO pharmacy (name, inn, region_id, manager_user_id, phone)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                name, inn, region_id, manager_user_id, phone,
            )

            seq_no = await conn.fetchval(
                """UPDATE counter SET last_seq = last_seq + 1
                   WHERE company_id = $1 RETURNING last_seq""",
                company_id,
            )
            if seq_no is None:
                raise ValueError("counter jadvalida kompaniya yo'q")

            contract_no = f"N{seq_no:02d}/{region['code']}/{account_code}"
            contract = await conn.fetchrow(
                """INSERT INTO contract (pharmacy_id, company_id, seq_no, region_code,
                                         account_code, contract_no, contract_date)
                   VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, CURRENT_DATE))
                   RETURNING *""",
                pharmacy_id, company_id, seq_no, region["code"],
                account_code, contract_no, contract_date,
            )
            return pharmacy_id, contract


PHARMACY_FIELDS = {"name", "inn", "phone"}


async def update_pharmacy_field(pharmacy_id: int, field: str, value) -> None:
    if field not in PHARMACY_FIELDS:
        raise ValueError(f"Ruxsat etilmagan ustun: {field}")
    async with get_pool().acquire() as conn:
        await conn.execute(
            f"UPDATE pharmacy SET {field} = $1 WHERE id = $2", value, pharmacy_id
        )


async def update_pharmacy_region(pharmacy_id: int, region_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE pharmacy SET region_id = $1 WHERE id = $2", region_id, pharmacy_id
        )


async def update_pharmacy_manager(pharmacy_id: int, manager_user_id: int | None) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE pharmacy SET manager_user_id = $1 WHERE id = $2",
            manager_user_id, pharmacy_id,
        )


async def count_pharmacies_by_region():
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            """SELECT r.id, r.name, r.code, COUNT(p.id) AS n
               FROM region r
               LEFT JOIN pharmacy p ON p.region_id = r.id AND p.active
               GROUP BY r.id, r.name, r.code, r.sort_order
               HAVING COUNT(p.id) > 0
               ORDER BY r.sort_order"""
        )


async def list_pharmacies_by_region(company_id: int, region_id: int, limit: int = 100):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            PHARMACY_SELECT + " WHERE p.active AND p.region_id = $2 ORDER BY p.name LIMIT $3",
            company_id, region_id, limit,
        )


# ============================================================
#  SAVAT
# ============================================================

async def cart_add(user_id: int, drug_id: int, quantity: int) -> int:
    """Savatga qo'shadi. Dori allaqachon bo'lsa — miqdorni ustiga qo'shadi.

    farm_botda har chaqiruv yangi qator yaratardi va savatda bir dori
    bir necha marta ko'rinardi. PRIMARY KEY (user_id, drug_id) buni yechadi.
    """
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO cart (user_id, drug_id, quantity)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id, drug_id) DO UPDATE
                   SET quantity = cart.quantity + EXCLUDED.quantity,
                       updated_at = now()
               RETURNING quantity""",
            user_id, drug_id, quantity,
        )


async def cart_set(user_id: int, drug_id: int, quantity: int) -> None:
    """Miqdorni ustiga qo'shmasdan aniq o'rnatadi (tahrirlash uchun)."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            """INSERT INTO cart (user_id, drug_id, quantity)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id, drug_id) DO UPDATE
                   SET quantity = EXCLUDED.quantity, updated_at = now()""",
            user_id, drug_id, quantity,
        )


async def cart_items(user_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            """SELECT c.drug_id, c.quantity,
                      d.name, d.unit, d.price_no_nds, d.nds_rate, d.box_capacity
               FROM cart c
               JOIN drug d ON c.drug_id = d.id
               WHERE c.user_id = $1
               ORDER BY d.sort_order, d.name""",
            user_id,
        )


async def cart_remove(user_id: int, drug_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "DELETE FROM cart WHERE user_id = $1 AND drug_id = $2", user_id, drug_id
        )


async def cart_clear(user_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM cart WHERE user_id = $1", user_id)


# ============================================================
#  BRONLAR
# ============================================================

async def create_bron(manager_tg_id: int, pharmacy, company_id: int, totals) -> int:
    """Bron + tarkibini bitta tranzaksiyada yozadi va savatni tozalaydi.

    Narx va nom snapshot qilinadi: dori keyin qimmatlashsa yoki nomi
    o'zgarsa, eski bron hujjati o'zgarmaydi.
    """
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            bron_id = await conn.fetchval(
                """INSERT INTO bron (manager_tg_id, pharmacy_id, contract_id, company_id,
                                     doc_contract_no, doc_contract_date, total_sum)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                manager_tg_id, pharmacy["id"], pharmacy["contract_id"], company_id,
                pharmacy["contract_no"], pharmacy["contract_date"], totals.grand_total,
            )
            await conn.executemany(
                """INSERT INTO bron_item (bron_id, drug_id, drug_name, unit, quantity,
                                          price_no_nds, nds_rate, nds_sum, line_total, line_no)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                [
                    (bron_id, ln.drug_id, ln.name, ln.unit, ln.quantity,
                     ln.price_no_nds, ln.nds_rate, ln.nds_sum, ln.line_total, i)
                    for i, ln in enumerate(totals.lines, 1)
                ],
            )
            await conn.execute("DELETE FROM cart WHERE user_id = $1", manager_tg_id)
            return bron_id


BRON_SELECT = """
    SELECT b.*, p.name AS pharmacy_name, p.inn, p.phone AS pharmacy_phone,
           r.name AS region_name, u.full_name AS manager_name
    FROM bron b
    JOIN pharmacy p ON b.pharmacy_id = p.id
    JOIN region r ON p.region_id = r.id
    LEFT JOIN app_user u ON u.telegram_id = b.manager_tg_id
"""


async def get_bron(bron_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(BRON_SELECT + " WHERE b.id = $1", bron_id)


async def get_bron_items(bron_id: int):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            """SELECT drug_id, drug_name AS name, unit, quantity,
                      price_no_nds, nds_rate, nds_sum, line_total
               FROM bron_item WHERE bron_id = $1 ORDER BY line_no""",
            bron_id,
        )


async def set_bron_group_msg(bron_id: int, msg_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE bron SET bron_group_msg_id = $1 WHERE id = $2", msg_id, bron_id
        )


async def mark_sent_to_pay(bron_id: int, by_tg_id: int) -> bool:
    """'new' → 'sent_to_pay'. Allaqachon yuborilgan bo'lsa False qaytaradi.

    Shart WHERE ichida — ikki kishi bir vaqtda tugmani bossa ham
    faqat bittasi o'tadi.
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE bron
               SET status = 'sent_to_pay', sent_to_pay_at = now(), sent_to_pay_by = $2
               WHERE id = $1 AND status = 'new'
               RETURNING id""",
            bron_id, by_tg_id,
        )
        return row is not None


async def revert_sent_to_pay(bron_id: int) -> None:
    """Oplata guruhiga yuborib bo'lmasa statusni qaytaradi.

    Aks holda bron 'sent_to_pay' bo'lib qolib, tugma ham ishlamay
    qolardi — hech kim uni to'lovga yubora olmasdi.
    """
    async with get_pool().acquire() as conn:
        await conn.execute(
            """UPDATE bron
               SET status = 'new', sent_to_pay_at = NULL, sent_to_pay_by = NULL
               WHERE id = $1 AND status = 'sent_to_pay'""",
            bron_id,
        )


async def list_brons(manager_tg_id: int | None = None, limit: int = 20):
    async with get_pool().acquire() as conn:
        if manager_tg_id is not None:
            return await conn.fetch(
                BRON_SELECT + " WHERE b.manager_tg_id = $1 ORDER BY b.id DESC LIMIT $2",
                manager_tg_id, limit,
            )
        return await conn.fetch(BRON_SELECT + " ORDER BY b.id DESC LIMIT $1", limit)


async def list_pending_brons(company_id: int):
    """Hali oplataga yuborilmagan (status='new') bronlar — tarkibi bilan.

    Markirovka sahifasi uchun: bitta so'rovda bron + dorilar (json_agg),
    eskisi birinchi — navbat tartibida.
    """
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            """SELECT b.id, b.doc_contract_no, b.total_sum, b.created_at,
                      p.name AS pharmacy_name, p.inn, p.phone AS pharmacy_phone,
                      r.name AS region_name, u.full_name AS manager_name,
                      COALESCE((
                          SELECT json_agg(json_build_object(
                                     'line_no', i.line_no,
                                     'drug_id', i.drug_id,
                                     'name', i.drug_name,
                                     'unit', i.unit,
                                     'quantity', i.quantity,
                                     'box_capacity', d.box_capacity
                                 ) ORDER BY i.line_no)
                          FROM bron_item i
                          LEFT JOIN drug d ON d.id = i.drug_id
                          WHERE i.bron_id = b.id
                      ), '[]'::json) AS items
               FROM bron b
               JOIN pharmacy p ON b.pharmacy_id = p.id
               JOIN region r ON p.region_id = r.id
               LEFT JOIN app_user u ON u.telegram_id = b.manager_tg_id
               WHERE b.company_id = $1 AND b.status = 'new'
               ORDER BY b.created_at""",
            company_id,
        )


# ============================================================
#  STATISTIKA
# ============================================================
# Bazada vaqt TIMESTAMPTZ (ya'ni UTC) saqlanadi, lekin "bugun" degani
# foydalanuvchi uchun O'zbekiston kuni. Shuning uchun davr chegarasi
# Python emas, Postgresda hisoblanadi — server qaysi zonada turishidan
# qat'i nazar natija bir xil bo'ladi.

STATS_TZ = "Asia/Tashkent"
PERIOD_UNITS = {"today": "day", "week": "week", "month": "month"}
# Davr chegarasi yo'q degani — 'all'


async def period_start(period: str) -> tuple:
    """(davr boshi, 'DD.MM.YYYY') juftligi. Noma'lum yoki 'all' → (None, None).

    Sana matni ham shu yerda yasaladi: chegara Toshkent vaqtida, natija
    esa UTC bo'lgani uchun Pythonda formatlash noto'g'ri kun ko'rsatardi.
    """
    unit = PERIOD_UNITS.get(period)
    if unit is None:
        return None, None
    # unit faqat PERIOD_UNITS dan keladi — foydalanuvchi matni emas
    start = f"date_trunc('{unit}', now() AT TIME ZONE $1::text)"
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            f"""SELECT {start} AT TIME ZONE $1::text     AS ts,
                       to_char({start}, 'DD.MM.YYYY')    AS label""",
            STATS_TZ,
        )
        return row["ts"], row["label"]


# $1 — company_id, $2 — davr boshi (NULL bo'lsa cheklov yo'q)
_PERIOD_WHERE = "b.company_id = $1 AND ($2::timestamptz IS NULL OR b.created_at >= $2)"


async def stats_totals(company_id: int, since):
    """Umumiy raqamlar: bronlar soni, summa, nechta har xil apteka."""
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(
            f"""SELECT COUNT(*)                        AS brons,
                       COALESCE(SUM(b.total_sum), 0)   AS total,
                       COUNT(DISTINCT b.pharmacy_id)   AS pharmacies
                FROM bron b
                WHERE {_PERIOD_WHERE}""",
            company_id, since,
        )


async def stats_by_status(company_id: int, since):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            f"""SELECT b.status,
                       COUNT(*)                      AS n,
                       COALESCE(SUM(b.total_sum), 0) AS total
                FROM bron b
                WHERE {_PERIOD_WHERE}
                GROUP BY b.status
                ORDER BY n DESC""",
            company_id, since,
        )


async def stats_top_drugs(company_id: int, since, limit: int = 10):
    """Qaysi dori ko'p ketdi.

    Guruhlash drug_name bo'yicha, drug_id bo'yicha emas: bron_item da nom
    snapshot qilingan va dori bazadan o'chirilsa ham hisobotda qoladi.
    """
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            f"""SELECT bi.drug_name,
                       MIN(bi.unit)          AS unit,
                       SUM(bi.quantity)      AS qty,
                       SUM(bi.line_total)    AS total
                FROM bron_item bi
                JOIN bron b ON b.id = bi.bron_id
                WHERE {_PERIOD_WHERE}
                GROUP BY bi.drug_name
                ORDER BY total DESC
                LIMIT $3""",
            company_id, since, limit,
        )


async def stats_by_region(company_id: int, since):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            f"""SELECT r.name,
                       COUNT(*)                      AS n,
                       COALESCE(SUM(b.total_sum), 0) AS total
                FROM bron b
                JOIN pharmacy p ON b.pharmacy_id = p.id
                JOIN region r   ON p.region_id = r.id
                WHERE {_PERIOD_WHERE}
                GROUP BY r.id, r.name
                ORDER BY total DESC""",
            company_id, since,
        )


async def stats_top_pharmacies(company_id: int, since, limit: int = 10):
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            f"""SELECT p.name,
                       r.name                        AS region_name,
                       COUNT(*)                      AS n,
                       COALESCE(SUM(b.total_sum), 0) AS total
                FROM bron b
                JOIN pharmacy p ON b.pharmacy_id = p.id
                JOIN region r   ON p.region_id = r.id
                WHERE {_PERIOD_WHERE}
                GROUP BY p.id, p.name, r.name
                ORDER BY total DESC
                LIMIT $3""",
            company_id, since, limit,
        )


# Excel uchun alohida select: sana Toshkent vaqtiga o'tkazilgan holda
# keladi (created_local). Aks holda faylda UTC ko'rinib, kechqurun
# qilingan bronlar oldingi kunga tushib qolardi.
EXPORT_SELECT = """
    SELECT b.id, b.status, b.total_sum, b.doc_contract_no,
           (b.created_at AT TIME ZONE $3::text) AS created_local,
           p.name       AS pharmacy_name,
           r.name       AS region_name,
           u.full_name  AS manager_name
    FROM bron b
    JOIN pharmacy p ON b.pharmacy_id = p.id
    JOIN region r   ON p.region_id = r.id
    LEFT JOIN app_user u ON u.telegram_id = b.manager_tg_id
"""


async def list_brons_for_export(company_id: int, since, limit: int = 5000):
    """Excel uchun davrdagi bronlar — eskisidan yangisiga."""
    async with get_pool().acquire() as conn:
        return await conn.fetch(
            EXPORT_SELECT + f" WHERE {_PERIOD_WHERE} ORDER BY b.id LIMIT $4",
            company_id, since, STATS_TZ, limit,
        )
