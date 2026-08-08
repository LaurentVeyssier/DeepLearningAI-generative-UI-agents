
import { serve } from "@hono/node-server";
import {
  CopilotRuntime,
  createCopilotEndpoint,
} from "@copilotkit/runtime/v2";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";

const langGraphAgent = new LangGraphHttpAgent({ url: "http://localhost:8004" });

const runtime = new CopilotRuntime({
  agents: { default: langGraphAgent },
  a2ui: {
    injectA2UITool: true,
    // Disable the middleware's progressive (args-streaming) A2UI
    // interception. It matches ANY tool call literally named
    // "render_a2ui" — including ag_ui_adk's internal nested subagent
    // call of that same name (a backend implementation detail, not a
    // real frontend tool). That inner call's schema never asks the
    // model for catalogId (by design — the host owns the catalog), so
    // the progressive builder defaults the missing field to the public
    // basic catalog and renders a bogus "Catalog not found" surface
    // before the correct final result ever arrives. An empty array
    // disables only this progressive path; the middleware still
    // detects and renders valid `a2ui_operations` from the final
    // TOOL_CALL_RESULT of any tool, which is what actually matters.
    a2uiToolNames: [],
  },
});

const app = createCopilotEndpoint({
  runtime,
  basePath: "/api/copilotkit",
});

serve({ fetch: app.fetch, port: 4004 }, () => {
  console.log("\u2713 CopilotKit API server running at http://localhost:4004");
});
