from typing import (
    Any,
    AsyncIterable,
    Callable,
    Dict,
    Iterable,
    Iterator,
    Optional,
    Tuple,
    Type,
    Union,
)

from peewee import Ordering
from starlette.requests import Request

from ..db.models import (
    CharField,
    DBField,
    FieldsMap,
    ForeignKeyField,
    ManyToManyField,
    Model,
    PropsDependenciesMap,
)
from ..db.queries import (
    JOIN,
    Expression,
    Function,
    Prefetch,
    Query,
    get_related,
    prefetch_related,
    set_related,
)
from ..exceptions import NotFound, ServerError, Unprocessable, db_errors_handler
from ..helpers import init_sql_logger, is_iterable
from ..schemas import Schema
from .dependencies import FILTERABLE_VIEWSET_FLAG, FilterBy, Paginator, ResponseFieldsDict
from .generics import (
    FIELDS_PARAM_NAME,
    CreateViewset,
    DestroyViewset,
    GenericViewSet,
    ListViewset,
    RetrieveViewset,
    UpdateViewset,
)

FK_FIELD_POSTFIX = '_id'
M2M_FIELD_POSTFIX = '_ids'
ModelPK = Any
ModelData = Dict[str, Any]
ModelRelations = Iterable[Tuple[ManyToManyField, set]]
ExtraFields = Dict[str, Union[DBField, Function]]


class GenericModelViewSet(GenericViewSet):
    model: Type[Model] = Model
    pk_field: DBField
    secondary_lookup_field: Optional[DBField] = None
    model_ordering: Tuple[Union[DBField, Ordering], ...] = ()
    _model_fields: FieldsMap
    _model_props_dependencies: PropsDependenciesMap
    _is_filterable_by_query_params: bool = False
    _VALIDATE_SCHEMA_CONSTR: bool = False

    def __init__(
        self,
        *args: Any,
        model: Type[Model] = None,
        model_ordering: Tuple[Union[DBField, Ordering], ...] = (),
        sql_debug: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.model = self.validate_model(model or self.model)
        self.pk_field = self.model.pk_field()
        self._model_fields = self.model.fields()
        if model_ordering:
            self.model_ordering = model_ordering
        if self._VALIDATE_SCHEMA_CONSTR:
            self.validate_schema_constraints()
        self._model_props_dependencies = self.model.map_props_dependencies()
        if self.validate_response:
            self.schema.__config__.orm_mode = True
        self._is_filterable_by_query_params = hasattr(self, FILTERABLE_VIEWSET_FLAG)
        if sql_debug:
            init_sql_logger()

    def validate_model(self, model: Type[Model]) -> Type[Model]:
        cls_name = type(self).__name__
        model_name = model.__name__
        assert isinstance(model, type), f'Model for {cls_name} must be a class'
        assert issubclass(
            model, Model
        ), f'Model for {cls_name} must be subclassed from {Model.__name__}'
        assert model.db() is not None, f'{model_name} database not set'
        assert model.manager is not None, f'{model_name} database manager not set'
        if self.secondary_lookup_field is not None:
            assert (
                len(self._pk_type_choices) > 1
            ), f'{cls_name}: secondary lookup field type must be set'
            assert (
                self.secondary_lookup_field.unique
            ), f'{cls_name}: non-unique secondary lookup field'
        return model

    def validate_schema_constraints(self) -> None:
        writable_schema_fields = self.schema.get_writable_fields()
        for field_name, db_field in self.model.fields().items():
            if isinstance(db_field, CharField) and field_name in writable_schema_fields:
                schema_max_length = self.schema.get_field_max_length(field_name)
                if not schema_max_length or schema_max_length > db_field.max_length:
                    raise AssertionError(
                        f'{self.schema.__name__}.{field_name} '
                        f'maxlength not set or greater than DB field maxlength'
                    )

    def lookup_expr(self, pk: Any) -> Expression:
        if self.secondary_lookup_field is not None and type(pk) != self._pk_type_choices[0]:
            return self.secondary_lookup_field == pk
        return self.pk_field == pk

    def apply_query_filters(self, query: Query, **params: Any) -> Query:
        if self._is_filterable_by_query_params:
            filter_params = params.get(FilterBy.PARAM_NAME, {})
            for field_name, filter_value in filter_params.items():
                model_field = self._model_fields.get(field_name)
                if model_field:
                    query = query.where(model_field == filter_value)
        return query

    def construct_query(
        self, request: Request, fields: ResponseFieldsDict = None, extra: ExtraFields = None
    ) -> Query:
        fields = fields if fields is not None else self._response_fields_default_config
        selected = set()
        joined = set()
        model_fields = {field_name: self._model_fields.get(field_name) for field_name in fields}
        for field_name, db_field in model_fields.items():
            # Foreign key ID
            if db_field is None and field_name.endswith(FK_FIELD_POSTFIX):
                selected.add(self._model_fields.get(field_name[: -len(FK_FIELD_POSTFIX)]))

            # Model property/getter method decorated with @depends_on
            elif db_field is None:
                dependencies: Iterable[DBField] = self._model_props_dependencies.get(field_name, [])
                for required_field in dependencies:
                    selected.add(required_field)
                fk_dependencies: Iterator[ForeignKeyField] = filter(
                    lambda f: isinstance(f, ForeignKeyField), dependencies
                )
                for fk in fk_dependencies:
                    joined.add(fk.rel_model)
                    selected.add(fk.rel_model)

            # Add related models
            # TODO: select only necessary related model fields
            elif isinstance(db_field, ForeignKeyField):
                joined.add(db_field.rel_model)
                selected.add(db_field.rel_model)

            # Just normal DB column to select
            else:
                selected.add(db_field)

        for alias, field in (extra or {}).items():
            if isinstance(field, (DBField, Function)):
                selected.add(field.alias(alias))

        query = self.model.select(*(selected or (self.pk_field,)))
        if self.model_ordering:
            query = query.order_by(*self.model_ordering)
        for joined_model in joined:
            query = query.join_from(self.model, joined_model, JOIN.LEFT_OUTER)
        return query

    def build_prefetch_config(self, fields: ResponseFieldsDict) -> Iterator[Prefetch]:
        for field_name in fields:
            attr_name = field_name
            ids_only = field_name.endswith(M2M_FIELD_POSTFIX)
            if ids_only:
                field_name = field_name[: -len(M2M_FIELD_POSTFIX)]
            field = self.model.manytomany.get(field_name)
            if field:
                yield Prefetch(
                    field=field,
                    attr_name=attr_name,
                    ids_only=ids_only,
                )

    async def get_object_or_404(
        self, pk: Any, request: Request, fields: ResponseFieldsDict = None
    ) -> Model:
        query = self.construct_query(request, fields)
        query = self.apply_query_filters(query).where(self.lookup_expr(pk))
        try:
            obj = await self.model.manager.get(query)
        except self.model.DoesNotExist:
            raise NotFound(f'{self._component_name.title()} not found')
        related_config = list(self.build_prefetch_config(fields or {}))
        if related_config:
            related = await get_related(obj.pk, related_config)
            for attr_name, items in related.items():
                setattr(obj, attr_name, items)
        return obj

    def serialize_request_body_for_db(
        self, body: Schema, on_create: bool = False
    ) -> Tuple[ModelData, ModelRelations]:
        data = {}
        related = []
        excluded_keys = self.schema.get_read_only_fields() | {self.pk_field.name}
        serialized = body.dict(
            exclude=excluded_keys,
            exclude_unset=not on_create,
            exclude_none=True,
            by_alias=True,
        )
        for key, value in serialized.items():
            if key not in self._model_fields:
                # Handle one-to-many relations
                if key.endswith(FK_FIELD_POSTFIX):
                    field_name = key[: -len(FK_FIELD_POSTFIX)]
                    if field_name in self._model_fields:
                        data[field_name] = value
                # Handle many-to-many relations
                elif key.endswith(M2M_FIELD_POSTFIX) and is_iterable(value):
                    field_name = key[: -len(M2M_FIELD_POSTFIX)]
                    field = self.model.manytomany.get(field_name)
                    if field is not None:
                        related.append((field, set(value)))
                continue
            data[key] = value
        return data, related


class ModelRetrieveViewset(GenericModelViewSet, RetrieveViewset):
    async def retrieve(self, pk: Any, *, request: Request, **params: Any) -> Model:
        fields = params.get(FIELDS_PARAM_NAME) or self._response_fields_default_config
        return await self.get_object_or_404(pk, request=request, fields=fields)


class ModelListViewset(GenericModelViewSet, ListViewset):
    async def list(
        self,
        *,
        request: Request,
        **params: Any,
    ) -> Union[Iterable[Model], AsyncIterable[Model]]:
        fields = params.get(FIELDS_PARAM_NAME) or self._response_fields_default_config
        query = self.construct_query(request, fields)
        query = self.apply_dependencies_params(query, **params)
        objects = await self.model.manager.execute(query)
        prefetched_config = list(self.build_prefetch_config(fields))
        if prefetched_config:
            return prefetch_related(objects, prefetched_config)
        return (obj for obj in objects)

    def apply_dependencies_params(self, query: Query, **params: Any) -> Query:
        filter_by: Optional[FilterBy] = params.get(FilterBy.PARAM_NAME)
        if filter_by:
            query = self.apply_query_filters(query, **params)
        paginator: Optional[Paginator] = params.get(Paginator.PARAM_NAME)
        if paginator:
            query = self.paginate_query(query, paginator)
        return query

    def paginate_query(self, query: Query, paginator: Paginator) -> Query:
        if paginator.limit:
            query = query.limit(paginator.limit)
        if paginator.offset:
            query = query.offset(paginator.offset)
        return query


class ModelCreateViewset(GenericModelViewSet, CreateViewset):
    _VALIDATE_SCHEMA_CONSTR = True

    async def perform_api_action(
        self, handler: Callable, *args: Any, request: Request, **kwargs: Any
    ) -> Any:
        if handler == self.create:
            pk = await super().perform_api_action(handler, *args, request=request, **kwargs)
            return await self.get_object_or_404(
                pk, request=request, fields=self._response_fields_full_config
            )
        return await super().perform_api_action(handler, *args, request=request, **kwargs)

    async def create(self, body: Schema, *, request: Request, **params: Any) -> ModelPK:
        data, related = self.serialize_request_body_for_db(body, on_create=True)
        if not data:
            raise Unprocessable('Empty request body')
        with db_errors_handler():
            pk = await self.perform_create(data, request=request, **params)
        if not pk:
            raise ServerError(f'{self._component_name.title()} not created')  # pragma: no cover
        with db_errors_handler():
            for field, ids in related:
                if not ids:
                    continue
                await set_related(pk, field, ids)
        return pk

    async def perform_create(self, data: ModelData, **params: Any) -> Any:
        query = self.model.insert(**data)
        return await self.model.manager.execute(query)


class ModelUpdateViewset(GenericModelViewSet, UpdateViewset):
    _VALIDATE_SCHEMA_CONSTR = True

    async def perform_api_action(
        self, handler: Callable, *args: Any, request: Request, **kwargs: Any
    ) -> Any:
        if handler == self.update:
            pk = await super().perform_api_action(handler, *args, request=request, **kwargs)
            return await self.get_object_or_404(
                pk, request=request, fields=self._response_fields_full_config
            )
        return await super().perform_api_action(handler, *args, request=request, **kwargs)

    async def update(
        self, pk: ModelPK, body: Schema, *, request: Request, **params: Any
    ) -> ModelPK:
        data, related = self.serialize_request_body_for_db(body, on_create=False)
        if data:
            with db_errors_handler():
                updated = await self.perform_update(pk, data, request=request, **params)
            if not updated:
                raise ServerError(f'{self._component_name.title()} not updated')  # pragma: no cover
        with db_errors_handler():
            for field, ids in related:
                await set_related(pk, field, ids)
        return pk

    async def perform_update(self, pk: ModelPK, data: ModelData, **params: Any) -> Any:
        query = self.model.update(**data)
        query = self.apply_query_filters(query, **params).where(self.lookup_expr(pk))
        return await self.model.manager.execute(query)


class ModelDestroyViewset(GenericModelViewSet, DestroyViewset):
    async def destroy(self, pk: ModelPK, *, request: Request, **params: Any) -> None:
        deleted = await self.perform_destroy(pk, request=request, **params)
        if not deleted:
            raise ServerError(f'{self._component_name.title()} not deleted')  # pragma: no cover

    async def perform_destroy(self, pk: ModelPK, **params: Any) -> Any:
        query = self.model.delete()
        query = self.apply_query_filters(query, **params).where(self.lookup_expr(pk))
        return await self.model.manager.execute(query)


class ReadOnlyModelViewSet(ModelListViewset, ModelRetrieveViewset):
    ...


class ListCreateModelViewSet(ModelListViewset, ModelCreateViewset):
    ...


class RetrieveUpdateModelViewSet(ModelRetrieveViewset, ModelUpdateViewset):
    ...


class RetrieveUpdateModelDestroyViewSet(
    ModelRetrieveViewset, ModelUpdateViewset, ModelDestroyViewset
):
    ...


class ModelViewSet(
    ModelListViewset,
    ModelRetrieveViewset,
    ModelCreateViewset,
    ModelUpdateViewset,
    ModelDestroyViewset,
):
    ...
