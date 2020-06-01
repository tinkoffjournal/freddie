from http import HTTPStatus
from typing import Any

from fastapi import HTTPException


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


class NotImplementedAction(Problem):
    status_code = HTTPStatus.NOT_IMPLEMENTED


class ServerError(Problem):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
