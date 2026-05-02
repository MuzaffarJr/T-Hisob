import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_SYSTEM = {
    "uz": (
        "Sening isming T-Hisob. Sen O'zbekistondagi MCHJ rahbarlari uchun "
        "professional soliq maslahatchisisan. O'zbekiston Respublikasi Soliq Kodeksi "
        "va qonunchiligiga tayanib, sodda va aniq tilda javob ber. "
        "Faqat o'zbek tilida javob ber."
    ),
    "ru": (
        "Ты T-Hisob — профессиональный налоговый консультант для руководителей ООО в Узбекистане. "
        "Отвечай на основе Налогового кодекса Республики Узбекистан, "
        "ясно и конкретно. Отвечай только на русском языке."
    ),
}

_PARSE_SYSTEM = (
    "Sen moliyaviy matn tahlilchisisan. Foydalanuvchi matni o'zbek yoki rus tilida bo'lishi mumkin. "
    "Matnda kirim yoki chiqim bo'lsa JSON formatda qaytarasan. Aks holda is_transaction: false.\n\n"
    "CHIQIM KATEGORIYALARI (faqat chiqim uchun):\n"
    "- 'Maosh': Xodimlar oyligi, bonuslar / Зарплата, бонусы\n"
    "- 'Ijara': Ijara to'lovi / Аренда\n"
    "- 'Tovar': Tovar-material xaridlari / Закупка товаров\n"
    "- 'Soliq': Soliqlar va to'lovlar / Налоги и сборы\n"
    "- 'Kommunal': Kommunal to'lovlar / Коммунальные услуги\n"
    "- 'Boshqa': Boshqa / Прочее\n\n"
    "Kirim uchun category: null\n"
    'Format: {"is_transaction": bool, "type": "kirim"|"chiqim", '
    '"amount": float, "description": str, "category": str|null}'
)


async def get_ai_response(user_question: str, lang: str = "uz") -> str:
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _SYSTEM.get(lang, _SYSTEM["uz"])},
                {"role": "user",   "content": user_question},
            ],
            max_tokens=600,
        )
        return response.choices[0].message.content
    except Exception as e:
        return (f"Xatolik yuz berdi: {e}" if lang == "uz"
                else f"Произошла ошибка: {e}")


async def parse_transaction(text: str, lang: str = "uz") -> dict | None:
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM},
                {"role": "user",   "content": text},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        if not data.get("is_transaction"):
            return None
        category = data.get("category")
        if data["type"].lower() == "chiqim" and not category:
            category = "Boshqa"
        return {
            "type":        data["type"].lower(),
            "amount":      float(data["amount"]),
            "description": data.get("description", ""),
            "category":    category,
        }
    except Exception:
        return None


async def get_financial_ai_response(question: str, context: dict, lang: str = "uz") -> str:
    """
    Foydalanuvchining moliyaviy ma'lumotlari bilan boyitilgan AI javob.
    context = {income, expense, profit, tax, month, top_expenses}
    """
    ctx_uz = (
        f"Foydalanuvchining {context['month']} oyi moliyaviy holati:\n"
        f"  Kirim: {context['income']:,.0f} so'm\n"
        f"  Chiqim: {context['expense']:,.0f} so'm\n"
        f"  Sof foyda: {context['profit']:,.0f} so'm\n"
        f"  Taxminiy soliq (4%): {context['tax']:,.0f} so'm\n"
        f"  Asosiy xarajatlar: {context.get('top_expenses', 'mavjud emas')}\n"
    )
    ctx_ru = (
        f"Финансовое состояние пользователя за {context['month']}:\n"
        f"  Доход: {context['income']:,.0f} сум\n"
        f"  Расход: {context['expense']:,.0f} сум\n"
        f"  Чистая прибыль: {context['profit']:,.0f} сум\n"
        f"  Прогноз налога (4%): {context['tax']:,.0f} сум\n"
        f"  Основные расходы: {context.get('top_expenses', 'нет данных')}\n"
    )
    ctx_text = ctx_uz if lang == "uz" else ctx_ru

    system = _SYSTEM.get(lang, _SYSTEM["uz"]) + (
        "\n\nFoydalanuvchi haqidagi moliyaviy ma'lumotlar (shaxsiylashtirilgan javob uchun foydalaning):\n"
        if lang == "uz" else
        "\n\nФинансовые данные пользователя (используйте для персонализированного ответа):\n"
    ) + ctx_text

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": question},
            ],
            max_tokens=700,
        )
        return response.choices[0].message.content
    except Exception as e:
        return (f"Xatolik: {e}" if lang == "uz" else f"Ошибка: {e}")
