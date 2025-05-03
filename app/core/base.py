"""
Base model for SQLAlchemy ORM.
This module defines the base class for all ORM models using SQLAlchemy's declarative base.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
