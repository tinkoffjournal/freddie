# 🕺 Freddie

[![pypi](https://img.shields.io/pypi/v/freddie)](https://pypi.org/project/freddie/)
[![codecov](https://img.shields.io/codecov/c/github/tinkoffjournal/freddie)](https://codecov.io/gh/tinkoffjournal/freddie)

Declarative CRUD viewsets for [FastAPI](https://fastapi.tiangolo.com/) with optional database (Postgres) objects support.
Inspired by [Django REST Framework](https://www.django-rest-framework.org/).

## Rationale

_Freddie_ is aimed to solve some problems of building CRUD domain using FastAPI framework:
1. Most logic is repetitive (run API some action on set of objects described in schema), while functional approach of routes
in FastAPI does not assume easy reuse. That may lead to code duplication or complicated helper functions.
2. API objects (Pydantic models) are validated both on request and response by default—which is good at some point—but a) may be the cause
of performance loss with complex nested structures, b) useless if you store already validated data in persistent state.

## Features

* Predefined class-based viewsets for basic REST API operations
* Schema-based serialization of response objects without running Pydantic model validation (can be optionally turned on)—with
saving auto-generated OpenAPI schema
* Built-in mixins for pagination and GraphQL-alike schema fields retrieval
* Optional tools for working with Postgres database objects in viewsets: use [Peewee](http://peewee-orm.com) for query building
and [aiopg](https://aiopg.readthedocs.io/) for async database operations. Include fine-grained database queries based on
schema and automatic joining/prefetching of related objects

## Installation

Core functionality only (basic viewsets & schema classes):

```bash
pip install freddie
```

Database tools:

```bash
pip install freddie[db]
```

## Usage

Let's create a viewset for managing content posts. It will provide full kit of actions with simple mock data:

```python
from typing import List
from fastapi import FastAPI
from freddie.exceptions import NotFound
from freddie.schemas import Schema
from freddie.viewsets import FieldedViewset, PaginatedListViewset, route, ViewSet

# Schema is just a subset of Pydantic model
class Post(Schema):
    id: int = ...
    title: str = ...
    content: str = ''
    metadata: dict = {}

    class Config:
        # By default, only post ID & title are returned in response.
        # All other allowed fields are requested via ?fields=... query parameter
        default_readable_fields = {'id', 'title'}


post = Post(id=1, title='Freddie', content='Mercury', metadata={'views': 42})

# All action methods (list, retrieve, create, update, destroy) must be implemented in this case.
# Other combinations are also possible, as in DRF (see freddie.viewsets module)
class PostViewSet(
    FieldedViewset,  # Allows retrieving non-default schema fields from query params
    PaginatedListViewset,  # Adds paginator parameter with limit/offset query params
    ViewSet
):
    schema = Post
    list_schema = List[Post]  # custom list response schema

    # Default viewset pagination options are set here
    class Paginator:
        default_limit = 10
        max_limit = 100

    # Async generators are supported as well
    async def list(self, *, paginator, fields, request):
        for i in range(1, paginator.limit + 1):
            item_id = i + paginator.offset
            yield Post(id=item_id, title=f'Freddie #{item_id}')

    # Handler functions may be both sync & async
    def retrieve(self, pk, *, fields, request):
        if pk != post.id:
            raise NotFound
        return post

    async def create(self, body, *, request):
        return body

    async def update(self, pk, body, *, request):
        updated_post = post.copy()
        for key, value in body.dict(exclude_unset=True).items():
            setattr(updated_post, key, value)
        return updated_post

    async def destroy(self, pk, *, request):
        ...

    # Add custom handler on /meta path
    @route(detail=False, summary='List metadata')
    async def meta(self):
        return post.metadata

    # Add custom handler on /{pk}/retrieve_meta path
    @route(detail=True, summary='Retrieve post metadata')
    async def retrieve_meta(self, pk: int):
        return {pk: post.metadata}


app = FastAPI()
# All viewsets are regular FastAPI routers
app.include_router(PostViewSet(), prefix='/posts')
```

Pseudocode extract from viewset OpenAPI schema:

```
paths: {
  /posts/{pk}/meta: {
    get: { tags: ["Post"], summary: "Retrieve post metadata", operationId: "post_retrieve_meta", parameters: [{…}] }
  },
  /posts/meta: {
    get: { tags: ["Post"], summary: "List metadata", operationId: "posts_meta", responses: {…} }
  },
  /posts/{pk}: {
    get: { tags: ["Post"], summary: "Retrieve post", operationId: "get_post", parameters: [{…}, {…}] },
    put: { tags: ["Post"], summary: "Full update post", operationId: "full_update_post", parameters: [{…}] },
    delete: { tags: ["Post"], summary: "Delete post", operationId: "delete_post", parameters: [{…}] },
    patch: { tags: ["Post"], summary: "Update post", operationId: "update_post", parameters: [{…}] }
  },
  /posts/: {
    get: { tags: ["Post"], summary: "List posts", operationId: "list_posts", parameters: [{…}, {…}, {…}] },
    post: { tags: ["Post"], summary: "Create post", operationId: "create_post", requestBody: {…} }
  }
}
```

<details markdown="1">
<summary>Example API requests & responses</summary>

`GET /posts/?limit=3&offset=1 → 200 OK`
```json
[
  {
    "title": "Freddie #2",
    "id": 2
  },
  {
    "title": "Freddie #3",
    "id": 3
  },
  {
    "title": "Freddie #4",
    "id": 4
  }
]
```

`GET /posts/1/?fields=content,metadata → 200 OK`
```json
{
  "title": "Freddie",
  "id": 1,
  "content": "Mercury",
  "metadata": {
    "views": 42
  }
}
```

`POST /posts/ {"id": 2, "title": "Another Freddie"} → 201 CREATED`
```json
{
  "title": "Another Freddie",
  "id": 2,
  "content": "",
  "metadata": {}
}
```

`PATCH /posts/1/ {"content": "Broke free"} → 200 OK`
```json
{
  "title": "Freddie",
  "id": 1,
  "content": "Broke free",
  "metadata": {
    "views": 42
  }
}
```

`DELETE /posts/1/ → 204 NO CONTENT`
</details>

The real power of viewsets reveals in working with database. Let's store our posts in Postgres database and add relations with posts' authors and tags:

```python
from typing import List, Union

from fastapi import FastAPI
from freddie.db import Database, DatabaseManager
from freddie.db.models import (
    CharField, ForeignKeyField, ManyToManyField, Model as _Model, ThroughModel, depends_on, TextField, JSONField
)
from freddie.schemas import Schema
from freddie.viewsets import FieldedViewset, FilterableListViewset, PaginatedListViewset, ModelViewSet
from freddie.viewsets.signals import post_delete, post_save, signal
from pydantic import constr

# Database object stores connection options, while DatabaseManager runs async stuff
db = Database('freddie', user='freddie')
db_manager = DatabaseManager(db)


# Model class is a subset of one used by Peewee ORM
class Model(_Model):
    manager = db_manager

    class Meta:
        database = db


# Let's first declare models for database

class Author(Model):
    nickname = CharField(max_length=127, unique=True)
    first_name = CharField(max_length=127)
    last_name = CharField(max_length=127, default='')


class Tag(Model):
    name = CharField(max_length=127)
    slug = CharField(max_length=127, unique=True)


class Post(Model):
    title = CharField(max_length=255)
    slug = CharField(unique=True, max_length=63)
    category = CharField(max_length=63)
    content = TextField(default='')
    metadata = JSONField(default=dict)
    author = ForeignKeyField(Author, null=True)
    # ManyToManyField is not a real DB column, but interface to object relations.
    # The relations model is defined below
    tags = ManyToManyField(Tag, 'PostTags')

    @property
    # This decorator declares DB fields that must be selected for API object property with the same name
    @depends_on(slug)
    def url(self):
        return f'http://example.com/{self.slug}/'

    @property
    # In this case, the whole related Author object will be joined
    @depends_on(author)
    def author_name(self):
        return f'{self.author.first_name} {self.author.last_name}'


class PostTags(Model, ThroughModel):
    post = ForeignKeyField(Post, on_delete='CASCADE')
    tag = ForeignKeyField(Tag, on_delete='CASCADE')


# And now time for serialization schemas.
# All text fields are defined as constraints with max. length (Pydantic's Field can also be used),
# to avoid database errors on writing longer values.
# If schema value is greater than in DB model (or not set), exception will be raised.

class AuthorSchema(Schema):
    id: int
    nickname: constr(max_length=127)
    first_name: constr(max_length=127)
    last_name: constr(max_length=127) = ''

    class Config:
        default_readable_fields = {'first_name', 'last_name'}


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
    category: constr(max_length=63)
    url: str = None
    content: str = ''
    metadata: dict = {}
    author: AuthorSchema = {}
    author_id: int = None
    tags: List[TagSchema] = []
    tags_ids: List[int] = []

    class Config:
        default_readable_fields = {'id', 'title', 'url'}
        read_only_fields = {'url', 'author', 'tags'}


class PostSchemaOnWrite(PostSchema):
    id: int = None


class PostViewSet(
    FieldedViewset, FilterableListViewset, PaginatedListViewset, ModelViewSet
):
    schema = PostSchema
    write_schema = PostSchemaOnWrite
    model = Post
    # Post can be retrieved by auto ID or unique slug. So we need to set types for FastAPI & DB field to build query.
    # If DB field is not unique, exception will be raised.
    pk_type = Union[int, str]
    secondary_lookup_field = Post.slug

    @signal(post_save)
    async def on_post_save(self, obj, obj_before_update=None, created=False, **params):
        # Do some stuff in background after post is saved (on create or after update).
        # obj is the current post state and obj_before_update is the state before action was run.
        ...

    @signal(post_delete)
    async def on_post_delete(self, obj, **params):
        # Do some stuff in background after post was deleted.
        ...

    class Filter:
        # Enable simple filter by post category
        category: str = None


app = FastAPI()
app.include_router(PostViewSet(), prefix='/posts')

# Open DB connection on app start-up & close on shutdown
@app.on_event('startup')
async def on_startup():
    await db_manager.connect()

@app.on_event('shutdown')
async def on_shutdown():
    await db_manager.close()
```

So what?

* Now all API actions process objects in database
* You can build effective queries that select only necessery fields from DB tables and join related models.
E.g. `GET /posts/1?fields=content&author(nickname)` will retrieve post default readable schema fields (ID, title and URL) + content field + joined author object,
for which we additionaly get non-default nickname field
* Many-to-many relations in list action are prefetched automatically to avoid N+1 problem
* Related objects are added via `*_id` (or `*_ids` for M2M relations) postfixed request body field on create/update
* Post can be found either by ID (`GET /posts/1`) or by its unique slug (`GET /posts/intro`)
* You can filter posts by fields declared in `Filter` config class: `GET /posts?category=longread`
* You can add background tasks in declarative way to run after post was created, updated or deleted

## TBD

- [ ] Mixin class with dependency for sorting in list action
- [ ] More advanced filter operators (not/in/lt/gt etc.)
- [ ] Viewset's default response class schema description & inclusion into API schema (correct API client code generation when using enveloped responses)

## Local development & Testing

```bash
make dev && . venv/bin/activate
make test
```

## Why is it called _Freddie_?

Because the backend of [Tinkoff Journal](https://journal.tinkoff.ru/?utm_source=freddie) content API,
which Freddie was originally developed for, is called _Mercury_.
