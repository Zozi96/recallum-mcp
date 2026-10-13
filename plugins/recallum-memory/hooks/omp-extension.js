import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Parent of hooks/, not the extension file. OMP loads this factory; it does not run hooks.json.
const pluginRoot = fileURLToPath(new URL("..", import.meta.url));
const hook = path.join(pluginRoot, "hooks", "recallum_hook.py");

function readContext(stdout) {
  try {
    const text = JSON.parse(String(stdout || ""))?.hookSpecificOutput?.additionalContext;
    return typeof text === "string" ? text : "";
  } catch {
    return "";
  }
}

function runHook(mode, event) {
  const payload = JSON.stringify({
    cwd: event?.cwd || process.cwd(),
    prompt: event?.prompt || "",
  });
  const env = { ...process.env, RECALLUM_OMP: "1" };
  return new Promise((resolve) => {
    let settled = false;
    const finish = (text) => {
      if (settled) return;
      settled = true;
      resolve(text);
    };
    const attempt = (bin, next) => {
      if (settled) return;
      let child;
      try {
        child = spawn(bin, [hook, mode], { env, stdio: ["pipe", "pipe", "ignore"] });
      } catch {
        if (next) next();
        else finish("");
        return;
      }
      let out = "";
      let failed = false;
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        finish("");
      }, 4000);
      child.on("error", (err) => {
        clearTimeout(timer);
        failed = true;
        if (err?.code === "ENOENT" && next) next();
        else finish("");
      });
      child.stdout?.on("data", (chunk) => {
        out += chunk;
      });
      child.on("close", (code) => {
        if (failed || settled) return;
        clearTimeout(timer);
        finish(code === 0 ? readContext(out) : "");
      });
      child.stdin?.end(payload);
    };
    attempt("python3", () => attempt("python"));
  });
}

export default function (pi) {
  // Set on agent_start, not on return, so a retried before_agent_start still injects.
  let sessionInjected = false;
  pi.on("session_start", () => {
    sessionInjected = false;
  });
  pi.on("agent_start", () => {
    sessionInjected = true;
  });
  pi.on("before_agent_start", async (event) => {
    try {
      const parts = [];
      if (!sessionInjected) {
        const session = await runHook("session", event);
        if (session) parts.push(session);
      }
      const hint = await runHook("prompt", event);
      if (hint) parts.push(hint);
      if (!parts.length) return;
      return {
        message: { customType: "recallum", content: parts.join("\n\n"), display: false },
      };
    } catch {
      return;
    }
  });
}
