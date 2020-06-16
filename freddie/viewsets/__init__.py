from .dependencies import Paginator
from .generics import (
    CreateViewset,
    DestroyViewset,
    ListCreateViewSet,
    ListViewset,
    ReadOnlyViewSet,
    RetrieveUpdateDestroyViewSet,
    RetrieveUpdateViewSet,
    RetrieveViewset,
    UnsupportedViewset,
    UpdateViewset,
    ViewSet,
)
from .mixins import (
    FieldedListViewset,
    FieldedRetrieveViewset,
    FieldedViewset,
    FilterableListViewset,
    PaginatedListViewset,
)
from .route_decorator import route

try:
    from .sql import (
        ListCreateModelViewSet,
        ModelViewSet,
        ReadOnlyModelViewSet,
        RetrieveUpdateModelDestroyViewSet,
        RetrieveUpdateModelViewSet,
    )
except ModuleNotFoundError:

    class UnsupportedDBViewset(UnsupportedViewset):
        error_message = 'database support not installed'

    ListCreateModelViewSet = UnsupportedDBViewset  # type: ignore
    ModelViewSet = UnsupportedDBViewset  # type: ignore
    ReadOnlyModelViewSet = UnsupportedDBViewset  # type: ignore
    RetrieveUpdateModelDestroyViewSet = UnsupportedDBViewset  # type: ignore
    RetrieveUpdateModelViewSet = UnsupportedDBViewset  # type: ignore

__all__ = (
    'CreateViewset',
    'DestroyViewset',
    'FieldedViewset',
    'FieldedListViewset',
    'FieldedRetrieveViewset',
    'FilterableListViewset',
    'ListCreateViewSet',
    'ListViewset',
    'Paginator',
    'PaginatedListViewset',
    'ReadOnlyViewSet',
    'RetrieveUpdateDestroyViewSet',
    'RetrieveUpdateViewSet',
    'RetrieveViewset',
    'UpdateViewset',
    'ViewSet',
    'route',
    'ReadOnlyModelViewSet',
    'ListCreateModelViewSet',
    'RetrieveUpdateModelViewSet',
    'RetrieveUpdateModelDestroyViewSet',
    'ModelViewSet',
)
