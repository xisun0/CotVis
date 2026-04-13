import readline from "node:readline";
import { Codex } from "@openai/codex-sdk";

async function main() {
  const rl = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

  let thread = null;

  for await (const line of rl) {
    if (!line.trim()) {
      continue;
    }

    let payload;
    try {
      payload = JSON.parse(line);
    } catch (error) {
      process.stdout.write(
        `${JSON.stringify({ ok: false, error: `Invalid JSON: ${String(error)}` })}\n`,
      );
      continue;
    }

    const action = payload.action ?? "ask";

    try {
      if (action === "start") {
        const codex = new Codex();
        thread = codex.startThread({
          workingDirectory: payload.working_directory || process.cwd(),
          skipGitRepoCheck: true,
          approvalPolicy: "never",
          modelReasoningEffort: payload.model_reasoning_effort || "low",
          webSearchEnabled: false,
        });
        process.stdout.write(`${JSON.stringify({ ok: true, started: true })}\n`);
        continue;
      }

      if (action === "ask") {
        if (!thread) {
          throw new Error("Session not started. Send action=start first.");
        }
        const turn = await thread.run(payload.prompt ?? "");
        process.stdout.write(
          `${JSON.stringify({ ok: true, response: turn.finalResponse })}\n`,
        );
        continue;
      }

      if (action === "ask_stream") {
        if (!thread) {
          throw new Error("Session not started. Send action=start first.");
        }

        const streamed = await thread.runStreamed(payload.prompt ?? "");
        let finalResponse = "";
        let usage = null;
        const seenTextByItemId = new Map();

        for await (const event of streamed.events) {
          if (event.type === "item.updated" || event.type === "item.completed") {
            if (event.item.type === "agent_message") {
              const previous = seenTextByItemId.get(event.item.id) || "";
              const current = event.item.text || "";
              const delta = current.startsWith(previous)
                ? current.slice(previous.length)
                : current;
              seenTextByItemId.set(event.item.id, current);
              finalResponse = current;
              if (delta) {
                process.stdout.write(
                  `${JSON.stringify({ ok: true, event: "delta", text: delta })}\n`,
                );
              }
            }
          } else if (event.type === "turn.completed") {
            usage = event.usage;
          } else if (event.type === "turn.failed") {
            throw new Error(event.error.message);
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
        }

        process.stdout.write(
          `${JSON.stringify({
            ok: true,
            event: "completed",
            response: finalResponse,
            usage,
          })}\n`,
        );
        continue;
      }

      if (action === "close") {
        process.stdout.write(`${JSON.stringify({ ok: true, closed: true })}\n`);
        rl.close();
        break;
      }

      throw new Error(`Unsupported action: ${action}`);
    } catch (error) {
      process.stdout.write(
        `${JSON.stringify({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        })}\n`,
      );
    }
  }
}

main().catch((error) => {
  process.stdout.write(
    `${JSON.stringify({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    })}\n`,
  );
  process.exit(1);
});
