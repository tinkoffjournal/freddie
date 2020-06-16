from http import HTTPStatus

from pytest import mark

from freddie.viewsets.dependencies import Paginator

from .app import Item, test_item, test_items_seq
from .utils import WithClient

pytestmark = mark.asyncio
api_prefixes = {
    'argnames': 'prefix',
    'argvalues': ['/unvalidated', '/validated', '/sync'],
    'ids': ['unvalidated', 'validated', 'synchronous'],
}
pk = 42


class TestBasicViewSet(WithClient):
    async def test_api_schema_is_accessable(self):
        response = await self.client.get('/openapi.json')
        assert response.status_code == HTTPStatus.OK

    @mark.parametrize(**api_prefixes)
    async def test_list(self, prefix):
        response = await self.client.get(prefix + '/')
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await Item.serialize(test_items_seq)

    @mark.parametrize(**api_prefixes)
    async def test_retrieve(self, prefix):
        response = await self.client.get(f'{prefix}/{pk}')
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await test_item.get_serialized()

    @mark.parametrize(**api_prefixes)
    async def test_invalid_pk_retrieve(self, prefix):
        response = await self.client.get(prefix + '/foobar')
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @mark.parametrize(**api_prefixes)
    async def test_create(self, prefix):
        data = {'id': 43, 'title': 'Yay'}
        created_item = Item(**data)
        response = await self.client.post(prefix + '/', json=data)
        assert response.status_code == HTTPStatus.CREATED
        assert response.json() == await created_item.get_serialized()

    @mark.parametrize(**api_prefixes)
    async def test_update(self, prefix):
        updated_item = Item(title='Yello')
        response = await self.client.put(f'{prefix}/{pk}', json=updated_item.dict())
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await updated_item.get_serialized()

    @mark.parametrize(**api_prefixes)
    async def test_update_partial(self, prefix):
        data = {'title': 'OK'}
        updated_item = Item(**data)
        response = await self.client.patch(f'{prefix}/{pk}', json=data)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await updated_item.get_serialized()

    @mark.parametrize(**api_prefixes)
    async def test_destroy(self, prefix):
        response = await self.client.delete(f'{prefix}/{pk}')
        assert response.status_code == HTTPStatus.NO_CONTENT
        assert response.text == ''

    ROUTE_QUERY_PARAMS = {'foo': 'one', 'bar': 42}

    @mark.parametrize(
        'path',
        [
            '/unvalidated/listroute',
            f'/unvalidated/{pk}/detail',
            '/unvalidated/listcustom',
            f'/unvalidated/{pk}/detailcustom',
        ],
        ids=['list', 'detail', 'list_named', 'detail_named'],
    )
    async def test_custom_route(self, path):
        invalid_response = await self.client.get(path)
        assert invalid_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        response = await self.client.get(path, query_string=self.ROUTE_QUERY_PARAMS)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == self.ROUTE_QUERY_PARAMS


class TestPaginatedViewSet(WithClient):
    @mark.parametrize(
        'limit,offset', [(Paginator.default_limit, Paginator.default_offset), (10, 3)]
    )
    async def test_default_pagination(self, limit, offset):
        response = await self.client.get(
            '/paginated/', query_string={'limit': limit, 'offset': offset}
        )
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == limit
        assert response_data[limit - 1]['id'] == limit + offset

    @mark.parametrize(
        'limit,offset',
        [
            ('string', 10),
            (20, 'foobar'),
            (Paginator.max_limit + 1, 0),
            (Paginator.max_limit + 100, 200),
        ],
    )
    async def test_invalid_values(self, limit, offset):
        response = await self.client.get(
            '/paginated/', query_string={'limit': limit, 'offset': offset}
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestFieldedViewSet(WithClient):
    request_fields = {'title'}

    @property
    def request_fields_qs(self):
        return {'fields': ','.join(self.request_fields)}

    async def test_list(self):
        response = await self.client.get('/fielded/', query_string=self.request_fields_qs)
        assert response.status_code == HTTPStatus.OK
        for item in response.json():
            for field in self.request_fields:
                assert field in item

    async def test_retrieve(self):
        response = await self.client.get(f'/fielded/{pk}', query_string=self.request_fields_qs)
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        for field in self.request_fields:
            assert field in response_data


async def test_http_exceptions(client):
    detail = 'NOTFOUND'
    header = 'custom-header'
    response = await client.get('/notfound', query_string={'detail': detail, 'header': header})
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json().get('detail') == detail
    assert response.headers['x-custom-header'] == header
