from collections import UserDict
from re import compile as re_compile, sub as re_sub
from typing import Any, Dict, Iterator, Match, Optional, Pattern, Tuple, Type, Union

from fastapi import Query
from pydantic import BaseConfig
from pydantic.dataclasses import dataclass
from pydantic.fields import ModelField

from ..schemas import ResponseFieldsConfig, SchemaFields


class Paginator:
    limit: int
    offset: int
    default_limit: int = 100
    max_limit: int = 1000
    default_offset: int = 0
    max_offset: Optional[int] = None
    PARAM_NAME: str = 'paginator'

    _limit_query = Query(
        default=default_limit,
        ge=1,
        le=max_limit,
        description='Maximum number of items to list',
    )
    _offset_query = Query(
        default=default_offset, ge=0, le=max_offset, description='Items list offset'
    )

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__()
        cls._limit_query.default = cls.default_limit
        cls._limit_query.le = cls.max_limit
        cls._offset_query.default = cls.default_offset
        cls._offset_query.le = cls.max_offset

    def __init__(
        self,
        limit: int = _limit_query,
        offset: int = _offset_query,
    ):
        self.limit = limit
        self.offset = offset

    @classmethod
    def setup(cls, dependency_class: Type) -> Type['Paginator']:
        if dependency_class is cls:
            return cls
        return type(cls.__name__, (dependency_class, cls), {})


class ResponseFieldsQuery(str):
    REGEX: Pattern = re_compile(r'[a-zA-Z(),-_]+')
    param = Query(
        default=None,
        description='Additional instance fields included to response',
        regex=REGEX.pattern,
        example='field(subfield1,subfield2),other_field',
    )


class ResponseFields(UserDict):
    data: 'ResponseFieldsConfig'
    allowed: SchemaFields = set()
    defaults: 'ResponseFieldsConfig' = {}
    PARAM_NAME: str = 'fields'

    # <field>(<subfield1>,<subfield2>,...)
    REGEX: Pattern = re_compile(r'(?P<field>\w+)\((?P<subfields>[\w,]+)\)')

    def __init__(self, fields: ResponseFieldsQuery = ResponseFieldsQuery.param):
        super().__init__()
        config = self.parse_query(fields) if fields else {}
        self.data = {
            **self.defaults,
            **{key: value for key, value in config.items() if key in self.allowed},
        }

    @classmethod
    def parse_query(cls, query_param: str) -> 'ResponseFieldsConfig':
        subfields = {}

        def get_subfields(matchobj: Match) -> str:
            subfields[matchobj.group('field')] = set(matchobj.group('subfields').split(','))
            return ''

        query_param = re_sub(cls.REGEX, get_subfields, query_param)
        rest: 'ResponseFieldsConfig' = {
            field: set() for field in query_param.strip(',').split(',') if field
        }
        return {**rest, **subfields}

    @classmethod
    def setup(cls, allowed: SchemaFields, defaults: ResponseFieldsConfig) -> Type['ResponseFields']:
        return type(cls.__name__, (cls,), {'allowed': allowed, 'defaults': defaults})


ResponseFieldsDict = Union[ResponseFields, dict]


class FilterBy:
    fields: Dict[str, ModelField] = {}
    PARAM_NAME: str = 'filter_by'

    class ModelConfig(BaseConfig):
        allow_population_by_field_name = True

    @classmethod
    def setup(cls, dependency_class: Type) -> Type['FilterBy']:
        if dependency_class is cls:
            return cls  # pragma: no cover
        data_cls = dataclass(dependency_class, config=cls.ModelConfig)
        cls.fields = data_cls.__pydantic_model__.__fields__
        return type(cls.__name__, (cls, data_cls), {})

    def items(self) -> Iterator[Tuple[str, Any]]:
        for key in self.fields.keys():
            value = getattr(self, key, None)
            if value is not None:
                yield key, value


FILTERABLE_VIEWSET_FLAG = '_IS_FILTERABLE'
