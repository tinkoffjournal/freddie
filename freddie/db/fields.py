from typing import Any, Iterable, Type, Union

from peewee import (
    Expression,
    Field as DBField,
    FieldAccessor,
    ForeignKeyField,
    MetaField,
    Model,
    Query,
)


class ManyToManyAccessor(FieldAccessor):
    field: 'ManyToManyField'

    def __get__(
        self, instance: Model, instance_type: Type[Model] = None
    ) -> Union[list, 'ManyToManyField']:
        if instance is not None:
            return instance.__data__.get(self.name, [])  # type: ignore
        return self.field


class ManyToManyField(MetaField):
    accessor_class = ManyToManyAccessor
    model: 'ModelType'
    rel_model: 'ModelType'
    through_model_name: str
    through_model: 'ModelType'

    def __init__(self, rel_model: 'ModelType', through_model_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.rel_model = rel_model
        self.through_model_name = through_model_name

    def __call__(self, pk: Any) -> 'QueryBuilder':
        return QueryBuilder(pk, self)

    @property
    def model_name(self) -> str:
        return self.model.__name__.lower()

    @property
    def rel_model_name(self) -> str:
        return self.rel_model.__name__.lower()

    @property
    def rel_model_keys(self) -> Iterable[str]:
        return tuple(self.rel_model._meta.fields.keys())

    @property
    def rel_model_pk(self) -> DBField:
        return self.rel_model._meta.primary_key

    @property
    def model_fk(self) -> ForeignKeyField:
        return getattr(self.through_model, self.model_name)

    @property
    def rel_model_fk(self) -> ForeignKeyField:
        return getattr(self.through_model, self.rel_model_name)


class QueryBuilder:
    pk: Any
    field: ManyToManyField
    name: str

    __slots__ = ('pk', 'field', 'name')

    def __init__(self, pk: Any, field: ManyToManyField):
        super().__init__()
        self.pk = pk
        self.field = field

    def get(
        self,
        fields: Iterable[DBField] = None,
        conditions: Iterable[Expression] = None,
    ) -> Query:
        related_objects_pks = self.field.through_model.select(self.field.rel_model_fk).where(
            self.field.model_fk == self.pk
        )
        rel_model_fields = fields if fields else (self.field.rel_model,)
        query = self.field.rel_model.select(*rel_model_fields).where(
            self.field.rel_model_pk << related_objects_pks, *(conditions or ())
        )
        return query

    def add(self, *related_model_ids: Any) -> Query:
        if not related_model_ids:
            raise ValueError('No objects IDs passed for many-to-many relation')
        data = [
            {self.field.rel_model_name: related_id, self.field.model_name: self.pk}
            for related_id in related_model_ids
        ]
        return self.field.through_model.insert_many(data)

    def clear(self) -> Query:
        return self.field.through_model.delete().where(self.field.model_fk == self.pk)


ModelType = Type[Model]
