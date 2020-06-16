import click
import uvicorn

from .app import BaseDBModel, app, db, settings
from .factories import AuthorFactory, PostFactory, TagFactory
from .utils import run_sql


@click.group()
def cli():
    pass


@cli.command()
def create_db():
    db_name = settings.postgres_db
    run_sql(f'DROP DATABASE IF EXISTS {db_name}')
    run_sql(f'CREATE DATABASE {db_name}')
    with db.allow_sync():
        db.create_tables(BaseDBModel.__subclasses__())
        AuthorFactory.create_batch(size=10)
        TagFactory.create_batch(size=10)
        PostFactory.create_batch(size=10)


@cli.command()
def run():
    uvicorn.run(app, port=settings.app_port, access_log=False, use_colors=True)


if __name__ == '__main__':
    cli()
