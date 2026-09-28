"""
Declarative base for all ORM models.

Every model class inherits from Base. SQLAlchemy uses this to discover
tables when generating migrations.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this."""
    pass