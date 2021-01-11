import logging
from inspect import (
    Parameter,
    Signature,
    isasyncgenfunction,
    iscoroutinefunction,
    signature as get_signature,
)
from itertools import chain
from operator import attrgetter
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    List,
    Mapping,
    Tuple,
    Type,
)

from fastapi import Depends
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool


def is_mappable(obj: Any) -> bool:
    return isinstance(obj, Mapping)


def is_iterable(obj: Any) -> bool:
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, BaseModel))


def is_async_iterable(obj: Any) -> bool:
    return isinstance(obj, AsyncIterable)


def is_awaitable(obj: Any) -> bool:
    return isinstance(obj, Awaitable)


async def run_async_or_thread(handler: Callable, *args: Any, **kwargs: Any) -> Any:
    if iscoroutinefunction(handler):
        return await handler(*args, **kwargs)
    elif isasyncgenfunction(handler):
        return handler(*args, **kwargs)
    return await run_in_threadpool(handler, *args, **kwargs)


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
_POS_PARAM_KINDS = {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}


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
    unique_parameters: List[Parameter] = []
    pos_param_index = 0
    for param in distinct(parameters, attrgetter('name')):
        if param.kind in _POS_PARAM_KINDS:
            unique_parameters.insert(pos_param_index, param)
            pos_param_index += 1
        else:
            unique_parameters.append(param)
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


SQL_LOGGER_NAME = 'peewee'


def init_sql_logger() -> None:
    logger = logging.getLogger(SQL_LOGGER_NAME)
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
