from sqlalchemy import create_engine,inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator
from app.core.settings import settings
from app.core.base import Base
from app.utils.constants import POOL_SIZE, MAX_OVERFLOW, POOL_RECYCLE


engine = create_engine(
    url= settings.DB_URI,
    pool_pre_ping= True,
    pool_recycle= POOL_RECYCLE,
    pool_size= POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
)

SessionLocal = sessionmaker(bind= engine, autoflush= False)
Base.metadata.create_all(engine)
inspector = inspect(engine)
print(f"Tables in database after creation: {inspector.get_table_names()}")
def get_db() -> Generator:
    """Create the database tables"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()