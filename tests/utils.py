from typing import Type

from factory import Factory
from peewee import fn
from psycopg2 import connect as pg_connect
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pydantic import BaseConfig
from pytest import fixture

from freddie import Schema


def create_schema_from_config(config: dict) -> Type[Schema]:
    config_cls = type('Config', (BaseConfig,), config)
    return type('Schema', (Schema,), {'Config': config_cls})


class WithClient:
    @fixture(autouse=True)
    def _setup_app_client(self, client):
        self.client = client


class BaseFactory(Factory):
    @classmethod
    def _setup_next_sequence(cls, *args, **kwargs):
        model = cls._meta.model
        pk = getattr(model, model._meta.primary_key.name)
        max_pk = model.select(fn.Max(pk)).scalar() or 1
        return max_pk + 1

    @classmethod
    def _create(cls, target_class, *args, **kwargs):
        model = target_class.create(**kwargs)
        return model


def run_sql(query, database='postgres'):
    conn = pg_connect(database=database)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute(query)
    conn.close()
