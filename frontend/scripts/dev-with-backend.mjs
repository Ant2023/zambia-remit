import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const scriptsDir = path.dirname(__filename);
const frontendDir = path.resolve(scriptsDir, "..");
const backendDir = path.resolve(frontendDir, "..", "backend");
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const BACKEND_START_TIMEOUT_MS = 30000;
const BACKEND_POLL_INTERVAL_MS = 1000;

let startedBackend = null;
let nextDevServer = null;
let shuttingDown = false;

function readEnvFileValue(filePath, key) {
  if (!existsSync(filePath)) {
    return "";
  }

  const lines = readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }

    const currentKey = trimmed.slice(0, separatorIndex).trim();
    if (currentKey !== key) {
      continue;
    }

    let value = trimmed.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    return value;
  }

  return "";
}

function getDjangoApiBaseUrl() {
  return (
    process.env.DJANGO_API_BASE_URL ||
    readEnvFileValue(path.join(frontendDir, ".env.local"), "DJANGO_API_BASE_URL") ||
    readEnvFileValue(path.join(frontendDir, ".env"), "DJANGO_API_BASE_URL") ||
    DEFAULT_API_BASE_URL
  );
}

function getHealthCheckUrl(apiBaseUrl) {
  const normalizedApiBaseUrl = apiBaseUrl.endsWith("/")
    ? apiBaseUrl
    : `${apiBaseUrl}/`;
  return new URL("health/", normalizedApiBaseUrl).toString();
}

function isLocalBackend(apiBaseUrl) {
  const hostname = new URL(apiBaseUrl).hostname;
  return hostname === "127.0.0.1" || hostname === "localhost";
}

async function isBackendHealthy(apiBaseUrl) {
  try {
    const response = await fetch(getHealthCheckUrl(apiBaseUrl), {
      method: "GET",
    });
    return response.ok;
  } catch {
    return false;
  }
}

function getPythonPath() {
  const windowsVenvPython = path.join(backendDir, ".venv", "Scripts", "python.exe");
  if (existsSync(windowsVenvPython)) {
    return windowsVenvPython;
  }

  const unixVenvPython = path.join(backendDir, ".venv", "bin", "python");
  if (existsSync(unixVenvPython)) {
    return unixVenvPython;
  }

  return "python";
}

function wait(delayMs) {
  return new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });
}

function stopChildProcess(childProcess) {
  if (!childProcess || childProcess.exitCode !== null) {
    return;
  }

  if (process.platform === "win32") {
    childProcess.kill();
    return;
  }

  childProcess.kill("SIGINT");
}

function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  stopChildProcess(nextDevServer);
  stopChildProcess(startedBackend);
  process.exit(exitCode);
}

function startBackend(apiBaseUrl) {
  const parsedUrl = new URL(apiBaseUrl);
  const host = parsedUrl.hostname;
  const port =
    parsedUrl.port || (parsedUrl.protocol === "https:" ? "443" : "80");
  const pythonPath = getPythonPath();

  console.log(`[dev] Starting Django backend on ${host}:${port}...`);

  const backendProcess = spawn(
    pythonPath,
    ["manage.py", "runserver", `${host}:${port}`],
    {
      cwd: backendDir,
      stdio: "inherit",
      env: process.env,
    },
  );

  backendProcess.on("exit", (code, signal) => {
    if (shuttingDown) {
      return;
    }

    console.error(
      `[dev] Django backend exited before Next.js finished (code=${code ?? "null"}, signal=${signal ?? "null"}).`,
    );
    shutdown(code ?? 1);
  });

  return backendProcess;
}

async function ensureBackend(apiBaseUrl) {
  if (!(await isBackendHealthy(apiBaseUrl))) {
    startedBackend = startBackend(apiBaseUrl);

    const deadline = Date.now() + BACKEND_START_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (startedBackend.exitCode !== null) {
        throw new Error("The Django backend stopped during startup.");
      }

      if (await isBackendHealthy(apiBaseUrl)) {
        console.log("[dev] Django backend is ready.");
        return;
      }

      await wait(BACKEND_POLL_INTERVAL_MS);
    }

    throw new Error(
      "Timed out waiting for the Django backend health check to respond.",
    );
  }

  console.log("[dev] Django backend is already running.");
}

function startNextDevServer() {
  const npxCommand = process.platform === "win32" ? "npx.cmd" : "npx";
  console.log("[dev] Starting Next.js frontend...");

  nextDevServer = spawn(npxCommand, ["next", "dev", "--webpack"], {
    cwd: frontendDir,
    stdio: "inherit",
    env: process.env,
  });

  nextDevServer.on("exit", (code) => {
    shuttingDown = true;
    stopChildProcess(startedBackend);
    process.exit(code ?? 0);
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function main() {
  const apiBaseUrl = getDjangoApiBaseUrl();

  if (!isLocalBackend(apiBaseUrl)) {
    console.log(`[dev] Using configured Django API: ${apiBaseUrl}`);
    startNextDevServer();
    return;
  }

  await ensureBackend(apiBaseUrl);
  startNextDevServer();
}

main().catch((error) => {
  console.error(`[dev] ${error.message}`);
  shutdown(1);
});
