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
    console.error(
      "Django API proxy missing env var env_var=DJANGO_API_BASE_URL path=%s",
      path,
    );
    return Response.json(
      {
        detail: "Frontend API configuration is missing. Set DJANGO_API_BASE_URL.",
      },
      { status: 500 },
    );
  }

  const targetUrl = `${apiBaseUrl}/${path}/${url.search}`;
  const shouldLogFxProxy = path === "quotes/rate";

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
    if (shouldLogFxProxy) {
      console.error(
        "Django API proxy request failed request_url=%s response_status= response_body=Could not reach backend",
        targetUrl,
      );
    }
    return Response.json(
      {
        detail: "Could not reach the backend API. Please try again.",
      },
      { status: 502 },
    );
  }

  const responseBody = await response.text();
  if (shouldLogFxProxy) {
    console.info(
      "Django API proxy response request_url=%s response_status=%s response_body=%s",
      targetUrl,
      response.status,
      responseBody,
    );
  }
  const responseHeaders = new Headers();
  const responseType = response.headers.get("content-type");

  if (responseType) {
    responseHeaders.set("content-type", responseType);
  }

  const wwwAuthenticate = response.headers.get("www-authenticate");
  if (wwwAuthenticate) {
    responseHeaders.set("www-authenticate", wwwAuthenticate);
  }

  if (response.status === 204 || response.status === 304) {
    return new Response(null, {
      status: response.status,
      headers: responseHeaders,
    });
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
