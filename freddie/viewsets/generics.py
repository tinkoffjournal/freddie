from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import Any, AsyncIterable, Callable, Dict, Iterable, List, Optional, Tuple, Type, Union
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Response
from fastapi.datastructures import Default, DefaultPlaceholder
from pydantic.fields import FieldInfo
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..helpers import extract_types, is_valid_type, patch_endpoint_signature, run_async_or_thread
from ..schemas import ApiComponentName, Schema, SchemaClass, validate_schema
from .dependencies import ResponseFields, ResponseFieldsDict
from .route_decorator import get_declared_routes
from .signals import Signal, SignalDispatcher, get_signals_map

VALID_PK_TYPES = {int, str, UUID}
DEFAULT_PK_TYPE = int
DETAIL_ROUTE_PATTERN = '/{pk}'
FIELDS_PARAM_NAME = ResponseFields.PARAM_NAME

_default_response_cls = Default(JSONResponse)


class GenericViewSet(APIRouter, ABC):
    schema: SchemaClass = Schema
    write_schema: Optional[SchemaClass] = None
    pk_type: Type = DEFAULT_PK_TYPE
    pk_parameter: FieldInfo

    _component_name: str
    _component_name_plural: str
    _pk_type_choices: Tuple[Type, ...]
    _openapi_tags: List[str]
    _response_fields_default_config: ResponseFieldsDict
    _response_fields_full_config: ResponseFieldsDict
    _signals_dispatcher_type: Type[SignalDispatcher]
    validate_response: bool
    default_response_class: Type[Response]

    def __init__(
        self,
        *args: Any,
        schema: SchemaClass = None,
        write_schema: SchemaClass = None,
        pk_type: Type = None,
        pk_parameter: FieldInfo = None,
        validate_response: bool = False,
        **kwargs: Any,
    ):
        self.schema = schema or self.schema
        self.write_schema = write_schema or self.write_schema
        self.validate_schema()
        self.set_components_names()
        self.pk_type = pk_type or self.pk_type
        self._pk_type_choices = tuple(_get_pk_type_choices(self.pk_type))
        self.pk_parameter = pk_parameter or Path(
            ...,
            title=f'{self._component_name.title()} lookup field',
            description='Lookup value',
        )
        self._openapi_tags = self.get_openapi_tags()
        self._response_fields_default_config = self.schema.get_default_response_fields_config()
        self._response_fields_full_config = self.schema.get_full_response_fields_config()
        self._signals_dispatcher_type = SignalDispatcher.setup(get_signals_map(self))
        super().__init__(*args, **kwargs)
        self.validate_response = validate_response
        self.default_response_class = (
            self.default_response_class
            if not isinstance(self.default_response_class, DefaultPlaceholder)
            else JSONResponse
        )
        self.add_routes_from_class_declaration()
        self.api_actions()

    def validate_schema(self) -> None:
        validate_schema(self.schema)
        if self.write_schema:
            validate_schema(self.write_schema)

    def set_components_names(self) -> None:
        schema_config = self.schema.get_config()
        component_name = schema_config.api_component_name or self.schema.__name__
        self._component_name = ApiComponentName.validate(component_name)
        component_name_plural = schema_config.api_component_name_plural or f'{component_name}s'
        self._component_name_plural = ApiComponentName.validate(component_name_plural)

    def get_openapi_tags(self) -> List[str]:
        return [self._component_name.title()]

    def notfound_response(self) -> 'ResponsesDict':
        return {
            int(HTTPStatus.NOT_FOUND): {
                'description': f'{self._component_name.title()} instance not found',
            }
        }

    def add_routes_from_class_declaration(self) -> None:
        for route in get_declared_routes(self):
            path = route.path
            if route.is_detail:
                path = DETAIL_ROUTE_PATTERN + path
            kwargs = route.kwargs.copy()
            operation_id = kwargs.pop('operation_id', None)
            if not operation_id:
                operation_id_prefix = (
                    self._component_name if route.is_detail else self._component_name_plural
                )
                operation_id = f'{operation_id_prefix}_{route.name}'
            summary = kwargs.pop('summary', None)
            if not summary:
                summary = route.name.title().replace('_', ' ')
            tags = kwargs.pop('tags', []) + self._openapi_tags
            self.add_api_route(
                path,
                route,  # type: ignore
                operation_id=operation_id,
                summary=summary,
                tags=tags,
                **kwargs,
            )

    async def response(
        self, content: Any, status_code: int = 200, fields: ResponseFieldsDict = None
    ) -> Any:
        if isinstance(content, Response) or self.validate_response:
            return content
        content = await self.schema.serialize(content, fields)
        return self.default_response_class(content=content, status_code=status_code)

    async def perform_api_action(self, handler: Callable, *args: Any, **kwargs: Any) -> Any:
        return await run_async_or_thread(handler, *args, **kwargs)

    @abstractmethod
    def api_actions(self) -> None:
        ...

    async def get_object_or_404(
        self, pk: Any, request: Request, fields: ResponseFieldsDict = None
    ) -> Any:
        ...

    async def validate_request_body(self, body: Schema, obj: Any = None) -> None:
        ...


def _get_pk_type_choices(pk_type: Type) -> Iterable[Type]:
    for type_ in extract_types(pk_type):
        if not is_valid_type(type_, VALID_PK_TYPES):
            raise TypeError(f'{type_} is not a valid ViewSet PK type. Allowed: {VALID_PK_TYPES}')
        yield type_


class ListViewset(GenericViewSet):
    def get_list_dependencies(self) -> 'PredefinedDependencies':
        return ()

    def api_actions(self) -> None:
        super().api_actions()
        status_code = int(HTTPStatus.OK)
        response_model = List[self.schema]  # type: ignore

        async def endpoint(*, request: Request, **params: Any) -> Any:
            objects = await self.perform_api_action(self.list, request=request, **params)
            return await self.response(objects, fields=params.get(FIELDS_PARAM_NAME))

        self.add_api_route(
            '/',
            patch_endpoint_signature(endpoint, self.list, self.get_list_dependencies()),
            methods=['GET'],
            status_code=status_code,
            response_class=_default_response_cls if self.validate_response else Response,
            response_model=response_model if self.validate_response else None,
            response_description=f'{self._component_name_plural.title()} listed',
            responses={status_code: {'model': response_model}},
            operation_id=f'list_{self._component_name_plural}',
            summary=f'List {self._component_name_plural}',
            tags=self._openapi_tags,
        )

    @abstractmethod
    async def list(self, *, request: Request, **params: Any) -> Union[Iterable, AsyncIterable]:
        ...  # pragma: no cover


class RetrieveViewset(GenericViewSet):
    def get_retrieve_dependencies(self) -> 'PredefinedDependencies':
        return ()

    def api_actions(self) -> None:
        super().api_actions()

        pk_type = self.pk_type
        status_code = int(HTTPStatus.OK)

        async def endpoint(
            pk: pk_type = self.pk_parameter,  # type: ignore
            *,
            request: Request,
            **params: Any,
        ) -> Any:
            obj = await self.perform_api_action(self.retrieve, pk, request=request, **params)
            return await self.response(obj, fields=params.get(FIELDS_PARAM_NAME))

        self.add_api_route(
            DETAIL_ROUTE_PATTERN,
            patch_endpoint_signature(endpoint, self.retrieve, self.get_retrieve_dependencies()),
            methods=['GET'],
            status_code=status_code,
            response_class=_default_response_cls if self.validate_response else Response,
            response_model=self.schema if self.validate_response else None,
            response_description=f'{self._component_name.title()} instance retrieved',
            responses={**self.notfound_response(), status_code: {'model': self.schema}},
            operation_id=f'get_{self._component_name}',
            summary=f'Retrieve {self._component_name}',
            tags=self._openapi_tags,
        )

    @abstractmethod
    async def retrieve(self, pk: Any, *, request: Request, **params: Any) -> Any:
        ...  # pragma: no cover


class CreateViewset(GenericViewSet):
    def api_actions(self) -> None:
        super().api_actions()

        status_code = int(HTTPStatus.CREATED)
        request_body_type = self.write_schema or self.schema
        signals_dispatcher = self._signals_dispatcher_type

        async def endpoint(
            body: request_body_type = Body(...),  # type: ignore
            *,
            request: Request,
            signals: signals_dispatcher = Depends(),  # type: ignore
            **params: Any,
        ) -> Any:
            await self.validate_request_body(body)
            obj = await self.perform_api_action(self.create, body, request=request, **params)
            signals.send(Signal.POST_SAVE, obj, created=True)  # type: ignore
            return await self.response(obj, status_code, fields=self._response_fields_full_config)

        self.add_api_route(
            '/',
            patch_endpoint_signature(endpoint, self.create),
            methods=['POST'],
            status_code=status_code,
            response_class=_default_response_cls if self.validate_response else Response,
            response_model=self.schema if self.validate_response else None,
            response_description=f'{self._component_name.title()} instance created',
            responses={status_code: {'model': self.schema}},
            operation_id=f'create_{self._component_name}',
            summary=f'Create {self._component_name}',
            tags=self._openapi_tags,
        )

    @abstractmethod
    async def create(self, body: Schema, *, request: Request, **params: Any) -> Any:
        ...  # pragma: no cover


class UpdateViewset(GenericViewSet):
    def api_actions(self) -> None:
        super().api_actions()

        pk_type = self.pk_type
        request_body_type = self.write_schema or self.schema
        request_body_partial_type = request_body_type.optional(
            f'{self.schema.__name__}UpdateRequest'
        )
        signals_dispatcher = self._signals_dispatcher_type
        status_code = int(HTTPStatus.OK)
        responses: 'ResponsesDict' = {
            **self.notfound_response(),
            status_code: {'model': self.schema},
        }
        response_fields = self._response_fields_full_config

        async def update_endpoint(
            pk: pk_type = self.pk_parameter,  # type: ignore
            body: request_body_type = Body(...),  # type: ignore
            *,
            request: Request,
            signals: signals_dispatcher = Depends(),  # type: ignore
            **params: Any,
        ) -> Any:
            obj = await self.get_object_or_404(
                pk, request=request, fields=self._response_fields_full_config
            )
            await self.validate_request_body(body, obj)
            pk = getattr(obj, 'pk', pk)
            updated_obj = await self.perform_api_action(
                self.update, pk, body, partial=False, request=request, **params
            )
            signals.send(  # type: ignore
                Signal.POST_SAVE, updated_obj, obj_before_update=obj, created=False
            )
            return await self.response(updated_obj, fields=response_fields)

        async def update_partial_endpoint(
            pk: pk_type = self.pk_parameter,  # type: ignore
            body: request_body_partial_type = Body(...),  # type: ignore
            *,
            request: Request,
            signals: signals_dispatcher = Depends(),  # type: ignore
        ) -> Any:
            obj = await self.get_object_or_404(
                pk, request=request, fields=self._response_fields_full_config
            )
            await self.validate_request_body(body, obj)
            pk = getattr(obj, 'pk', pk)
            updated_obj = await self.perform_api_action(
                self.update, pk, body, partial=True, request=request
            )
            signals.send(  # type: ignore
                Signal.POST_SAVE, updated_obj, obj_before_update=obj, created=False
            )
            return await self.response(updated_obj, fields=response_fields)

        self.add_api_route(
            DETAIL_ROUTE_PATTERN,
            patch_endpoint_signature(update_endpoint, self.update),
            methods=['PUT'],
            status_code=status_code,
            response_class=_default_response_cls if self.validate_response else Response,
            response_model=self.schema if self.validate_response else None,
            response_description=f'{self._component_name.title()} instance fully updated',
            responses=responses,
            operation_id=f'full_update_{self._component_name}',
            summary=f'Full update {self._component_name}',
            tags=self._openapi_tags,
        )
        self.add_api_route(
            DETAIL_ROUTE_PATTERN,
            patch_endpoint_signature(update_partial_endpoint, self.update),
            methods=['PATCH'],
            status_code=status_code,
            response_class=_default_response_cls if self.validate_response else Response,
            response_model=self.schema if self.validate_response else None,
            response_description=f'{self._component_name.title()} instance updated',
            responses=responses,
            operation_id=f'update_{self._component_name}',
            summary=f'Update {self._component_name}',
            tags=self._openapi_tags,
        )

    @abstractmethod
    async def update(self, pk: Any, body: Schema, *, request: Request, **params: Any) -> Any:
        ...  # pragma: no cover


class DestroyViewset(GenericViewSet):
    def api_actions(self) -> None:
        super().api_actions()

        pk_type = self.pk_type
        signals_dispatcher = self._signals_dispatcher_type
        status_code = int(HTTPStatus.NO_CONTENT)

        async def endpoint(
            pk: pk_type = self.pk_parameter,  # type: ignore
            *,
            request: Request,
            signals: signals_dispatcher = Depends(),  # type: ignore
            **params: Any,
        ) -> Response:
            obj = await self.get_object_or_404(
                pk, request=request, fields=self._response_fields_full_config
            )
            await self.perform_api_action(self.destroy, pk, request=request, **params)
            signals.send(Signal.POST_DELETE, obj)  # type: ignore
            return Response('', status_code=int(HTTPStatus.NO_CONTENT))

        self.add_api_route(
            DETAIL_ROUTE_PATTERN,
            patch_endpoint_signature(endpoint, self.destroy),
            methods=['DELETE'],
            status_code=status_code,
            response_description=f'{self._component_name.title()} instance deleted',
            responses=self.notfound_response(),
            operation_id=f'delete_{self._component_name}',
            summary=f'Delete {self._component_name}',
            tags=self._openapi_tags,
        )

    @abstractmethod
    async def destroy(self, pk: Any, *, request: Request, **params: Any) -> None:
        ...  # pragma: no cover


ResponsesDict = Dict[Union[int, str], Dict[str, Any]]
Dependency = Tuple[str, Type]
PredefinedDependencies = Tuple[Dependency, ...]


class UnsupportedViewset:
    error_message: str = ''

    def __init__(self, *args: Any, **kwargs: Any):
        raise RuntimeError(f'ViewSet cannot be used: {self.error_message}')  # pragma: no cover


class ReadOnlyViewSet(ListViewset, RetrieveViewset):
    ...


class ListCreateViewSet(ListViewset, CreateViewset):
    ...


class RetrieveUpdateViewSet(RetrieveViewset, UpdateViewset):
    ...


class RetrieveUpdateDestroyViewSet(RetrieveViewset, UpdateViewset, DestroyViewset):
    ...


class ViewSet(ListViewset, RetrieveViewset, CreateViewset, UpdateViewset, DestroyViewset):
    ...
