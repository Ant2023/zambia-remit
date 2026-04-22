import uuid


class RequestIdMiddleware:
    header_name = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.header_name) or uuid.uuid4().hex
        request.request_id = request_id[:64]

        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
