from asyncio import get_event_loop

from async_asgi_testclient import TestClient
from pytest import fixture

from freddie.db import Database

from .app import BaseDBModel, app, settings
from .utils import run_sql

MODELS = BaseDBModel.__subclasses__()


# pytest-asyncio creates function-scoped loop by default,
# and so aiopg failes on closed event loop
@fixture(autouse=True, scope='session')
def event_loop():
    loop = get_event_loop()
    yield loop
    loop.close()


@fixture(scope='session')
def client():
    yield TestClient(app)


@fixture(autouse=True, scope='session')
def test_db():
    db_name = f'{settings.postgres_db}_test'
    run_sql(f'DROP DATABASE IF EXISTS {db_name}')
    run_sql(f'CREATE DATABASE {db_name}')
    db = Database(
        db_name,
        user=settings.postgres_user,
        host=settings.postgres_host,
        port=settings.postgres_port,
        password=settings.postgres_password,
    )
    db.set_allow_sync(True)
    db.bind(MODELS, bind_refs=False, bind_backrefs=False)
    db.connect()
    for model in MODELS:
        model.manager.database = db

    yield db

    # Close all connections & drop DB
    db.close()
    run_sql(f'SELECT pg_terminate_backend(pid) from pg_stat_activity where datname=\'{db_name}\'')
    run_sql(f'DROP DATABASE {db_name}')


@fixture(autouse=True)
def transaction(test_db):
    test_db.create_tables(MODELS)
    yield
    test_db.drop_tables(MODELS)
