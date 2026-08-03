import type { Command } from "commander";
import pc from "picocolors";
import { createPublicKey, verify as cryptoVerify, createHash } from "node:crypto";
import { addCommonClientOptions, handleCommandError, resolveCommandContext } from "./common.js";

interface AttestationFetchResponse {
  activityId: string;
  projectId: string;
  algorithm: string;
  signedPayload: string;
  payloadHash: string;
  signature: string;
  signingKeyVersion: number;
  createdAt: string;
  publicKey: string;
}

interface PublicKeyResponse {
  projectId: string;
  algorithm: string;
  publicKey: string;
  keyVersion: number;
}

export function registerAttestCommands(program: Command): void {
  const attest = program.command("attest").description("Verify GitMesh activity-log attestations");

  // ── verify <attestation-url-or-flags> ─────────────────────────────────
  const verify = attest
    .command("verify")
    .description("Verify a GitMesh attestation. Accepts either a full attestation URL as positional argument, or --activity-id + --project-id + --api-base.")
    .argument("[attestation-url]", "Full URL to GET, e.g. http://localhost:3100/api/projects/<id>/attestations/<activityId>")
    .option("--activity-id <id>", "Activity ID (used when no positional URL given)")
    .option("--strict", "Exit non-zero if the attestation is missing or pending", false);

  addCommonClientOptions(verify, { includeProject: true });

  verify.action(async (urlArg: string | undefined, opts) => {
    try {
      const fetchResult = await fetchAttestation(urlArg, opts);
      if (!fetchResult) {
        const msg = "No attestation found for this activity.";
        if (opts.strict) {
          console.error(pc.red(`  ✗  ${msg}`));
          process.exit(2);
        }
        console.log(pc.yellow(`  ⚠  ${msg}`));
        return;
      }
      printAndVerify(fetchResult);
    } catch (err) {
      handleCommandError(err);
    }
  });

  // ── fetch-public-key ──────────────────────────────────────────────────
  const pkCmd = attest
    .command("fetch-public-key")
    .description("Fetch a project's attestation public key (PEM SPKI). Useful for pinning in CI scripts.");

  addCommonClientOptions(pkCmd, { includeProject: true });

  pkCmd.action(async (opts) => {
    try {
      const ctx = resolveCommandContext(opts, { requireProject: true });
      const result = await ctx.api.get<PublicKeyResponse>(
        `/api/projects/${ctx.projectId}/attestations/public-key`,
      );
      if (!result) {
        console.error(pc.red("  ✗  no public key returned (project not yet provisioned)"));
        process.exit(1);
      }
      if (opts.json) {
        console.log(JSON.stringify(result, null, 2));
        return;
      }
      console.log(pc.bold(`Project ${result.projectId} (key v${result.keyVersion}, ${result.algorithm})`));
      console.log(result.publicKey);
    } catch (err) {
      handleCommandError(err);
    }
  });
}

async function fetchAttestation(
  urlArg: string | undefined,
  opts: { activityId?: string; apiBase?: string; apiKey?: string; profile?: string; context?: string; projectId?: string },
): Promise<AttestationFetchResponse | null> {
  if (urlArg && urlArg.trim()) {
    const url = urlArg.trim();
    const response = await fetch(url, { headers: { accept: "application/json" } });
    if (response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`Fetch failed: ${response.status} ${response.statusText}`);
    }
    const json = (await response.json()) as AttestationFetchResponse;
    return json;
  }

  if (!opts.activityId) {
    throw new Error(
      "Either provide a full URL as positional arg or pass --activity-id (with --project-id and --api-base).",
    );
  }

  const ctx = resolveCommandContext(opts, { requireProject: true });
  const result = await ctx.api.get<AttestationFetchResponse>(
    `/api/projects/${ctx.projectId}/attestations/${opts.activityId}`,
    { ignoreNotFound: true },
  );
  return result ?? null;
}

function printAndVerify(att: AttestationFetchResponse): void {
  // 1. recompute payload hash
  const expectedHash = createHash("sha256").update(att.signedPayload, "utf8").digest("hex");
  const hashMatch = expectedHash === att.payloadHash;

  // 2. verify ed25519 signature
  let signatureValid = false;
  try {
    const pubKey = createPublicKey({ key: att.publicKey, format: "pem" });
    const sigBuf = Buffer.from(att.signature, "base64url");
    const msgBuf = Buffer.from(att.signedPayload, "utf8");
    signatureValid = cryptoVerify(null, msgBuf, pubKey, sigBuf);
  } catch (err) {
    signatureValid = false;
  }

  console.log(pc.bold(`Activity: ${att.activityId}`));
  console.log(pc.dim(`Project:  ${att.projectId}`));
  console.log(pc.dim(`Signed:   ${att.createdAt}`));
  console.log(pc.dim(`Algorithm: ${att.algorithm}, key v${att.signingKeyVersion}`));
  console.log("");
  console.log(pc.bold("Canonical payload:"));
  try {
    console.log(JSON.stringify(JSON.parse(att.signedPayload), null, 2));
  } catch {
    console.log(att.signedPayload);
  }
  console.log("");

  if (hashMatch && signatureValid) {
    console.log(pc.green(`  ✓  PASS - payload hash matches and signature verifies against the project key`));
    process.exitCode = 0;
  } else {
    if (!hashMatch) {
      console.log(pc.red(`  ✗  FAIL - sha256(signedPayload) != payloadHash`));
      console.log(pc.dim(`    expected: ${expectedHash}`));
      console.log(pc.dim(`    received: ${att.payloadHash}`));
    }
    if (!signatureValid) {
      console.log(pc.red(`  ✗  FAIL - signature did not verify against the project's public key`));
    }
    process.exitCode = 1;
  }
}
