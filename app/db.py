from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


url = get_settings().database_url
# Render provides a generic PostgreSQL URL. Select psycopg 3 explicitly so
# SQLAlchemy does not fall back to the uninstalled psycopg2 driver.
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 15} if url.startswith('sqlite') else {})
if url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_setup(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
