from typing import Type

from ..schemas import SchemaClass
from .dependencies import FilterBy, Paginator, ResponseFields
from .generics import Dependency, PredefinedDependencies


class FieldedViewset:
    schema: SchemaClass

    def _get_dependency(self) -> Dependency:
        return (
            ResponseFields.PARAM_NAME,
            ResponseFields.setup(
                allowed=self.schema.get_readable_fields(),
                defaults=self.schema.get_default_response_fields_config(),
            ),
        )


class FieldedListViewset(FieldedViewset):
    def get_list_dependencies(self) -> PredefinedDependencies:
        return super().get_list_dependencies() + (self._get_dependency(),)  # type: ignore


class FieldedRetrieveViewset(FieldedViewset):
    def get_retrieve_dependencies(self) -> PredefinedDependencies:
        return super().get_retrieve_dependencies() + (self._get_dependency(),)  # type: ignore


class PaginatedListViewset:
    Paginator: Type = Paginator

    def get_list_dependencies(self) -> PredefinedDependencies:
        paginator = Paginator.PARAM_NAME, Paginator.setup(self.Paginator)
        return super().get_list_dependencies() + (paginator,)  # type: ignore


class FilterableListViewset:
    Filter: Type = FilterBy

    def get_list_dependencies(self) -> PredefinedDependencies:
        filter_by = FilterBy.PARAM_NAME, FilterBy.setup(self.Filter)
        return super().get_list_dependencies() + (filter_by,)  # type: ignore
