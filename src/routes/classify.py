"""POST /tasks/classify: file a messy task description under a category."""
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.routing import APIRoute

from src.llm.classifier import classify_text
from src.llm.client import LLMClient, LLMNotConfiguredError, get_llm_client
from src.llm.schema import ClassifyRequest, ClassifyResponse


def validation_error_body(exc: RequestValidationError) -> dict:
    """Name the first offending field, e.g. "text" or "body" for a bad JSON body."""
    error = exc.errors()[0]
    # Keep named parts only: malformed JSON reports ("body", <char position>).
    location = [
        part for part in error.get("loc", ())
        if isinstance(part, str) and part != "body"
    ]

    return {
        "error": "Invalid request data",
        "field": ".".join(location) or "body",
        "message": error.get("msg", "Invalid value"),
    }


class FieldNamingRoute(APIRoute):
    """Returns 400 naming the field for this router only.

    The app-wide handler in main.py stays unchanged for the existing endpoints.
    """

    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                return JSONResponse(status_code=400, content=validation_error_body(exc))

        return handler


router = APIRouter(tags=["Tasks"], route_class=FieldNamingRoute)


@router.post(
    "/tasks/classify",
    response_model=ClassifyResponse,
    responses={
        400: {"description": "Invalid input; the response names the field"},
        503: {"description": "The LLM is not configured"},
    },
)
def classify_task(
    payload: ClassifyRequest,
    response: Response,
    client: Optional[LLMClient] = Depends(get_llm_client),
):
    try:
        result, source = classify_text(payload.text, client)
    except LLMNotConfiguredError as exc:
        return JSONResponse(
            status_code=503, content={"error": f"LLM is not configured: {exc}"}
        )

    if isinstance(result, str):
        # Stage 2 only: the model's raw text. Stage 3 replaces this.
        return PlainTextResponse(result, headers={"X-Classify-Source": source})

    response.headers["X-Classify-Source"] = source
    return result
