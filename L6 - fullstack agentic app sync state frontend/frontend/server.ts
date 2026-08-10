import { serve } from "@hono/node-server";
import {
  CopilotRuntime,
  createCopilotEndpoint,
} from "@copilotkit/runtime/v2";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";

// Without this, an unhandled rejection from a failed/aborted agent fetch
// (e.g. the backend model raising mid-stream — seen live with Gemini's
// stricter message-ordering validation, see README Gotchas) crashes this
// entire process via Node's default `unhandledRejection` behavior. Since
// watch-server.ts only restarts its child on a *file change*, not a crash,
// that turns one bad model turn into a total outage (every subsequent
// request 500s/ECONNREFUSEDs) until someone notices and manually restarts
// `npm run dev`. Logging instead of crashing keeps the runtime alive for
// the next request — the failed turn still surfaces as a RUN_ERROR to the
// one request that hit it, which is the correct, contained behavior.
// EADDRINUSE (something else already holds this port) is a startup failure,
// not a single-request failure — there's no server actually running to "keep
// alive" once this happens, so pretending otherwise just hides a clear error
// behind a misleading log line and leaves watch-server.ts restart-looping
// against a port that was never going to free itself. Fail fast and loud
// instead; everything else (a request-scoped failure, once the server is
// genuinely up and listening) is handled by the generic handlers below.
function isAddrInUse(err: unknown): boolean {
  return typeof err === "object" && err !== null && (err as { code?: string }).code === "EADDRINUSE";
}

process.on("unhandledRejection", (reason) => {
  if (isAddrInUse(reason)) {
    console.error(`✗ Port 4006 is already in use by another process — cannot start. ${String(reason)}`);
    process.exit(1);
  }
  console.error("⚠ Unhandled rejection in CopilotKit runtime (ignored, process kept alive):", reason);
});
process.on("uncaughtException", (err) => {
  if (isAddrInUse(err)) {
    console.error(`✗ Port 4006 is already in use by another process — cannot start. ${String(err)}`);
    process.exit(1);
  }
  console.error("⚠ Uncaught exception in CopilotKit runtime (ignored, process kept alive):", err);
});

const langGraphAgent = new LangGraphHttpAgent({
  url: process.env.LANGGRAPH_DEPLOYMENT_URL || "http://localhost:8006",
});

const runtime = new CopilotRuntime({
  agents: {
    default: langGraphAgent,
  },
});

const app = createCopilotEndpoint({
  runtime,
  basePath: "/api/copilotkit",
});

serve({ fetch: app.fetch, port: 4006 }, () => {
  console.log("CopilotKit API server running at http://localhost:4006");
});
