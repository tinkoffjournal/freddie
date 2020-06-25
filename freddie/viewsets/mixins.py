from typing import Any, Type

from ..schemas import SchemaClass
from .dependencies import FILTERABLE_VIEWSET_FLAG, FilterBy, Paginator, ResponseFields
from .generics import Dependency, PredefinedDependencies


class FieldedViewsetMixin:
    schema: SchemaClass

    @staticmethod
    def setup_response_fields(schema: SchemaClass) -> Type[ResponseFields]:
        return ResponseFields.setup(
            allowed=schema.get_readable_fields(),
            defaults=schema.get_default_response_fields_config(),
        )

    def _get_dependency(self) -> Dependency:
        return (
            ResponseFields.PARAM_NAME,
            self.setup_response_fields(self.schema),
        )


class FieldedListViewset(FieldedViewsetMixin):
    def get_list_dependencies(self) -> PredefinedDependencies:
        return super().get_list_dependencies() + (self._get_dependency(),)  # type: ignore


class FieldedRetrieveViewset(FieldedViewsetMixin):
    def get_retrieve_dependencies(self) -> PredefinedDependencies:
        return super().get_retrieve_dependencies() + (self._get_dependency(),)  # type: ignore


class FieldedViewset(FieldedListViewset, FieldedRetrieveViewset):
    ...


class PaginatedListViewset:
    Paginator: Type = Paginator

    def get_list_dependencies(self) -> PredefinedDependencies:
        paginator = Paginator.PARAM_NAME, Paginator.setup(self.Paginator)
        return super().get_list_dependencies() + (paginator,)  # type: ignore


class FilterableListViewset:
    Filter: Type = FilterBy

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__()
        setattr(cls, FILTERABLE_VIEWSET_FLAG, True)

    def get_list_dependencies(self) -> PredefinedDependencies:
        filter_by = FilterBy.PARAM_NAME, FilterBy.setup(self.Filter)
        return super().get_list_dependencies() + (filter_by,)  # type: ignore
