from inspect import getmembers
from typing import Callable, Iterator, Tuple, Type

from peewee import Field as DBField, Model as DBModel

DEPENDANT_PROPERTY_ATTR_NAME = 'property_deps'


def depends_on(*fields: DBField) -> Callable:
    def wrapper(getter: Callable) -> Callable:
        setattr(getter, DEPENDANT_PROPERTY_ATTR_NAME, fields)
        return getter

    return wrapper


def get_properties_dependencies(
    model_class: Type[DBModel],
) -> Iterator[Tuple[str, Tuple[DBField, ...]]]:
    for name, method in getmembers(
        model_class,
        lambda member: (isinstance(member, (property, Callable))),  # type: ignore
    ):
        # Get getter if property or method itself
        method_fn = getattr(method, 'fget', method)
        fields = tuple(
            # Need to re-get class attribute, otherwise child models will depend on parent fields
            getattr(model_class, field.name)
            for field in getattr(method_fn, DEPENDANT_PROPERTY_ATTR_NAME, [])
            if isinstance(field, DBField)
        )
        if fields:
            yield name, fields
