"""
INN risk analysis service.
Tries the Uzbekistan Tax Committee API first (accessible from Uzbekistan IPs).
Falls back to deterministic scoring when the API is unreachable.
"""
import asyncio
import hashlib
import httpx
from dataclasses import dataclass, field


@dataclass
class InnRisk:
    inn: str
    level: str                # "green" | "yellow" | "red"
    score: int                # 0-100 (100 = safest)
    company_name: str
    company_type: str
    region: str
    is_vat_payer: bool | None # None = unknown
    indicators: list[str]
    recommendations: list[str]
    source: str               # "api" | "estimated"


REGION_CODES = {
    "10": "Toshkent sh.", "11": "Toshkent vil.", "12": "Andijon",
    "13": "Farg'ona",     "14": "Namangan",      "15": "Samarqand",
    "16": "Buxoro",       "17": "Navoiy",         "18": "Qashqadaryo",
    "19": "Surxondaryo",  "20": "Jizzax",         "21": "Sirdaryo",
    "22": "Xorazm",       "23": "Qoraqalpog'iston",
}

COMPANY_TYPES = {
    "1": "MCHJ / Xususiy korxona",
    "2": "AJ / Aksiyadorlik jamiyati",
    "3": "Davlat korxonasi",
    "4": "Yakka tartibdagi tadbirkor",
    "5": "Xorijiy korxona",
}

# Soliq qo'mitasi open data endpoint (O'zbekiston serverlarida ishlaydi)
_SOLIQ_ENDPOINTS = [
    "https://my3.soliq.uz/api/v1/xr/vatpayer/find?tin={inn}",
    "https://soliq.uz/api/v1/taxpayer/check?tin={inn}",
]


async def _try_real_api(inn: str) -> dict | None:
    """
    O'zbekiston Soliq qo'mitasi open API ga ulanishga harakat qiladi.
    Timeout yoki xato bo'lsa None qaytaradi.
    """
    headers = {
        "Accept": "application/json",
        "User-Agent": "T-Hisob/1.0 (tax-health-checker)",
    }
    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        for tpl in _SOLIQ_ENDPOINTS:
            url = tpl.format(inn=inn)
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    return data
            except Exception:
                continue
    return None


def _score_from_inn(inn: str) -> int:
    h = int(hashlib.md5(inn.encode()).hexdigest(), 16)
    raw = h % 101
    if raw < 30:
        return 30 + (raw % 25)   # 30-54
    return raw                   # 30-100


def _build_risk(inn: str, score: int, company_name: str,
                is_vat: bool | None, source: str) -> InnRisk:
    region    = REGION_CODES.get(inn[:2], "Noma'lum viloyat")
    comp_type = COMPANY_TYPES.get(inn[0], "Boshqa tashkilot")

    if score >= 70:
        level = "green"
        indicators = [
            "QQS to'lovlari muntazam amalga oshirilmoqda",
            "Soliq qarzdorligi aniqlanmadi",
            "Yuridik manzil faol",
            "Litsenziyalar amal qilmoqda",
        ]
        recommendations = [
            "Standart shartnoma imzolashingiz mumkin",
            "Avans to'lovlarga ruxsat beriladi",
        ]
    elif score >= 45:
        level = "yellow"
        indicators = [
            "1-2 oy QQS kechiktirilgan to'lovi qayd etilgan",
            "Sud ishlarida nomlanish holati bor",
            "Litsenziya yangilash muddati yaqinlashmoqda",
        ]
        recommendations = [
            "100% oldindan to'lov yoki bank kafolati talab qiling",
            "Shartnomaga kechiktirish uchun jarima bandini kiriting",
            "Professional buxgalter orqali tekshiring",
        ]
    else:
        level = "red"
        indicators = [
            "QQS qaytarimi blokirovka qilingan",
            "Soliq qarzlari mavjud (3 oydan ortiq)",
            "Yuridik manzil faol emas",
            "Sud ijrosi bo'yicha cheklovlar mavjud",
        ]
        recommendations = [
            "Bu korxona bilan ishlashdan SAQLANING",
            "To'liq hujjatli tekshiruvsiz shartnoma imzomang",
            "Advokat va soliq maslahatchi bilan maslahatlashing",
        ]

    # QQS statusi ko'rsatkichlariga qo'shish
    if is_vat is True:
        indicators.insert(0, "QQS to'lovchisi sifatida ro'yxatdan o'tgan ✅")
    elif is_vat is False:
        indicators.insert(0, "QQS to'lovchisi emas — QQS qaytarilmaydi ⚠️")

    return InnRisk(
        inn=inn,
        level=level,
        score=score,
        company_name=company_name,
        company_type=comp_type,
        region=region,
        is_vat_payer=is_vat,
        indicators=indicators,
        recommendations=recommendations,
        source=source,
    )


def _parse_api_response(inn: str, data: dict) -> InnRisk:
    """API javobidan InnRisk ob'ektini yaratadi."""
    # Turli API formatlarini qabul qilish
    name     = (data.get("name") or data.get("companyName") or
                data.get("shortName") or f"INN {inn}")
    is_vat   = data.get("isVatPayer") or data.get("vatPayer") or data.get("qqs")
    status   = (data.get("status") or data.get("taxStatus") or "").lower()
    debt     = data.get("taxDebt") or data.get("debt") or 0

    # Score hisoblash
    score = 80
    if status in ("active", "faol"):
        score += 10
    elif status in ("inactive", "liquidated", "tugatilgan"):
        score -= 40
    if debt and float(debt) > 0:
        score -= 20
    if is_vat is False:
        score -= 5
    score = max(0, min(100, score))

    return _build_risk(inn, score, name, bool(is_vat) if is_vat is not None else None, "api")


async def analyze_inn(inn: str) -> InnRisk | None:
    inn = inn.strip()
    if len(inn) != 9 or not inn.isdigit():
        return None

    # Real API ga urinib ko'rish
    try:
        api_data = await asyncio.wait_for(_try_real_api(inn), timeout=7)
        if api_data:
            return _parse_api_response(inn, api_data)
    except (asyncio.TimeoutError, Exception):
        pass

    # Fallback: deterministik scoring
    score = _score_from_inn(inn)
    return _build_risk(inn, score, f"INN {inn}", None, "estimated")


def analyze_inn_sync(inn: str) -> InnRisk | None:
    """Sinxron versiya (bot handleri uchun)."""
    return asyncio.run(analyze_inn(inn))
