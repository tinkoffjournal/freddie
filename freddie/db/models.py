from inspect import getmembers
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Tuple,
    Union,
)
from warnings import warn

from peewee import (
    JOIN,
    AutoField,
    BigAutoField,
    BigBitField,
    BigIntegerField,
    BinaryUUIDField,
    BitField,
    BlobField,
    BooleanField,
    CharField,
    DateField,
    DateTimeField,
    DecimalField,
    DoubleField,
    Expression,
    Field as DBField,
    FixedCharField,
    FloatField,
    ForeignKeyField,
    IdentityField,
    IntegerField,
    IPField,
    Model as DBModel,
    Query,
    SmallIntegerField,
    TextField,
    TimeField,
    TimestampField,
    UUIDField,
)
from playhouse.postgres_ext import (
    ArrayField,
    BinaryJSONField as JSONField,
    DateTimeTZField,
    HStoreField,
    TSVectorField,
)

from ..db import Database, DatabaseManager as _DatabaseManager, UnpooledDatabase
from .depends_decorator import depends_on, get_properties_dependencies
from .fields import ManyToManyField

if TYPE_CHECKING:
    from typing_extensions import Protocol

    class DatabaseManager(Protocol):
        atomic: Callable[..., AsyncContextManager]
        get: Callable[..., Awaitable['Model']]
        execute: Callable[..., Awaitable[Any]]


else:
    DatabaseManager = _DatabaseManager


class Model(DBModel):
    manager: DatabaseManager
    manytomany: Dict[str, ManyToManyField] = {}

    @property
    def pk(self) -> Any:
        return getattr(self, self._meta.primary_key.name)

    @classmethod
    def db(cls) -> Union[Database, UnpooledDatabase, None]:
        return cls._meta.database

    @classmethod
    def pk_field(cls) -> DBField:
        return cls._meta.primary_key

    @classmethod
    def fields(cls) -> 'FieldsMap':
        return cls._meta.fields  # type: ignore

    @classmethod
    def map_props_dependencies(cls) -> 'PropsDependenciesMap':
        return {prop: deps for prop, deps in get_properties_dependencies(cls)}

    @classmethod
    def select_only(
        cls, *fields: Union[str, DBField, DBModel], join_type: str = JOIN.LEFT_OUTER
    ) -> Query:
        selected_fields = {cls._meta.primary_key}
        joined_models = set()
        for field in fields:
            field = cls._meta.fields.get(field) if isinstance(field, str) else field
            if field is not None:
                selected_fields.add(field)
            if isinstance(field, type) and issubclass(field, DBModel):
                joined_models.add(field)
        query = cls.select(*selected_fields)
        for model in joined_models:
            query = query.join_from(cls, model, join_type)
        return query


class ThroughModel(DBModel):
    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__()
        cls.setup_related_m2m_fields()

    @classmethod
    def setup_related_m2m_fields(cls) -> None:
        related_fields_found = 0
        foreign_keys: Iterable[ForeignKeyField] = (
            fk for _, fk in getmembers(cls, lambda f: isinstance(f, ForeignKeyField))
        )
        for fk in foreign_keys:
            rel_model: Model = fk.rel_model
            for field_name, field in getmembers(
                rel_model, lambda f: isinstance(f, ManyToManyField)
            ):
                field.through_model = cls
                rel_model.manytomany[field_name] = field
                related_fields_found += 1
        if not related_fields_found:
            warn(f'No many-to-many model fields assigned with {cls.__name__}')  # pragma: no cover


FieldsMap = Dict[str, DBField]
PropsDependenciesMap = Dict[str, Tuple[DBField, ...]]


__all__ = (
    'ArrayField',
    'AutoField',
    'BigAutoField',
    'BigBitField',
    'BigIntegerField',
    'BinaryUUIDField',
    'BitField',
    'BlobField',
    'BooleanField',
    'CharField',
    'CharField',
    'DateField',
    'DateTimeField',
    'DateTimeTZField',
    'DecimalField',
    'Expression',
    'depends_on',
    'DoubleField',
    'DBField',
    'FixedCharField',
    'FloatField',
    'ForeignKeyField',
    'HStoreField',
    'IdentityField',
    'IntegerField',
    'IPField',
    'JSONField',
    'Model',
    'ThroughModel',
    'ManyToManyField',
    'SmallIntegerField',
    'TextField',
    'TimeField',
    'TimestampField',
    'TSVectorField',
    'UUIDField',
)
