function getDjangoApiBaseUrl() {
  const apiBaseUrl = process.env.DJANGO_API_BASE_URL;

  if (!apiBaseUrl && process.env.NODE_ENV === "production") {
    throw new Error("DJANGO_API_BASE_URL must be set in production.");
  }

  return apiBaseUrl ?? "http://127.0.0.1:8000/api/v1";
}

type RouteContext = {
  params: { path: string[] } | Promise<{ path: string[] }>;
};

async function proxyToDjango(request: Request, context: RouteContext) {
  const params = await context.params;
  const path = params.path.join("/");
  const url = new URL(request.url);
  const targetUrl = `${getDjangoApiBaseUrl()}/${path}/${url.search}`;

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
  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });

  const responseBody = await response.text();
  const responseHeaders = new Headers();
  const responseType = response.headers.get("content-type");

  if (responseType) {
    responseHeaders.set("content-type", responseType);
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
