import { watchFile } from "fs";
import { fork, type ChildProcess } from "child_process";

let child: ChildProcess | null = null;
let intentionalRestart = false;

// Guard against a restart loop when the exit is caused by something a
// restart can never fix — e.g. EADDRINUSE because another process already
// owns the port. server.ts's own unhandledRejection/uncaughtException
// handlers log-and-continue rather than crash, so by the time a bad startup
// error reaches here, the child has usually already logged its own error
// and simply run out of work (exit code 0) rather than crashing (nonzero).
// Retrying that instantly, forever, just re-fails the same way on a tight
// loop. Cap it: a handful of quick attempts (in case the conflicting
// process is mid-shutdown and the port frees up momentarily), then stop and
// say so clearly instead of spinning silently.
const MAX_QUICK_RESTARTS = 3;
const RESTART_WINDOW_MS = 10_000;
const RESTART_DELAY_MS = 1_000;
let recentRestarts: number[] = [];

function start() {
  child = fork("server.ts", {
    execArgv: ["--import", "tsx/esm"],
    stdio: "inherit",
  });

  // Defense in depth: server.ts already guards against unhandledRejection/
  // uncaughtException internally (see its comment), so the child normally
  // stays up even after a failed agent turn. But if it ever DOES die from
  // something those handlers don't catch — or from a startup failure like a
  // taken port — auto-restart here rather than leaving every request
  // 500s/ECONNREFUSEDs until someone notices and manually re-runs
  // `npm run dev`. Bounded by the cap above so a permanent conflict (not a
  // transient one) fails loudly instead of looping forever.
  child.on("exit", (code) => {
    if (intentionalRestart) {
      intentionalRestart = false;
      return;
    }

    const now = Date.now();
    recentRestarts = recentRestarts.filter((t) => now - t < RESTART_WINDOW_MS);
    recentRestarts.push(now);

    if (recentRestarts.length > MAX_QUICK_RESTARTS) {
      console.error(
        `✗ Runtime process exited unexpectedly (code ${code}) ${recentRestarts.length} times in ` +
          `${RESTART_WINDOW_MS / 1000}s — giving up. This usually means the port is already held by ` +
          `another process (check the startup error above for EADDRINUSE) rather than a transient ` +
          `crash. Free the port and restart \`npm run dev\` manually.`,
      );
      return;
    }

    console.error(`⚠ Runtime process exited unexpectedly (code ${code}) — restarting in ${RESTART_DELAY_MS}ms...`);
    setTimeout(start, RESTART_DELAY_MS);
  });
}

start();

watchFile("server.ts", { interval: 500 }, () => {
  console.log("↻ server.ts changed — restarting runtime...");
  intentionalRestart = true;
  child?.kill();
  start();
});
