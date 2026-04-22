import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


api_logger = logging.getLogger("mbongopay.api")
security_logger = logging.getLogger("mbongopay.security")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    view = context.get("view")
    request_id = getattr(request, "request_id", "")
    path = getattr(request, "path", "")
    method = getattr(request, "method", "")
    view_name = view.__class__.__name__ if view else ""
    user = getattr(request, "user", None)
    user_id = str(getattr(user, "id", "")) if getattr(user, "is_authenticated", False) else ""

    extra = {
        "request_id": request_id,
        "path": path,
        "method": method,
        "view": view_name,
        "user_id": user_id,
    }

    if response is None:
        api_logger.exception("Unhandled API exception", extra=extra)
        return Response(
            {
                "detail": "An unexpected error occurred.",
                "request_id": request_id,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        security_logger.warning(
            "API authorization failure",
            extra={**extra, "status_code": response.status_code},
        )
    elif response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        security_logger.warning(
            "API rate limit exceeded",
            extra={**extra, "status_code": response.status_code},
        )
    elif response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        api_logger.error(
            "API server error response",
            extra={**extra, "status_code": response.status_code},
        )

    return response
