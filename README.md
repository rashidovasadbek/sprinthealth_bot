# sprinthealth_bron_bot

Sprint Health'ning **ikkinchi bank sho'ti (kod `02`)** bo'yicha bron yig'uvchi Telegram bot — [@sprinthelth_bron_bot](https://t.me/sprinthelth_bron_bot).

Menejer aptekani tanlaydi → dorilarni bron qiladi → Excel spesifikatsiya oladi → bron **bron guruhiga** tushadi → to'lov qilingach **oplata guruhiga** o'tadi.

Butun interfeys va kod izohlari **o'zbekcha** — handler yoki xabar qo'shsangiz shu qoidani saqlang.

## Ishga tushirish

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # to'ldiring (pastga qarang)
python -m db.migrate              # baza sxemasini qo'llash
python main.py
```

Testlar yoki linter sozlamasi yo'q.

## `.env`

| Kalit | Izoh |
|---|---|
| `BOT_TOKEN` | @BotFather dan |
| `BRON_GROUP_ID` | Bronlar tushadigan guruh (bot admin bo'lishi shart) |
| `OPLATA_GROUP_ID` | To'lov qilinganlar tushadigan guruh |
| `BOOTSTRAP_ADMIN_ID` | Faqat birinchi ishga tushirish uchun: bazada admin bo'lmasa, shu ID admin qilib yoziladi |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` / `DB_HOST` / `DB_PORT` | PostgreSQL |
| `COMPANY_CODE` | `company.code` — odatda `sprinthealth` |

Adminlar `.env` da emas, **bazada** (`app_user.role`). Admin qo'shish uchun kod ham, qayta ishga tushirish ham kerak emas.

> Guruh supergroup'ga o'tkazilsa **ID o'zgaradi** — `.env` ni yangilash kerak.
> Log'da `TelegramMigrateToChat: group chat was upgraded to a supergroup chat`
> chiqadi. Yangi ID ni topish uchun (hech qanday xabar qoldirmaydi):
>
> ```bash
> curl -s "https://api.telegram.org/bot<TOKEN>/sendChatAction?chat_id=<ESKI_ID>&action=typing"
> # javobdagi parameters.migrate_to_chat_id — yangi ID
> ```

## Arxitektura

| Papka / fayl | Vazifasi |
|---|---|
| `main.py` | Dispatcher, middleware va routerlarni yig'adi |
| `config.py` | Env **bitta joyda** o'qiladi (`Settings`) |
| `db/pool.py` | asyncpg pool — butun bot uchun bitta |
| `db/repo.py` | **Barcha SQL** shu yerda; handlerlarda SQL yo'q |
| `db/migrate.py` + `db/migrations/` | Idempotent migration runner (`schema_migrations`) |
| `handlers/bron.py` | Apteka tanlash → savat → hisoblash → tasdiqlash |
| `handlers/groups.py` | Bron guruhidagi «To'lov guruhiga yuborish» tugmasi |
| `handlers/admin.py` | Xodimlar, dorilar, kompaniya rekvizitlari |
| `handlers/pharmacy_admin.py` | Aptekalar: qo'shish, tahrirlash, ma'lumot, Excel |
| `handlers/stats.py` | 📊 Statistika: davr bo'yicha hisobot + Excel (faqat admin) |
| `middlewares/auth.py` | `app_user` ro'yxatidan o'tmagan odam kira olmaydi |
| `services/pricing.py` | Pul hisobi — **yagona manba** |
| `services/render.py` | Xabar matnlari + 4096 belgi chegarasi (`chunks()`) |
| `services/excel.py` | Excel → `bytes` (diskka yozilmaydi) |
| `web/` | Markirovka sahifasi — oplataga yuborilmagan bronlar (faqat o'qiydi) |

### Rollar

`admin` — hamma narsa · `buxgalter` — to'lovni tasdiqlaydi · `manager` — bron qiladi

To'lov tugmasini faqat `admin` va `buxgalter` bosa oladi.

### Shartnoma raqami

Format `N{A}/{B}/{C}` — masalan `N01/90/02`:
- **A** — `counter` jadvalidan, `UPDATE … RETURNING` bilan (atomar, poyga yo'q).
  Kamida ikki xonagacha nol bilan to'ldiriladi (`1` → `01`), 99 dan oshsa
  tabiiy o'sadi (`100` → `N100`)
- **B** — viloyat kodi (`region.code`)
- **C** — kompaniyaning sho't kodi — bu botda doim **`02`**

Raqamning o'zida `N` bor, shuning uchun xabarlarda «№» takrorlanmaydi —
«Shartnoma N01/90/02» deb chiqadi.

### Pul hisobi

`services/pricing.py` da, `Decimal` + `ROUND_HALF_UP`. Yaxlitlash tartibi o'zgartirilmasligi kerak:

1. qator qiymati = narx × miqdor — yaxlitlanmaydi
2. NDS summasi — 2 xonagacha
3. qator jami = qiymat + NDS — butun so'mgacha
4. umumiy jami = yaxlitlangan qator jamilar yig'indisi

Bron yaratilganda narx, NDS va qator jami `bron_item` ga **snapshot** qilinadi — dori keyin qimmatlashsa ham eski hujjat o'zgarmaydi. Oplata guruhiga yuborishda summalar qayta hisoblanmaydi (`pricing.stored_items`).

## Markirovka sahifasi

Bron guruhidagi **oplataga hali yuborilmagan** (`status='new'`) bronlarni bitta
sahifada ko'rsatadi — markirovka olishda adashmaslik uchun. Bot bilan bitta
jarayonda ishlaydi, bazaga hech narsa yozmaydi.

- `.env` ga `WEB_PORT=8090` va `WEB_TOKEN=...` (kamida 16 belgi) qo'shing.
  `WEB_PORT` bo'sh bo'lsa sahifa o'chiq.
- Birinchi marta: `http://SERVER_IP:8090/markirovka?token=WEB_TOKEN` — token
  brauzerda saqlanadi, keyin shunchaki `/markirovka`.
- Port ochiq bo'lishi kerak: `sudo ufw allow 8090/tcp` (ufw yoqilgan bo'lsa).

Sahifada: bron kartalari (apteka, shartnoma, dorilar, karobka hisobi) va
«Preparatlar bo'yicha» jami ro'yxat. Har qatorga «markirovkasi olindi»
belgisi qo'yiladi — bu belgi **faqat shu brauzerda** saqlanadi. Bron
oplataga yuborilganda sahifadan o'zi yo'qoladi, oldingi yuklashdan keyin
kelganlari «YANGI» deb belgilanadi.

API boshqa sahifadan ham chaqirilishi mumkin (CORS ochiq):

```js
fetch("http://SERVER_IP:8090/api/pending", { headers: { "X-Token": TOKEN } })
  .then(r => r.json())   // { company, generated_at, brons: [{ id, pharmacy_name, inn, doc_contract_no, items: [...] }] }
```

## Deploy

Server: `asadbek@193.180.209.245`, papka `/home/asadbek/farm/sprinthealth_bron_bot/`, baza `sprinthealth_bron`.

```bash
git pull origin main
./venv/bin/pip install -r requirements.txt   # requirements o'zgargan bo'lsa
./venv/bin/python -m db.migrate              # yangi migration bo'lsa
sudo systemctl restart sprinthealthbot.service
journalctl -u sprinthealthbot.service -f
```

Sog'lom start log'i: `Bot ishga tushdi... 🚀`

Shu serverda `farm_bot` (`@spets_sos_bot`) ham ishlaydi — alohida baza, alohida systemd unit. Ularga tegilmaydi.

## Sxemani o'zgartirish

`db/migrations/` ga yangi `00N_*.sql` qo'shing va `python -m db.migrate` yugurtiring. Mavjud fayllar **tahrirlanmaydi** — ular allaqachon qo'llangan.

## Rebrending: MEDIWELL → SPRINT HEALTH

Bajarilgan — bu yerda faqat nima o'zgargani yozib qo'yilgan.

| Nima | Eski | Yangi |
|---|---|---|
| `company.code` | `mediwell` | `sprinthealth` |
| `company.name` | `OOO "MEDIWELL" MCHJ` | `OOO "SPRINT HEALTH" MCHJ` |
| `company.account_no` | `20208000607367249001` | `20208000807367249002` |
| Bot | `@mediwell02_bron_bot` | `@sprinthelth_bron_bot` |
| Baza / rol | `mediwell02_bron` / `mediwell02_user` | `sprinthealth_bron` / `sprinthealth_user` |
| Papka | `mediwell02_bron_bot` | `sprinthealth_bron_bot` |
| systemd | `mediwell02bot.service` | `sprinthealthbot.service` |

Nomlardagi `02` olib tashlandi, lekin **`company.account_code` hamon `02`** —
u shartnoma raqamiga (`A/C`) tushadi va mavjud hujjatlarga bog'langan.

Bank rekvizitlari (`"InFinBANK"`, INN `312636862`, MFO `01070`, direktor)
o'zgarmadi. `address` hamon `NULL` — admin panel orqali to'ldiriladi.

Bot username'ida imlo xatosi bor (`sprinthelth`, «a» yo'q) — `sprinthealth...`
variantlari band edi.
