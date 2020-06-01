from typing import List

from fastapi import FastAPI, Request

from freddie import __version__ as freddie_version, Schema, ViewSet
from freddie.viewsets import route


class Item(Schema):
    id: int = 42
    title: str = ...
    metadata: dict = {'foo': 'bar'}


class AnotherItem(Item):
    ...


test_item = Item(title='Hello')
test_items_list = [test_item, Item(id=43, title='Hi')]


class TestViewSet(ViewSet):
    schema = Item

    async def list(self, *, request: Request, **params) -> List[Item]:
        return test_items_list

    async def retrieve(self, pk, *, request: Request, **params) -> Item:
        return test_item

    async def create(self, body: Item, *, request: Request, **params) -> Item:
        return body

    async def update(self, pk, body: Schema, *, request: Request, **params) -> Item:
        updated_item = test_item.copy()
        for key, value in body.dict(exclude_unset=True).items():
            setattr(updated_item, key, value)
        return updated_item

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


app = FastAPI(title='🕺 Freddie', version=freddie_version)
app.include_router(TestViewSet())
app.include_router(TestViewSet(validate_response=True, schema=AnotherItem), prefix='/other')

if __name__ == '__main__':
    from os import environ
    import uvicorn

    port = int(environ.get('PORT', 8000))
    uvicorn.run('main:app', port=port, access_log=False, reload=True, use_colors=True)
