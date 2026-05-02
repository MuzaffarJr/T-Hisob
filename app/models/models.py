from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime
from app.db.session import Base


class UserSettings(Base):
    __tablename__ = "user_settings"
    telegram_id = Column(BigInteger, primary_key=True)
    language    = Column(String, default="uz")   # "uz" | "ru"


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True)
    name = Column(String)
    inn = Column(String, unique=True)
    tax_type = Column(String)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True)
    amount = Column(Float)
    type = Column(String)
    category = Column(String, nullable=True)  # Maosh, Ijara, Tovar, Soliq, Boshqa (chiqim uchun)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
