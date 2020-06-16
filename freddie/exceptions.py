from contextlib import contextmanager
from http import HTTPStatus
from logging import getLogger
from typing import TYPE_CHECKING, Any, Iterator, NoReturn

import psycopg2.errors as pg_errors
from fastapi import HTTPException
from peewee import DatabaseError as _DatabaseError, IntegrityError
from psycopg2 import Error as _PostgresError

logger = getLogger(__name__)


class Problem(HTTPException):
    status_code: HTTPStatus

    def __init__(self, detail: Any = None, headers: dict = None):
        super().__init__(int(self.status_code), detail=detail, headers=headers)


class BadRequest(Problem):
    status_code = HTTPStatus.BAD_REQUEST


class Unprocessable(Problem):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class NotFound(Problem):
    status_code = HTTPStatus.NOT_FOUND


class ServerError(Problem):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


if TYPE_CHECKING:
    from psycopg2.extensions import Diagnostics

    class PostgresError(_PostgresError):
        diag: Diagnostics

    class DatabaseError(_DatabaseError):
        orig: PostgresError


else:
    DatabaseError = _DatabaseError
    PostgresError = _PostgresError


@contextmanager
def db_errors_handler() -> Iterator:
    try:
        yield
    except Exception as exc:
        dispatch_db_error(exc)


def dispatch_db_error(exc: Exception) -> NoReturn:
    if isinstance(exc, DatabaseError):
        pg_err = exc.orig
        if isinstance(exc, IntegrityError) and isinstance(
            pg_err, (pg_errors.UniqueViolation, pg_errors.ForeignKeyViolation)
        ):
            raise BadRequest(pg_err.diag.message_detail)

    logger.exception('Error during database request')  # pragma: no cover
    raise ServerError('Database error')  # pragma: no cover


__all__ = (
    'BadRequest',
    'Unprocessable',
    'NotFound',
    'ServerError',
    'db_errors_handler',
)
