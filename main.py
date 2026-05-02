import asyncio
import calendar
from datetime import datetime, timezone, timedelta
from typing import Optional

UZB = timezone(timedelta(hours=5))

def now_uzb() -> datetime:
    return datetime.now(UZB)

def month_start_utc(dt: datetime) -> datetime:
    """O'zbekiston vaqti bo'yicha oy boshini UTC ga aylantiradi."""
    ms_uzb = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (ms_uzb - timedelta(hours=5)).replace(tzinfo=None)

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func

from app.bot.main import start_bot, _next_tax_deadlines
from app.db.session import engine, Base, SessionLocal
from app.models.models import Transaction, UserSettings
from app.services.pdf_service import generate_monthly_report_pdf
from app.services.inn_service import analyze_inn
from app.services.ai_service import get_financial_ai_response

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_dt(value) -> datetime | None:
    """SQLite ba'zan datetime ni string sifatida qaytaradi — ikkalasini qabul qilamiz."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


@app.on_event("startup")
async def startup():
    asyncio.create_task(start_bot())


@app.get("/")
async def root():
    return FileResponse("index.html")


@app.get("/api/status")
async def get_status():
    return {"message": "T-Hisob faol"}


@app.get("/reports/pnl")
async def get_pnl(telegram_id: Optional[int] = Query(default=None)):
    try:
        now = now_uzb().replace(tzinfo=None)
        ms_utc = month_start_utc(now_uzb())
        days_in_month = calendar.monthrange(now.year, now.month)[1]

        daily_kirim = [0.0] * days_in_month
        daily_chiqim = [0.0] * days_in_month

        db = SessionLocal()
        try:
            q = db.query(Transaction)
            if telegram_id:
                q = q.filter(Transaction.telegram_id == telegram_id)
            txns = q.all()

            for t in txns:
                dt = parse_dt(t.created_at)
                if dt is None:
                    continue
                # UTC da saqlangan → UTC+5 ga aylantirish
                dt_uzb = dt + timedelta(hours=5)
                if dt_uzb < datetime(now.year, now.month, 1):
                    continue
                day_idx = min(dt_uzb.day - 1, days_in_month - 1)
                amount = float(t.amount or 0)
                if t.type == "kirim":
                    daily_kirim[day_idx] += amount
                else:
                    daily_chiqim[day_idx] += amount
        finally:
            db.close()

        labels = [f"{d + 1}-{now.strftime('%b')}" for d in range(days_in_month)]
        total_kirim = sum(daily_kirim)
        total_chiqim = sum(daily_chiqim)

        return {
            "month": now.strftime("%B %Y"),
            "total_kirim": total_kirim,
            "total_chiqim": total_chiqim,
            "sof_foyda": total_kirim - total_chiqim,
            "soliq": total_kirim * 0.04,
            "chart": {
                "labels": labels,
                "kirim": daily_kirim,
                "chiqim": daily_chiqim,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/reports/categories")
async def get_expense_categories(telegram_id: Optional[int] = Query(default=None)):
    """Xarajatlarni kategoriyalar bo'yicha hisobni beradi"""
    try:
        now = now_uzb().replace(tzinfo=None)
        ms_utc = month_start_utc(now_uzb())

        db = SessionLocal()
        try:
            q = db.query(Transaction).filter(
                Transaction.type == "chiqim",
                Transaction.created_at >= ms_utc,
            )
            if telegram_id:
                q = q.filter(Transaction.telegram_id == telegram_id)
            
            txns = q.all()
        finally:
            db.close()

        # Kategoriyalar bo'yicha jami hisobla
        categories = {}
        for t in txns:
            cat = t.category or "Boshqa"
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += float(t.amount or 0)

        total = sum(categories.values())
        
        # Foizlar bilan birga qaytarish
        result = []
        for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            result.append({
                "name": cat,
                "amount": amount,
                "percentage": round((amount / total * 100) if total > 0 else 0, 1),
            })

        return {
            "month": now.strftime("%B %Y"),
            "total": total,
            "categories": result,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


async def _generate_ai_summary(income: float, expense: float,
                               profit: float, month_str: str) -> str:
    """AI yordamida qisqa tahliliy xulosa yaratadi."""
    try:
        from openai import AsyncOpenAI
        import os
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            f"{month_str} oyi moliyaviy natijalar:\n"
            f"Kirim: {income:,.0f} so'm\n"
            f"Chiqim: {expense:,.0f} so'm\n"
            f"Sof foyda: {profit:,.0f} so'm\n"
            f"Soliq (4%): {income * 0.04:,.0f} so'm\n\n"
            "Ushbu moliyaviy natijalarni O'zbekiston MCHJ rahbari uchun "
            "2-3 qisqa jumlada professional tilda tahlil qiling. "
            "Xatarlar va tavsiyalarni ham kiriting."
        )
        r = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return r.choices[0].message.content
    except Exception:
        return ""


@app.get("/reports/download-pdf")
async def download_report(telegram_id: int, year: int = None, month: int = None):
    """PDF hisobotini AI xulosa bilan yuklab olish"""
    try:
        if year is None or month is None:
            now = now_uzb().replace(tzinfo=None)
            year = now.year
            month = now.month

        report_date = datetime(year, month, 1)
        db = SessionLocal()
        try:
            # Asosiy summalar
            from sqlalchemy import func as sqlfunc
            from app.models.models import Transaction as Txn
            month_end = datetime(year + (month // 12), (month % 12) + 1, 1)
            base_q = db.query(Txn).filter(
                Txn.telegram_id == telegram_id,
                Txn.created_at >= report_date,
                Txn.created_at < month_end,
            )
            income  = sum(t.amount for t in base_q.all() if t.type == "kirim")
            expense = sum(t.amount for t in base_q.all() if t.type == "chiqim")

            # AI xulosa (parallel, 6 sek timeout)
            try:
                ai_summary = await asyncio.wait_for(
                    _generate_ai_summary(income, expense, income - expense,
                                         report_date.strftime("%B %Y")),
                    timeout=10
                )
            except asyncio.TimeoutError:
                ai_summary = ""

            pdf = generate_monthly_report_pdf(telegram_id, db, report_date, ai_summary)
        finally:
            db.close()

        month_name = report_date.strftime("%B_%Y")
        filename = f"T-Hisob_Hisoboti_{month_name}.pdf"

        return StreamingResponse(
            iter([pdf.getvalue()]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/dashboard-stats")
async def get_dashboard_stats(telegram_id: Optional[int] = Query(default=None)):
    try:
        now    = now_uzb().replace(tzinfo=None)
        ms_utc = month_start_utc(now_uzb())

        db = SessionLocal()
        try:
            income = (
                db.query(func.sum(Transaction.amount))
                .filter(Transaction.type == "kirim", Transaction.created_at >= ms_utc)
            )
            expense = (
                db.query(func.sum(Transaction.amount))
                .filter(Transaction.type == "chiqim", Transaction.created_at >= ms_utc)
            )
            if telegram_id:
                income = income.filter(Transaction.telegram_id == telegram_id)
                expense = expense.filter(Transaction.telegram_id == telegram_id)

            total_income = income.scalar() or 0
            total_expense = expense.scalar() or 0

            exp_q = (
                db.query(Transaction.category, func.sum(Transaction.amount))
                .filter(Transaction.type == "chiqim", Transaction.created_at >= ms_utc)
            )
            inc_q = (
                db.query(Transaction.description, func.sum(Transaction.amount))
                .filter(Transaction.type == "kirim", Transaction.created_at >= ms_utc)
            )
            if telegram_id:
                exp_q = exp_q.filter(Transaction.telegram_id == telegram_id)
                inc_q = inc_q.filter(Transaction.telegram_id == telegram_id)

            exp_rows = exp_q.group_by(Transaction.category).all()
            inc_rows = inc_q.group_by(Transaction.description).all()
        finally:
            db.close()

        return {
            "month": now.strftime("%B %Y"),
            "net_profit": total_income - total_expense,
            "total_income": total_income,
            "total_expense": total_expense,
            "tax_forecast": total_income * 0.04,
            "expense_chart": {
                "labels": [row[0] or "Boshqa" for row in exp_rows],
                "values": [float(row[1]) for row in exp_rows],
            },
            "income_chart": {
                "labels": [row[0] or "Kirim" for row in inc_rows],
                "values": [float(row[1]) for row in inc_rows],
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


CATEGORIES = {
    "kirim":  ["Tovar sotuvi", "Xizmat ko'rsatish", "Eksport", "Investitsiya", "Boshqa"],
    "chiqim": ["Ijara", "Maosh", "Tovar", "Soliq", "Kommunal", "Logistika", "Boshqa"],
}


@app.get("/api/categories")
async def get_categories():
    return CATEGORIES


class TxnIn(BaseModel):
    telegram_id: int
    type: str        # "kirim" | "chiqim"
    category: str
    amount: float


@app.post("/api/transactions")
async def add_transaction(body: TxnIn):
    try:
        if body.type not in ("kirim", "chiqim"):
            return JSONResponse(status_code=400, content={"detail": "type kirim yoki chiqim bo'lishi kerak"})
        if body.amount <= 0:
            return JSONResponse(status_code=400, content={"detail": "Summa 0 dan katta bo'lishi kerak"})
        db = SessionLocal()
        try:
            db.add(Transaction(
                telegram_id=body.telegram_id,
                type=body.type,
                category=body.category if body.type == "chiqim" else None,
                description=body.category,
                amount=body.amount,
            ))
            db.commit()
        finally:
            db.close()
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/check_inn")
async def api_check_inn(inn: str = Query(...)):
    risk = await analyze_inn(inn)
    if risk is None:
        return JSONResponse(status_code=400, content={"detail": "INN noto'g'ri"})
    return {
        "inn":          risk.inn,
        "level":        risk.level,
        "score":        risk.score,
        "company_name": risk.company_name,
        "company_type": risk.company_type,
        "region":       risk.region,
        "source":       risk.source,
        "indicators":   risk.indicators,
        "recommendations": risk.recommendations,
    }


@app.get("/api/tax-calendar")
async def get_tax_calendar(telegram_id: Optional[int] = Query(default=None)):
    """Keyingi soliq muddat va taxminiy summa."""
    from app.bot.main import _next_tax_deadlines
    try:
        now = now_uzb().replace(tzinfo=None)
        deadlines = _next_tax_deadlines(now)[:3]

        monthly_kirim = 0.0
        if telegram_id:
            db = SessionLocal()
            try:
                ms_utc = month_start_utc(now_uzb())
                txns = db.query(Transaction).filter(
                    Transaction.telegram_id == telegram_id,
                    Transaction.created_at >= ms_utc,
                ).all()
                monthly_kirim = sum(t.amount for t in txns if t.type == "kirim")
            finally:
                db.close()

        result = []
        for dl in deadlines:
            days_left = (dl["date"].date() - now.date()).days
            result.append({
                "type":       dl["type"],
                "emoji":      dl["emoji"],
                "date":       dl["date"].strftime("%d.%m.%Y"),
                "days_left":  days_left,
                "estimated":  round(monthly_kirim * 0.04, 0),
            })
        return {"deadlines": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


class ChatIn(BaseModel):
    telegram_id: int
    message:     str
    lang:        str = "uz"   # "uz" | "ru"


@app.post("/api/ai-chat")
async def ai_chat(body: ChatIn):
    try:
        lang = body.lang if body.lang in ("uz", "ru") else "uz"

        # Foydalanuvchi tilini DB ga saqlash
        db = SessionLocal()
        try:
            s = db.query(UserSettings).filter(
                UserSettings.telegram_id == body.telegram_id).first()
            if s:
                s.language = lang
            else:
                db.add(UserSettings(telegram_id=body.telegram_id, language=lang))
            db.commit()

            # Moliyaviy kontekst
            ms_utc = month_start_utc(now_uzb())
            txns = db.query(Transaction).filter(
                Transaction.telegram_id == body.telegram_id,
                Transaction.created_at >= ms_utc,
            ).all()
        finally:
            db.close()

        income  = sum(t.amount for t in txns if t.type == "kirim")
        expense = sum(t.amount for t in txns if t.type == "chiqim")

        # Top 3 xarajat kategoriyasi
        cats: dict[str, float] = {}
        for t in txns:
            if t.type == "chiqim":
                k = t.category or "Boshqa"
                cats[k] = cats.get(k, 0) + t.amount
        top_exp = ", ".join(
            f"{k}: {v:,.0f}" for k, v in
            sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        ) or ("mavjud emas" if lang == "uz" else "нет данных")

        context = {
            "month":        now_uzb().strftime("%B %Y"),
            "income":       income,
            "expense":      expense,
            "profit":       income - expense,
            "tax":          income * 0.04,
            "top_expenses": top_exp,
        }

        answer = await get_financial_ai_response(body.message, context, lang)
        return {"answer": answer}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
