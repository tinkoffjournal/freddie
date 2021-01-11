from collections import defaultdict
from operator import attrgetter
from typing import Any, AsyncIterator, DefaultDict, Dict, Iterable, NamedTuple, Tuple

from peewee import JOIN, SQL, Check, Expression, Function, Query, fn

from .fields import ManyToManyField
from .models import Model


class Prefetch(NamedTuple):
    field: 'ManyToManyField'
    attr_name: str
    ids_only: bool = False


async def prefetch_related(
    objects: Iterable[Model],
    config: Iterable[Prefetch],
    as_objects: bool = True,
) -> AsyncIterator[Model]:
    ids = set(map(attrgetter('id'), objects))
    prefetched_data: Dict[str, DefaultDict] = {}
    for (field, attr_name, ids_only) in config:
        mapping = defaultdict(list)
        related_model = field.rel_model
        related_model_keys = field.rel_model_keys
        through_model = field.through_model
        query = through_model.select()
        if not ids_only:
            query = through_model.select(through_model, related_model).join(related_model)
        query = query.where(field.model_fk << ids).dicts()
        for relation in await through_model.manager.execute(query):
            obj_id = relation[field.model_fk.name]
            related_id = relation[field.rel_model_fk.name]
            related = related_id
            if not ids_only:
                related = {
                    **{key: relation.get(key) for key in related_model_keys},
                    field.rel_model.pk_field().name: related_id,
                }
                if as_objects:
                    related = related_model(**related)
            mapping[obj_id].append(related)

        prefetched_data[attr_name] = mapping

    for obj in objects:
        for attr_name, mapped in prefetched_data.items():
            setattr(obj, attr_name, mapped[obj.id])
        yield obj


async def get_related(pk: Any, config: Iterable[Prefetch]) -> Dict[str, Tuple[Any, ...]]:
    related = {}
    for (field, attr_name, ids_only) in config:
        model = field.rel_model
        builder = field(pk)
        retrieved_fields = [model.pk_field()] if ids_only else None
        query = builder.get(fields=retrieved_fields)
        items = await model.manager.execute(query)
        if ids_only:
            items = map(attrgetter(model.pk_field().name), items)
        related[attr_name] = tuple(items)
    return related


async def set_related(pk: Any, field: ManyToManyField, ids: Iterable[Any] = None) -> None:
    manager = field.through_model.manager
    builder = field(pk)
    delete_query = builder.clear()
    insert_query = builder.add(*ids) if ids else None
    async with manager.atomic():
        await manager.execute(delete_query)
        if insert_query is not None:
            await manager.execute(insert_query)


__all__ = (
    'Check',
    'Expression',
    'Query',
    'JOIN',
    'Prefetch',
    'SQL',
    'fn',
    'Function',
    'prefetch_related',
    'get_related',
    'set_related',
)
