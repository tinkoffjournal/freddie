import re
from enum import Enum
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Pattern, Set, Type

from fastapi.encoders import jsonable_encoder
from pydantic import BaseConfig, BaseModel, ConstrainedStr, create_model

from .helpers import is_async_iterable, is_awaitable, is_iterable, is_mappable


class SchemaConfig(BaseConfig):
    api_component_name: Optional[str] = None
    api_component_name_plural: Optional[str] = None
    default_readable_fields: 'SchemaFields' = set()
    read_only_fields: 'SchemaFields' = set()
    write_only_fields: 'SchemaFields' = set()


class Schema(BaseModel):
    __config__: Type[SchemaConfig]
    _cache: Dict[str, Any] = {}

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__()
        cls._cache = {}

    class Config(SchemaConfig):
        ...

    @classmethod
    def optional(cls, class_name: str = None) -> 'SchemaClass':
        class_name = class_name or f'{cls.__name__}Optional'
        model = cls._cache.get(class_name)
        if model is None:
            fields = {
                field_name: (field.type_, None) for field_name, field in cls.__fields__.items()
            }
            model = create_model(
                class_name, __base__=cls, __module__=cls.__module__, **fields  # type: ignore
            )
            # Prevent class from recreation on each call,
            # otherwise OpenAPI schema generation is broken
            cls._cache[class_name] = model
        return model

    @classmethod
    def get_config(cls) -> Type[SchemaConfig]:
        return cls.__config__

    @classmethod
    def get_read_only_fields(cls) -> 'SchemaFields':
        return cls.__config__.read_only_fields & set(cls.__fields__.keys())

    @classmethod
    def get_write_only_fields(cls) -> 'SchemaFields':
        return cls.__config__.write_only_fields & set(cls.__fields__.keys())

    @classmethod
    def get_readable_fields(cls) -> 'SchemaFields':
        return set(cls.__fields__.keys()) - cls.get_write_only_fields()

    @classmethod
    def get_writable_fields(cls) -> 'SchemaFields':
        return set(cls.__fields__.keys()) - cls.get_read_only_fields()

    @classmethod
    def get_default_readable_fields(cls) -> 'SchemaFields':
        return (
            cls.__config__.default_readable_fields & set(cls.__fields__.keys())
            or cls.get_readable_fields()
        )

    @classmethod
    def get_field_max_length(cls, field_name: str) -> Optional[int]:
        field = cls.__fields__.get(field_name)
        if not field:
            return None
        field_type = field.type_
        if issubclass(field_type, ConstrainedStr):
            max_length = field_type.max_length
        elif isinstance(field_type, type) and issubclass(field_type, Enum):
            members_lengths = (len(str(i.value)) for i in field_type)
            max_length = max(members_lengths)
        else:
            max_length = field.field_info.max_length
        return int(max_length) if max_length else None

    @classmethod
    def get_default_response_fields_config(cls) -> 'ResponseFieldsConfig':
        config = cls._cache.get('default_response_fields_config')
        if config is None:
            config = {}
            for field_name in cls.get_default_readable_fields():
                nested_model = cls.__fields__[field_name].type_
                if is_subschema(nested_model):
                    subfields = nested_model.get_default_readable_fields()
                else:
                    subfields = set()
                config[field_name] = subfields
            cls._cache['default_response_fields_config'] = config
        return config

    @classmethod
    def get_full_response_fields_config(cls) -> 'ResponseFieldsConfig':
        config = {}
        for field_name in cls.get_readable_fields():
            nested_model = cls.__fields__[field_name].type_
            if is_subschema(nested_model):
                subfields = nested_model.get_readable_fields()
            else:
                subfields = set()
            config[field_name] = subfields
        return config

    @classmethod
    async def serialize(
        cls, obj: Any, fields: Optional[Mapping] = None, jsonable: bool = True, full: bool = False
    ) -> Any:
        if is_async_iterable(obj):
            obj = [obj async for obj in obj]
        is_mapping = is_mappable(obj)
        if not is_mapping and is_iterable(obj):
            return [await cls.serialize(item, fields, jsonable=jsonable, full=full) for item in obj]
        if not fields:
            fields = (
                cls.get_full_response_fields_config()
                if full
                else cls.get_default_response_fields_config()
            )
        serialized = {}
        for field_name, subfields in fields.items():
            if field_name not in cls.get_readable_fields():
                continue
            field = cls.__fields__[field_name]
            field_value = await cls._getattr(
                obj, field_name, default=field.default, is_mapping=is_mapping
            )
            if is_subschema(field.type_):
                subschema: Type[Schema] = field.type_
                subfields_config = (
                    subschema.get_full_response_fields_config()
                    if full
                    else subschema.get_default_response_fields_config()
                )
                subattrs = {
                    **subfields_config,
                    **{
                        subattr: set()
                        for subattr in (subfields or [])
                        if subattr in subschema.get_readable_fields()
                    },
                }
                field_value = await subschema.serialize(
                    field_value, fields=subattrs, jsonable=False
                )
            serialized[field_name] = field_value
        return jsonable_encoder(serialized) if jsonable else serialized

    async def get_serialized(self, fields: Optional[Mapping] = None, jsonable: bool = True) -> Any:
        return await self.serialize(self, fields=fields, jsonable=jsonable)

    @classmethod
    async def _getattr(
        cls,
        obj: Any,
        name: str,
        default: Any = None,
        is_mapping: bool = False,
    ) -> Any:
        if is_mapping:
            value = obj.get(name, None)
        else:
            value = getattr(obj, name, None)
        if callable(value):
            value = value()
        if is_awaitable(value):
            value = await value
        if is_async_iterable(value):
            value = [val async for val in value]
        return value or default


class ApiComponentName(str):
    REGEX: Pattern = re.compile(r'[a-z_]+', flags=re.IGNORECASE)

    @classmethod
    def __get_validators__(cls) -> Iterator[Callable]:
        yield cls.validate  # pragma: no cover

    @classmethod
    def validate(cls, value: Any) -> 'ApiComponentName':
        if not isinstance(value, str):
            raise TypeError('API component name must be a string')
        elif not value:
            raise ValueError('API component name must not be empty')
        elif not cls.REGEX.fullmatch(value):
            raise ValueError(
                f'API component name "{value}" is invalid' f'(allowed pattern: {cls.REGEX.pattern})'
            )
        return cls(value.lower())


def validate_schema(schema: Any) -> None:
    assert isinstance(schema, type), f'{schema} is not a class'
    assert issubclass(schema, Schema), f'{schema} is not subclassed from {Schema.__name__}'


def is_subschema(type_: Any) -> bool:
    return isinstance(type_, type) and issubclass(type_, Schema)


SchemaClass = Type[Schema]
SchemaFields = Set[str]
ResponseFieldsConfig = Dict[str, Set[str]]
