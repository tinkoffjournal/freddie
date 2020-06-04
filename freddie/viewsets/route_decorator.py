from inspect import getmembers
from typing import TYPE_CHECKING, Any, Callable, Iterator

if TYPE_CHECKING:
    from typing_extensions import Protocol

    class ViewSetRoute(Protocol):
        name: str
        path: str
        is_detail: bool
        kwargs: dict


else:
    ViewSetRoute = Callable

VIEWSET_ROUTE_FLAG = 'is_viewset_route'


def route(detail: bool = False, path: str = None, name: str = None, **kwargs: Any) -> Callable:
    def decorator(endpoint: ViewSetRoute) -> ViewSetRoute:
        setattr(endpoint, VIEWSET_ROUTE_FLAG, True)
        endpoint_name = name or getattr(endpoint, '__name__')
        endpoint.name = endpoint_name
        endpoint.path = path or f'/{endpoint_name}'
        endpoint.is_detail = detail
        endpoint.kwargs = kwargs
        return endpoint

    return decorator


def get_declared_routes(obj: Any) -> Iterator[ViewSetRoute]:
    for _, route_endpoint in getmembers(
        obj, lambda member: callable(member) and hasattr(member, VIEWSET_ROUTE_FLAG)
    ):
        yield route_endpoint
