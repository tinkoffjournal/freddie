from typing import Type

from pydantic import BaseConfig

from freddie import Schema


def create_schema_from_config(config: dict) -> Type[Schema]:
    config_cls = type('Config', (BaseConfig,), config)
    return type('Schema', (Schema,), {'Config': config_cls})
