import asyncio
import os
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.models import Company, Transaction, UserSettings
from app.services.ai_service import get_ai_response, parse_transaction
from app.services.inn_service import analyze_inn

BOT_TOKEN  = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "")
UZB = timezone(timedelta(hours=5))

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ─── Tarjimalar ───────────────────────────────────────────────────────────────
T = {
    "uz": {
        "choose_lang":    "🌐 Tilni tanlang / Выберите язык:",
        "lang_set":       "✅ O'zbek tili tanlandi!",
        "welcome": (
            "Salom! T-Hisob faol. Men sizning shaxsiy AI soliq maslahatchingizman.\n\n"
            "📌 Buyruqlar:\n"
            "/register  — Kompaniyani ro'yxatdan o'tkazish\n"
            "/report    — Oylik P&L hisoboti\n"
            "/check_inn — Hamkor INN xavf tahlili 🛡️\n\n"
            "Shunchaki yozing:\n"
            "  Kirim 5000000 tovar sotuvi\n"
            "  Chiqim 1200000 ijara uchun"
        ),
        "register_prompt":  "Ro'yxatdan o'tish uchun MCHJning 9 xonali INN raqamini yuboring:",
        "inn_invalid":      "Xato! Iltimos, faqat 9 ta raqamdan iborat INN yuboring.",
        "inn_exists":       "Bu INN ({inn}) allaqachon ro'yxatdan o'tgan. ℹ️",
        "inn_saved":        "Rahmat! INN {inn} muvaffaqiyatli saqlandi. ✅\nEndi kirim/chiqimlaringizni yozishingiz mumkin.",
        "check_inn_prompt": "🛡️ Hamkor INN xavf tahlili\n\nHamkoringizning 9 xonali INN raqamini yuboring.\nMisol: /check_inn 302644038",
        "inn_bad_format":   "❌ INN noto'g'ri. 9 ta raqam kiriting (masalan: 302644038).",
        "checking":         "🔍 Tekshirilmoqda...",
        "pdf_hint":         "\n\n📄 PDF hisobotni yuklab olish uchun Dashboardni oching.",
        "analyzing":        "Tahlil qilyapman... 🧠",
        "income_saved":     "📈 Kirim saqlandi!{cat}\nSumma: {amount} so'm\nIzoh: {desc}\n\nHisobotni ko'rish uchun /report yozing.",
        "expense_saved":    "📉 Chiqim saqlandi!{cat}\nSumma: {amount} so'm\nIzoh: {desc}\n\nHisobotni ko'rish uchun /report yozing.",
        "report_title":     "📊 {month} — Foyda va Zarar hisoboti",
        "total_income":     "📈 Umumiy kirim:",
        "total_expense":    "📉 Umumiy chiqim:",
        "net_profit":       "💰 Sof foyda:",
        "tax_line":         "🏛  Taxminiy soliq 4%:",
        "tax_reminder":     "⏰ SOLIQ ESLATMASI — 3 kun qoldi!",
        "deadline":         "📅 Muddat:",
        "cur_income":       "📈 Joriy oy kirim:",
        "tax_due":          "🏛 To'lash kerak (4%):",
        "tax_save_tip":     "✅ O'z vaqtida to'lash — jarima va blokirovkadan saqlaydi!\n💡 /report — batafsil hisobot",
        "dashboard_btn":    "📊 Dashboard",
    },
    "ru": {
        "choose_lang":    "🌐 Tilni tanlang / Выберите язык:",
        "lang_set":       "✅ Выбран русский язык!",
        "welcome": (
            "Привет! T-Hisob активен. Я ваш персональный AI налоговый советник.\n\n"
            "📌 Команды:\n"
            "/register  — Регистрация компании\n"
            "/report    — Ежемесячный P&L отчёт\n"
            "/check_inn — Проверка ИНН контрагента 🛡️\n\n"
            "Просто напишите:\n"
            "  Kirim 5000000 продажа товара\n"
            "  Chiqim 1200000 аренда"
        ),
        "register_prompt":  "Для регистрации введите 9-значный ИНН вашего ООО:",
        "inn_invalid":      "Ошибка! Пожалуйста, введите ИНН из 9 цифр.",
        "inn_exists":       "Этот ИНН ({inn}) уже зарегистрирован. ℹ️",
        "inn_saved":        "Спасибо! ИНН {inn} успешно сохранён. ✅\nТеперь можете вводить доходы/расходы.",
        "check_inn_prompt": "🛡️ Проверка налогового риска ИНН\n\nВведите 9-значный ИНН контрагента.\nПример: /check_inn 302644038",
        "inn_bad_format":   "❌ Неверный ИНН. Введите 9 цифр (например: 302644038).",
        "checking":         "🔍 Проверяем...",
        "pdf_hint":         "\n\n📄 Скачайте PDF отчёт в Dashboard.",
        "analyzing":        "Анализирую... 🧠",
        "income_saved":     "📈 Доход сохранён!{cat}\nСумма: {amount} сум\nКомментарий: {desc}\n\nДля отчёта напишите /report.",
        "expense_saved":    "📉 Расход сохранён!{cat}\nСумма: {amount} сум\nКомментарий: {desc}\n\nДля отчёта напишите /report.",
        "report_title":     "📊 {month} — Отчёт о прибылях и убытках",
        "total_income":     "📈 Общий доход:",
        "total_expense":    "📉 Общий расход:",
        "net_profit":       "💰 Чистая прибыль:",
        "tax_line":         "🏛  Прогноз налога 4%:",
        "tax_reminder":     "⏰ НАПОМИНАНИЕ О НАЛОГЕ — осталось 3 дня!",
        "deadline":         "📅 Срок:",
        "cur_income":       "📈 Доход за месяц:",
        "tax_due":          "🏛 К оплате (4%):",
        "tax_save_tip":     "✅ Своевременная оплата — защита от штрафов!\n💡 /report — подробный отчёт",
        "dashboard_btn":    "📊 Dashboard",
    },
}


def now_uzb() -> datetime:
    return datetime.now(UZB)


def get_lang(telegram_id: int) -> str:
    db = SessionLocal()
    try:
        s = db.query(UserSettings).filter(UserSettings.telegram_id == telegram_id).first()
        return s.language if s else "uz"
    finally:
        db.close()


def set_lang(telegram_id: int, lang: str):
    db = SessionLocal()
    try:
        s = db.query(UserSettings).filter(UserSettings.telegram_id == telegram_id).first()
        if s:
            s.language = lang
        else:
            db.add(UserSettings(telegram_id=telegram_id, language=lang))
        db.commit()
    finally:
        db.close()


def t(telegram_id: int, key: str, **kwargs) -> str:
    lang = get_lang(telegram_id)
    text = T[lang].get(key, T["uz"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def dashboard_keyboard(lang: str = "uz") -> InlineKeyboardMarkup | None:
    if not WEB_APP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=T[lang]["dashboard_btn"],
            web_app=WebAppInfo(url=WEB_APP_URL),
        )
    ]])


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
    ]])


# ─── States ───────────────────────────────────────────────────────────────────
class Registration(StatesGroup):
    waiting_for_inn = State()

class CheckINN(StatesGroup):
    waiting_for_inn = State()


# ─── /start + til tanlash ─────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(T["uz"]["choose_lang"], reply_markup=lang_keyboard())


@dp.callback_query(F.data.in_({"lang_uz", "lang_ru"}))
async def cb_lang(call: types.CallbackQuery):
    lang = call.data.split("_")[1]
    set_lang(call.from_user.id, lang)
    await call.message.edit_text(T[lang]["lang_set"])
    await call.message.answer(
        T[lang]["welcome"],
        reply_markup=dashboard_keyboard(lang),
    )


# ─── /register ────────────────────────────────────────────────────────────────
@dp.message(Command("register"))
async def start_registration(message: types.Message, state: FSMContext):
    await message.answer(t(message.from_user.id, "register_prompt"))
    await state.set_state(Registration.waiting_for_inn)


@dp.message(Registration.waiting_for_inn)
async def process_inn(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    inn = message.text.strip()
    if len(inn) == 9 and inn.isdigit():
        db: Session = SessionLocal()
        try:
            existing = db.query(Company).filter(Company.inn == inn).first()
            if existing:
                await message.answer(t(uid, "inn_exists", inn=inn))
            else:
                db.add(Company(telegram_id=uid, inn=inn, name=f"MCHJ {inn}"))
                db.commit()
                lang = get_lang(uid)
                await message.answer(t(uid, "inn_saved", inn=inn),
                                     reply_markup=dashboard_keyboard(lang))
        finally:
            db.close()
        await state.clear()
    else:
        await message.answer(t(uid, "inn_invalid"))


# ─── /check_inn ───────────────────────────────────────────────────────────────
@dp.message(Command("check_inn"))
async def cmd_check_inn(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) == 2:
        await send_inn_report(message, parts[1])
    else:
        await message.answer(t(message.from_user.id, "check_inn_prompt"))
        await state.set_state(CheckINN.waiting_for_inn)


@dp.message(CheckINN.waiting_for_inn)
async def process_check_inn(message: types.Message, state: FSMContext):
    await send_inn_report(message, message.text.strip())
    await state.clear()


async def send_inn_report(message: types.Message, inn: str):
    uid  = message.from_user.id
    lang = get_lang(uid)
    wait = await message.answer(T[lang]["checking"])
    risk = await analyze_inn(inn)
    await wait.delete()

    if risk is None:
        await message.answer(T[lang]["inn_bad_format"])
        return

    icon  = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[risk.level]
    level = {
        "uz": {"green": "PAST — Xavfsiz", "yellow": "O'RTA — Ehtiyotkor", "red": "YUQORI — Xavfli!"},
        "ru": {"green": "НИЗКИЙ — Безопасно", "yellow": "СРЕДНИЙ — Осторожно", "red": "ВЫСОКИЙ — Опасно!"},
    }[lang][risk.level]
    src = ("Soliq API" if lang == "uz" else "Налоговый API") if risk.source == "api" \
          else ("Taxminiy tahlil" if lang == "uz" else "Расчётная оценка")

    inds = "\n".join(f"  • {i}" for i in risk.indicators)
    recs = "\n".join(f"  {n+1}. {r}" for n, r in enumerate(risk.recommendations))

    lbl_type   = "Turi" if lang == "uz" else "Тип"
    lbl_region = "Hudud" if lang == "uz" else "Регион"
    lbl_level  = "Xavf darajasi" if lang == "uz" else "Уровень риска"
    lbl_score  = "Xavfsizlik balli" if lang == "uz" else "Балл безопасности"
    lbl_ind    = "Ko'rsatkichlar" if lang == "uz" else "Показатели"
    lbl_rec    = "Tavsiyalar" if lang == "uz" else "Рекомендации"
    lbl_warn   = ("⚠️ Katta shartnomalar uchun professional auditor bilan maslahatlashing."
                  if lang == "uz" else
                  "⚠️ Для крупных договоров проконсультируйтесь с профессиональным аудитором.")

    await message.answer(
        f"{icon} {risk.company_name}  |  INN {risk.inn}  |  {src}\n"
        f"{'─' * 34}\n"
        f"🏢 {lbl_type}:       {risk.company_type}\n"
        f"📍 {lbl_region}:     {risk.region}\n"
        f"📊 {lbl_level}: {level}\n"
        f"🎯 {lbl_score}: {risk.score}/100\n"
        f"{'─' * 34}\n"
        f"📋 {lbl_ind}:\n{inds}\n\n"
        f"💡 {lbl_rec}:\n{recs}\n\n"
        f"{lbl_warn}"
    )


# ─── /report ──────────────────────────────────────────────────────────────────
@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    uid  = message.from_user.id
    lang = get_lang(uid)
    now  = now_uzb().replace(tzinfo=None)
    month_start_utc = datetime(now.year, now.month, 1) - timedelta(hours=5)

    db: Session = SessionLocal()
    try:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.telegram_id == uid,
                Transaction.created_at >= month_start_utc,
            )
            .all()
        )
    finally:
        db.close()

    total_kirim  = sum(x.amount for x in txns if x.type == "kirim")
    total_chiqim = sum(x.amount for x in txns if x.type == "chiqim")
    sof_foyda    = total_kirim - total_chiqim
    soliq        = total_kirim * 0.04
    sep          = "─" * 32

    await message.answer(
        f"{T[lang]['report_title'].format(month=now.strftime('%B %Y'))}\n"
        f"{sep}\n"
        f"{T[lang]['total_income']}  {total_kirim:>14,.0f} so'm\n"
        f"{T[lang]['total_expense']} {total_chiqim:>14,.0f} so'm\n"
        f"{sep}\n"
        f"{T[lang]['net_profit']}    {sof_foyda:>14,.0f} so'm\n"
        f"{T[lang]['tax_line']}  {soliq:>14,.0f} so'm"
        f"{T[lang]['pdf_hint'] if WEB_APP_URL else ''}",
        reply_markup=dashboard_keyboard(lang),
    )


# ─── Umumiy xabar handler ─────────────────────────────────────────────────────
@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    if not message.text:
        return

    uid  = message.from_user.id
    lang = get_lang(uid)
    status_msg = await message.answer(T[lang]["analyzing"])
    txn = await parse_transaction(message.text, lang)

    if txn:
        db: Session = SessionLocal()
        try:
            db.add(Transaction(
                telegram_id=uid,
                amount=txn["amount"],
                type=txn["type"],
                category=txn.get("category"),
                description=txn["description"],
            ))
            db.commit()
        finally:
            db.close()

        cat_text = f" ({txn.get('category')})" if txn.get("category") else ""
        key = "income_saved" if txn["type"] == "kirim" else "expense_saved"
        await status_msg.delete()
        await message.answer(
            T[lang][key].format(
                cat=cat_text,
                amount=f"{txn['amount']:,.0f}",
                desc=txn["description"],
            )
        )
    else:
        answer = await get_ai_response(message.text, lang)
        await status_msg.delete()
        await message.answer(answer)


# ─── Soliq Kalendari Scheduler ────────────────────────────────────────────────
def _next_tax_deadlines(from_date: datetime) -> list[dict]:
    deadlines = []
    y, m = from_date.year, from_date.month

    for delta in range(2):
        month = m + delta
        year  = y + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        for day, label_uz, label_ru, emoji in [
            (15, "Avans soliq to'lovi (15-sana)", "Авансовый налог (15-е число)", "💳"),
            (20, "Asosiy QQS to'lovi (20-sana)", "Основной НДС (20-е число)", "🏛"),
        ]:
            d = datetime(year, month, day)
            if d.date() >= from_date.date():
                deadlines.append({"date": d, "uz": label_uz, "ru": label_ru, "emoji": emoji})

    quarterly_dates = [
        datetime(y, 4, 25), datetime(y, 7, 25),
        datetime(y, 10, 25), datetime(y + 1, 1, 25),
    ]
    for d in quarterly_dates:
        if d.date() >= from_date.date():
            deadlines.append({
                "date": d,
                "uz": "Choraklik hisobot (25-sana)",
                "ru": "Квартальный отчёт (25-е число)",
                "emoji": "📋",
            })
            break

    return sorted(deadlines, key=lambda x: x["date"])[:4]


async def tax_calendar_scheduler():
    while True:
        now_uz   = now_uzb()
        next_run = now_uz.replace(hour=9, minute=0, second=0, microsecond=0)
        if next_run <= now_uz:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now_uz).total_seconds())

        today      = now_uzb().replace(hour=0, minute=0, second=0, microsecond=0)
        alert_date = today + timedelta(days=3)
        deadlines  = _next_tax_deadlines(today.replace(tzinfo=None))
        due_today  = [d for d in deadlines if d["date"].date() == alert_date.date()]
        if not due_today:
            continue

        db: Session = SessionLocal()
        try:
            companies = db.query(Company).all()
            for company in companies:
                lang = get_lang(company.telegram_id)
                month_start_utc = today.replace(day=1, tzinfo=None) - timedelta(hours=5)
                txns = db.query(Transaction).filter(
                    Transaction.telegram_id == company.telegram_id,
                    Transaction.created_at >= month_start_utc,
                ).all()
                kirim = sum(x.amount for x in txns if x.type == "kirim")
                taxed = kirim * 0.04

                for dl in due_today:
                    try:
                        await bot.send_message(
                            company.telegram_id,
                            f"{T[lang]['tax_reminder']}\n\n"
                            f"{dl['emoji']} {dl[lang]}\n"
                            f"{T[lang]['deadline']} {dl['date'].strftime('%d.%m.%Y')}\n"
                            f"{'─' * 30}\n"
                            f"{T[lang]['cur_income']}  {kirim:>12,.0f} so'm\n"
                            f"{T[lang]['tax_due']}      {taxed:>12,.0f} so'm\n\n"
                            f"{T[lang]['tax_save_tip']}"
                        )
                    except Exception:
                        pass
        finally:
            db.close()


async def start_bot():
    asyncio.create_task(tax_calendar_scheduler())
    await dp.start_polling(bot)
