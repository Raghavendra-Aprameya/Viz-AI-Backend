from sqlalchemy import create_engine,inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator
from app.core.settings import settings
from app.core.base import Base


engine = create_engine(
    url= settings.DB_URI,
    pool_pre_ping= True,
    pool_recycle= 300,
    pool_size= 5,
    max_overflow=0
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