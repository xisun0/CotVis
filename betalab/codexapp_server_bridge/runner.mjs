import { Codex } from "@openai/codex-sdk";

function readStdinJson() {
  return new Promise((resolve, reject) => {
    let buffer = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      buffer += chunk;
    });
    process.stdin.on("end", () => {
      try {
        resolve(JSON.parse(buffer || "{}"));
      } catch (error) {
        reject(error);
      }
    });
    process.stdin.on("error", reject);
  });
}

async function main() {
  const payload = await readStdinJson();
  const codex = new Codex();
  const thread = codex.startThread({
    workingDirectory: payload.working_directory || process.cwd(),
    skipGitRepoCheck: true,
    approvalPolicy: "never",
    modelReasoningEffort: payload.model_reasoning_effort || "low",
    webSearchEnabled: false,
  });
  const prompts = Array.isArray(payload.prompts)
    ? payload.prompts
    : [payload.prompt];
  const responses = [];

  for (const prompt of prompts) {
    const turn = await thread.run(prompt);
    responses.push(turn.finalResponse);
  }

  process.stdout.write(
    JSON.stringify({
      ok: true,
      mode: "codex-sdk",
      responses,
    }),
  );
}

main().catch((error) => {
  process.stdout.write(
    JSON.stringify({
      ok: false,
      mode: "codex-sdk",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exit(1);
});
