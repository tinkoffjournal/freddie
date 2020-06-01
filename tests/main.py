from typing import List

from fastapi import FastAPI, Request

from freddie import __version__ as freddie_version, Schema
from freddie.exceptions import NotFound
from freddie.viewsets import route, ViewSet, PaginatedListViewset, ListViewset, FieldedRetrieveViewset, RetrieveViewset


class Item(Schema):
    id: int = 42
    title: str = ...
    metadata: dict = {'foo': 'bar'}

    def update(self, body: Schema) -> 'Item':
        updated = self.copy()
        for key, value in body.dict(exclude_unset=True).items():
            setattr(updated, key, value)
        return updated

    @classmethod
    def paginate(cls, limit: int, offset: int = 0):
        for i in range(1, limit + 1):
            item_id = i + offset
            yield cls(id=item_id, title='Freddie')


class AnotherItem(Item):
    ...


class SyncItem(Item):
    ...


test_item = Item(title='Hello')
test_items_seq = [test_item, Item(id=43, title='Hi')]


class TestViewSet(ViewSet):
    schema = Item

    async def list(self, *, request: Request, **params) -> List[Item]:
        return test_items_seq

    async def retrieve(self, pk, *, request: Request, **params) -> Item:
        return test_item

    async def create(self, body: Item, *, request: Request, **params) -> Item:
        return body

    async def update(self, pk, body: Schema, *, request: Request, **params) -> Item:
        return test_item.update(body)

    async def destroy(self, pk, *, request: Request, **params) -> None:
        pass

    @route(detail=False)
    async def listroute(self, *, foo: str, bar: int):
        return {'foo': foo, 'bar': bar}

    @route(detail=True)
    async def detail(self, *, foo: str, bar: int):
        return {'foo': foo, 'bar': bar}

    @route(detail=False, name='listcustom')
    async def listroute_named(self, *, foo: str, bar: int):
        return {'foo': foo, 'bar': bar}

    @route(detail=True, name='detailcustom')
    async def detail_named(self, *, foo: str, bar: int):
        return {'foo': foo, 'bar': bar}


class TestViewSetSync(TestViewSet):
    def list(self, *, request: Request, **params) -> List[Item]:
        return test_items_seq

    def retrieve(self, pk, *, request: Request, **params) -> Item:
        return test_item

    def create(self, body: Item, *, request: Request, **params) -> Item:
        return body

    def update(self, pk, body: Schema, *, request: Request, **params) -> Item:
        return test_item.update(body)

    def destroy(self, pk, *, request: Request, **params) -> None:
        pass


class Paginated(PaginatedListViewset, ListViewset):
    async def list(self, *, paginator, **params):
        return Item.paginate(paginator.limit, paginator.offset)


class FieldedItem(Item):
    class Config:
        default_readable_fields = {'id'}


class Fielded(FieldedRetrieveViewset, RetrieveViewset, ListViewset):
    schema = FieldedItem

    async def list(self, *, paginator, **params):
        return Item.paginate(paginator.limit, paginator.offset)

    async def retrieve(self, pk, *, fields, **params) -> Item:
        return test_item


app = FastAPI(title='🕺 Freddie', version=freddie_version)
app.include_router(TestViewSet(), prefix='/unvalidated')
app.include_router(TestViewSet(validate_response=True, schema=AnotherItem), prefix='/validated')
app.include_router(TestViewSetSync(schema=SyncItem), prefix='/sync')
app.include_router(Paginated(schema=Item), prefix='/paginated')
app.include_router(Fielded(), prefix='/fielded')


@app.api_route('/notfound')
def notfound(detail: str, header: str):
    raise NotFound(detail, headers={'x-custom-header': header})


if __name__ == '__main__':
    from os import environ
    import uvicorn

    port = int(environ.get('PORT', 8000))
    uvicorn.run('main:app', port=port, access_log=False, reload=True, use_colors=True)
