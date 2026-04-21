function getDjangoApiBaseUrl() {
  const apiBaseUrl = process.env.DJANGO_API_BASE_URL;

  if (!apiBaseUrl && process.env.NODE_ENV === "production") {
    return null;
  }

  return (apiBaseUrl ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
}

type RouteContext = {
  params: { path: string[] } | Promise<{ path: string[] }>;
};

async function proxyToDjango(request: Request, context: RouteContext) {
  const params = await context.params;
  const path = params.path.join("/");
  const url = new URL(request.url);
  const apiBaseUrl = getDjangoApiBaseUrl();

  if (!apiBaseUrl) {
    return Response.json(
      {
        detail: "Frontend API configuration is missing. Set DJANGO_API_BASE_URL.",
      },
      { status: 500 },
    );
  }

  const targetUrl = `${apiBaseUrl}/${path}/${url.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const authorization = request.headers.get("authorization");

  if (contentType) {
    headers.set("content-type", contentType);
  }

  if (authorization) {
    headers.set("authorization", authorization);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let response: Response;

  try {
    response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json(
      {
        detail: "Could not reach the backend API. Please try again.",
      },
      { status: 502 },
    );
  }

  const responseBody = await response.text();
  const responseHeaders = new Headers();
  const responseType = response.headers.get("content-type");

  if (responseType) {
    responseHeaders.set("content-type", responseType);
  }

  const wwwAuthenticate = response.headers.get("www-authenticate");
  if (wwwAuthenticate) {
    responseHeaders.set("www-authenticate", wwwAuthenticate);
  }

  return new Response(responseBody, {
    status: response.status,
    headers: responseHeaders,
  });
}

export async function GET(request: Request, context: RouteContext) {
  return proxyToDjango(request, context);
}

export async function POST(request: Request, context: RouteContext) {
  return proxyToDjango(request, context);
}

export async function PATCH(request: Request, context: RouteContext) {
  return proxyToDjango(request, context);
}

export async function DELETE(request: Request, context: RouteContext) {
  return proxyToDjango(request, context);
}
