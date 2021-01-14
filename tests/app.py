from enum import Enum
from typing import List, Union

from fastapi import FastAPI, Request
from pydantic import BaseSettings, constr

from freddie import Schema, __version__ as freddie_version
from freddie.db import Database, DatabaseManager
from freddie.db.models import (
    CharField,
    ForeignKeyField,
    JSONField,
    ManyToManyField,
    Model,
    SmallIntegerField,
    TextField,
    ThroughModel,
    depends_on,
)
from freddie.db.queries import fn
from freddie.exceptions import NotFound
from freddie.viewsets import (
    FieldedListViewset,
    FieldedRetrieveViewset,
    FieldedViewset,
    FilterableListViewset,
    ListCreateModelViewSet,
    ListViewset,
    ModelViewSet,
    PaginatedListViewset,
    RetrieveViewset,
    ViewSet,
    route,
)
from freddie.viewsets.signals import post_delete, post_save, signal


class Settings(BaseSettings):
    postgres_db: str = 'freddie'
    postgres_user: str = 'freddie'
    postgres_password: str = ''
    postgres_host: str = 'localhost'
    postgres_port: int = 5432
    app_port: int = 8000
    sql_debug: bool = True


settings = Settings(_env_file='.env')
db = Database(
    database=settings.postgres_db,
    user=settings.postgres_user,
    host=settings.postgres_host,
    port=settings.postgres_port,
)
db_manager = DatabaseManager(db)


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

    async def destroy(self, pk, *, request: Request, **params):
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

    def destroy(self, pk, *, request: Request, **params):
        pass


class Paginated(PaginatedListViewset, ListViewset):
    schema = Item

    async def list(self, *, paginator, **params):
        return Item.paginate(paginator.limit, paginator.offset)


class FieldedItem(Item):
    class Config:
        default_readable_fields = {'id'}


class Fielded(FieldedRetrieveViewset, FieldedListViewset, RetrieveViewset, ListViewset):
    schema = FieldedItem

    async def list(self, *, fields, **params):
        for item in self.schema.paginate(3):
            yield item

    async def retrieve(self, pk, *, fields, **params) -> Item:
        return test_item


class AuthorSchema(Schema):
    id: int
    first_name: constr(max_length=127)
    last_name: constr(max_length=127)
    nickname: constr(max_length=127)

    class Config:
        default_readable_fields = {'id', 'first_name', 'last_name'}


class TagSchema(Schema):
    id: int
    name: constr(max_length=127)
    slug: constr(max_length=127)

    class Config:
        default_readable_fields = {'name'}


class PostSchema(Schema):
    id: int
    title: constr(max_length=255)
    slug: constr(max_length=63)
    urlpath: str = None
    url: str = None
    status: str = None
    content: str = ''
    metadata: dict = {}
    fields_list: list = []
    author: AuthorSchema = {}
    author_id: int = None
    tags: List[TagSchema] = []
    tags_ids: List = []

    class Config:
        read_only_fields = {'url', 'author', 'tags'}


class PostSchemaOnWrite(PostSchema):
    id: int = None


class PostSchemaSimple(Schema):
    id: int
    title: constr(max_length=255)
    slug: constr(max_length=63)


class BaseDBModel(Model):
    manager = db_manager

    class Meta:
        database = db


class Author(BaseDBModel):
    first_name = CharField(max_length=127, null=False)
    last_name = CharField(max_length=127, null=True)
    nickname = CharField(max_length=127, null=False, unique=True)


class Tag(BaseDBModel):
    name = CharField(max_length=127, null=False)
    slug = CharField(max_length=127, null=False, unique=True)


class Post(BaseDBModel):
    title = CharField(max_length=255, null=False)
    slug = CharField(unique=True, max_length=63, null=False)
    content = TextField(default='')
    metadata = JSONField(default=dict)
    author = ForeignKeyField(Author, null=True)
    tags = ManyToManyField(Tag, 'PostTags')

    @classmethod
    @depends_on(metadata)
    async def fields_list(cls):
        for key in cls.fields().keys():
            yield key

    @property
    @depends_on(slug)
    def urlpath(self):
        return f'/{self.slug}/'

    @depends_on(slug)
    def url(self):
        return f'http://example.com/{self.slug}/'

    # Just to test async methods serialization
    @depends_on(author)
    async def status(self):
        return 'OK'


class PostTags(BaseDBModel, ThroughModel):
    tag = ForeignKeyField(Tag, on_delete='CASCADE')
    post = ForeignKeyField(Post, on_delete='CASCADE')


class Log(BaseDBModel):
    action_type = CharField(max_length=63, null=False)
    obj_id = SmallIntegerField(null=False)
    state_before = JSONField(default=dict, null=True)
    state_after = JSONField(default=dict, null=True)

    class ActionType(Enum):
        CREATE = 'create'
        UPDATE = 'update'
        DESTROY = 'destroy'


class TestDatabaseViewSet(
    FieldedViewset, FilterableListViewset, PaginatedListViewset, ModelViewSet
):
    schema = PostSchema
    write_schema = PostSchemaOnWrite
    model = Post
    pk_type = Union[int, str]
    secondary_lookup_field = Post.slug

    @classmethod
    async def log(cls, action_type, obj, obj_before=None):
        state_before = await cls.schema.serialize(obj_before, full=True) if obj_before else None
        state_after = await cls.schema.serialize(obj, full=True) if obj else None
        log_record = {
            'action_type': action_type,
            'obj_id': obj.id if obj else obj_before.id,
            'state_before': state_before,
            'state_after': state_after,
        }
        await Log.manager.execute(Log.insert(**log_record))

    @signal(post_save)
    async def on_post_save(self, obj, obj_before_update=None, created=False, **params):
        action_type = Log.ActionType.CREATE if created else Log.ActionType.UPDATE
        await self.log(action_type, obj, obj_before_update)

    @signal(post_delete)
    async def on_post_delete(self, obj, **params):
        await self.log(Log.ActionType.DESTROY, None, obj_before=obj)

    @route(detail=False, include_in_schema=False)
    async def extra(self):
        query = self.construct_query(
            request={}, fields={}, extra={'total': fn.Count(self.model.id)}
        )
        return await self.model.manager.scalar(query)

    class Paginator:
        max_limit = 100

    class Filter:
        slug: str = None


app = FastAPI(title='🕺 Freddie', version=freddie_version)
app.include_router(TestViewSet(), prefix='/unvalidated')
app.include_router(TestViewSet(validate_response=True), prefix='/validated')
app.include_router(TestViewSetSync(), prefix='/sync')
app.include_router(Paginated(), prefix='/paginated')
app.include_router(Fielded(), prefix='/fielded')
app.include_router(TestDatabaseViewSet(sql_debug=settings.sql_debug), prefix='/post')
app.include_router(
    ModelViewSet(model=Post, schema=PostSchemaSimple, validate_response=True),
    prefix='/post-validated',
)
app.include_router(
    ModelViewSet(model=Post, schema=PostSchemaSimple, model_ordering=(Post.slug,)),
    prefix='/post-ordered',
)
app.include_router(
    ListCreateModelViewSet(model=Post, schema=PostSchema.optional()), prefix='/post-create'
)


@app.api_route('/notfound')
def notfound(detail: str, header: str):
    raise NotFound(detail, headers={'x-custom-header': header})


@app.on_event('startup')
async def on_startup():
    await db_manager.connect()


@app.on_event('shutdown')
async def on_shutdown():
    await db_manager.close()
