from inspect import Parameter, Signature, signature as get_signature
from itertools import chain
from operator import attrgetter
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    Tuple,
    Type,
)

from fastapi import Depends
from pydantic import BaseModel


def is_mappable(obj: Any) -> bool:
    return isinstance(obj, Mapping)


def is_iterable(obj: Any) -> bool:
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, BaseModel))


def is_async_iterable(obj: Any) -> bool:
    return isinstance(obj, AsyncIterable)


def is_awaitable(obj: Any) -> bool:
    return isinstance(obj, Awaitable)


def distinct(sequence: Iterable, key_getter: Callable) -> Iterator:
    seen = set()
    for item in sequence:
        key = key_getter(item)
        if key not in seen:
            seen.add(key)
            yield item


def extract_types(type_: Type) -> Tuple[Type, ...]:
    # Generic types like Union or List have undocumented __origin__ attribute
    origin = getattr(type_, '__origin__', None)
    return tuple(type_.__args__) if origin else (type_,)


def is_valid_type(type_: Type, whitelist: Iterable[Type]) -> bool:
    is_valid = lambda valid: issubclass(type_, valid)
    return any(map(is_valid, whitelist))


_ENDPOINT_PARAM_KINDS = {Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD}


def patch_endpoint_signature(
    endpoint: Callable,
    handler: Callable = None,
    dependencies: Iterable[Tuple[str, Type]] = None,
) -> Callable:
    signature = get_signature(endpoint)
    parameters = chain(
        _build_dependencies_parameters(dependencies or ()),
        _get_signature_parameters(signature),
        _get_signature_parameters(get_signature(handler)) if handler else [],
    )
    # Parameters defined in handler function can overlap predefined ones from dependencies,
    # so we need to filter it out, as dependency/endpoint params have greater priority
    unique_parameters = list(distinct(parameters, attrgetter('name')))
    endpoint.__signature__ = signature.replace(parameters=unique_parameters)  # type: ignore
    return endpoint


def _build_dependencies_parameters(dependencies: Iterable) -> Iterator[Parameter]:
    for (dependency_name, dependency_type) in dependencies:
        yield Parameter(
            name=dependency_name,
            kind=Parameter.KEYWORD_ONLY,
            annotation=dependency_type,
            default=Depends(),
        )


def _get_signature_parameters(signature: Signature) -> Iterator[Parameter]:
    for param in signature.parameters.values():
        if param.kind in _ENDPOINT_PARAM_KINDS:
            yield param
