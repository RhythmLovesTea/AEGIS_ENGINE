"""AEGIS-Marine: RFC 7807 Problem Details & Domain Exception Handling."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from scripts.lint_banned_terms import BANNED_RULES

logger = logging.getLogger(__name__)

RFC7807_MEDIA_TYPE = "application/problem+json"


def assert_no_banned_terms(text: str, context_label: str = "text") -> None:
    """Enforces Constitutional Rule 6: zero banned determination terms in error copy."""
    import re

    for rule in BANNED_RULES:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            raise ValueError(
                f"Rule 6 Violation: Detected banned term '{rule['name']}' in {context_label}: {text}"
            )


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details representation."""

    type: str = Field(
        default="urn:aegis:error:unknown",
        description="URI reference identifying problem type",
    )
    title: str = Field(..., description="Short human-readable summary of problem")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation of this specific error")
    instance: str | None = Field(
        default=None, description="URI reference identifying the specific occurrence"
    )
    invalid_params: list[dict[str, Any]] | None = Field(
        default=None, description="Validation parameter errors"
    )


class AegisException(Exception):
    """Base exception for AEGIS-Marine domain errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        title: str | None = None,
        problem_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        assert_no_banned_terms(detail, context_label="Domain Exception Detail")
        self.detail = detail
        self.status_code = status_code
        self.title = title or "Internal Server Error"
        self.problem_type = problem_type or "urn:aegis:error:internal_server_error"
        self.headers = headers
        super().__init__(detail)


class AuthenticationError(AegisException):
    """Raised when authentication credentials are missing or invalid (401)."""

    def __init__(
        self, detail: str = "Authentication credentials were not provided or are invalid."
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            problem_type="urn:aegis:error:authentication_failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(AegisException):
    """Raised when authenticated user lacks permissions for an operation (403)."""

    def __init__(self, detail: str = "Insufficient permissions for this operation.") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            title="Forbidden",
            problem_type="urn:aegis:error:forbidden",
        )


class NotFoundError(AegisException):
    """Raised when a requested resource is not found (404)."""

    def __init__(self, detail: str = "Resource not found.") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Resource Not Found",
            problem_type="urn:aegis:error:not_found",
        )


class RuleViolationError(AegisException):
    """Raised when a constitutional or scientific business rule is violated (400)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Rule Violation",
            problem_type="urn:aegis:error:rule_violation",
        )


def _build_problem_response(
    status_code: int,
    title: str,
    detail: str,
    problem_type: str,
    request: Request | None = None,
    invalid_params: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Builds a compliant RFC 7807 JSONResponse."""
    instance = request.url.path if request else f"urn:aegis:incident:{uuid.uuid4()}"

    # Verify no banned terms exist in title or detail
    assert_no_banned_terms(title, context_label="Error Title")
    assert_no_banned_terms(detail, context_label="Error Detail")

    problem = ProblemDetail(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        invalid_params=invalid_params,
    )

    resp_headers = headers.copy() if headers else {}
    resp_headers["Content-Type"] = RFC7807_MEDIA_TYPE

    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type=RFC7807_MEDIA_TYPE,
        headers=resp_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global RFC 7807 problem details exception handlers on FastAPI."""

    @app.exception_handler(AegisException)
    async def handle_aegis_exception(request: Request, exc: AegisException) -> JSONResponse:
        logger.warning("Domain exception caught: %s", exc.detail)
        return _build_problem_response(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            problem_type=exc.problem_type,
            request=request,
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        title_map = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
            409: "Conflict",
            422: "Unprocessable Entity",
            500: "Internal Server Error",
        }
        type_slug = title_map.get(exc.status_code, "error").lower().replace(" ", "_")
        problem_type = f"urn:aegis:error:{type_slug}"
        title = title_map.get(exc.status_code, "HTTP Error")
        detail = str(exc.detail) if exc.detail else title

        return _build_problem_response(
            status_code=exc.status_code,
            title=title,
            detail=detail,
            problem_type=problem_type,
            request=request,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        invalid_params = []
        for error in exc.errors():
            loc = " -> ".join(str(item) for item in error.get("loc", []))
            invalid_params.append(
                {
                    "name": loc,
                    "reason": error.get("msg", "Invalid parameter"),
                    "type": error.get("type", "value_error"),
                }
            )

        return _build_problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation Error",
            detail="The request body or query parameters failed schema validation.",
            problem_type="urn:aegis:error:validation_error",
            request=request,
            invalid_params=invalid_params,
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("ValueError caught: %s", str(exc))
        detail = str(exc)
        return _build_problem_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Bad Request",
            detail=detail,
            problem_type="urn:aegis:error:bad_request",
            request=request,
        )

    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
        incident_id = str(uuid.uuid4())
        logger.error("Unhandled server exception [%s]: %s", incident_id, exc, exc_info=True)
        return _build_problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail=f"An unexpected internal error occurred (Reference ID: {incident_id}).",
            problem_type="urn:aegis:error:internal_server_error",
            request=request,
        )
