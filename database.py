from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./jobjockey.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}   # SQLite-specific
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()