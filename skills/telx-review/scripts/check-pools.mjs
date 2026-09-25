#!/usr/bin/env node
// Check src/data/pool.json against the chain with plain JSON-RPC. No dependencies.
//
// Usage: node check-pools.mjs <repo-path> [--all]
//
// For every active pool (every non-hidden pool with --all):
//   - each pool asset address has contract code on the pool's chain
//   - for Uniswap v4 entries with a decimals block, ERC-20 decimals() matches
//     amount0Decimals / amount1Decimals (currency0 is the lower address; native
//     ETH counts as the zero address with 18 decimals)
//   - for legacy entries, pool_address and the active stake addresses have code
//
// Prints a markdown report. Exit code 1 only when an RPC endpoint could not be
// reached, so a mismatch never masks an outage and the reverse.
//
// Override an endpoint with TELX_REVIEW_RPC_ETHEREUM, _POLYGON, or _BASE.

import fs from "node:fs";
import path from "node:path";

const repo = process.argv[2];
const all = process.argv.includes("--all");
if (!repo) {
  console.error("usage: check-pools.mjs <repo-path> [--all]");
  process.exit(2);
}

// Public endpoints, tried in order; the first one that answers is kept for the chain.
const RPC = {
  ethereum: [process.env.TELX_REVIEW_RPC_ETHEREUM, "https://ethereum-rpc.publicnode.com", "https://cloudflare-eth.com", "https://eth.llamarpc.com"],
  polygon: [process.env.TELX_REVIEW_RPC_POLYGON, "https://polygon-bor-rpc.publicnode.com", "https://polygon.llamarpc.com", "https://polygon-rpc.com"],
  base: [process.env.TELX_REVIEW_RPC_BASE, "https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.llamarpc.com"],
};
for (const k of Object.keys(RPC)) RPC[k] = RPC[k].filter(Boolean);
const chosen = new Map();

const isNative = (a) => /^0x0{40}$/i.test(a) || /^0xe{40}$/i.test(a);
const isAddress = (a) => typeof a === "string" && /^0x[0-9a-fA-F]{40}$/.test(a);

async function rpcOnce(url, method, params, attempt = 0) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    if (body.error) throw new Error(body.error.message || JSON.stringify(body.error));
    return body.result;
  } catch (err) {
    if (attempt < 1) {
      await new Promise((r) => setTimeout(r, 500));
      return rpcOnce(url, method, params, attempt + 1);
    }
    throw new Error(`${url} ${method}: ${err.message}`);
  }
}

// `url` is a chain key; the endpoints for that chain are tried in order until one answers.
async function rpc(chain, method, params) {
  if (chosen.has(chain)) return rpcOnce(chosen.get(chain), method, params);
  let last;
  for (const url of RPC[chain]) {
    try {
      const out = await rpcOnce(url, method, params);
      chosen.set(chain, url);
      return out;
    } catch (err) {
      last = err;
    }
  }
  throw last;
}

const cache = new Map();
async function cached(key, fn) {
  if (!cache.has(key)) cache.set(key, fn());
  return cache.get(key);
}
const hasCode = (url, addr) =>
  cached(`code:${url}:${addr.toLowerCase()}`, async () => {
    const code = await rpc(url, "eth_getCode", [addr, "latest"]);
    return Boolean(code && code !== "0x");
  });
const decimals = (url, addr) =>
  cached(`dec:${url}:${addr.toLowerCase()}`, async () => {
    const out = await rpc(url, "eth_call", [{ to: addr, data: "0x313ce567" }, "latest"]);
    if (!out || out === "0x") return null;
    return parseInt(out.slice(-64), 16);
  });

const pools = JSON.parse(fs.readFileSync(path.join(repo, "src/data/pool.json"), "utf8"));
const rows = [];
const skipped = [];
let checks = 0;
let outages = 0;

function note(pool, check, result) {
  rows.push(`| ${pool.id} | ${pool.attributes.name} | ${chainOf(pool)} | ${check} | ${result} |`);
}
function chainOf(pool) {
  return String(pool.attributes.network || pool.attributes.blockchain || "polygon").toLowerCase();
}

for (const pool of pools) {
  const a = pool.attributes;
  if (a.hidden) continue;
  if (!all && !a.active) continue;
  const chain = chainOf(pool);
  const url = RPC[chain] ? chain : null;
  if (!url) {
    note(pool, "chain", `unknown chain "${chain}"`);
    continue;
  }
  // pool.json stores native ETH as an asset named ETH with a null address.
  const NATIVE = "0x0000000000000000000000000000000000000000";
  const assets = (a.pool_assets?.data || [])
    .map((x) => (isAddress(x.attributes?.address) ? x.attributes.address : /^w?eth$/i.test(x.attributes?.name || "") ? NATIVE : null))
    .filter(Boolean);
  try {
    for (const addr of assets) {
      if (isNative(addr)) continue;
      checks++;
      if (!(await hasCode(url, addr))) note(pool, `code at asset ${addr}`, "no contract code on this chain");
    }
    if (a.protocol === "uniswap" && a.decimals && assets.length === 2) {
      const sorted = [...assets].sort((x, y) => {
        if (isNative(x)) return -1;
        if (isNative(y)) return 1;
        return BigInt(x) < BigInt(y) ? -1 : 1;
      });
      const expected = [a.decimals.amount0Decimals, a.decimals.amount1Decimals];
      for (let i = 0; i < 2; i++) {
        checks++;
        const actual = isNative(sorted[i]) ? 18 : await decimals(url, sorted[i]);
        if (actual === null) note(pool, `decimals() of currency${i} ${sorted[i]}`, "call returned no data");
        else if (Number(expected[i]) !== actual)
          note(pool, `decimals of currency${i} ${sorted[i]}`, `pool.json says ${expected[i]}, chain says ${actual}`);
      }
    } else if (a.protocol === "uniswap") {
      skipped.push(`${pool.id} ${a.name}: no decimals block or not two assets`);
    }
    if (a.protocol !== "uniswap") {
      if (isAddress(a.pool_address)) {
        checks++;
        if (!(await hasCode(url, a.pool_address))) note(pool, `code at pool_address ${a.pool_address}`, "no contract code on this chain");
      }
      for (const s of a.stake_addresses?.data || []) {
        const addr = s.attributes?.address;
        if (!isAddress(addr) || !s.attributes?.active) continue;
        checks++;
        if (!(await hasCode(url, addr))) note(pool, `code at active stake address ${addr}`, "no contract code on this chain");
      }
    }
  } catch (err) {
    outages++;
    note(pool, "rpc", `could not check: ${err.message}`);
  }
}

console.log(`# pool.json against the chain\n`);
console.log(`Checked ${checks} facts across ${all ? "all non-hidden" : "active"} pools. ${rows.length} problem${rows.length === 1 ? "" : "s"}, ${outages} RPC failure${outages === 1 ? "" : "s"}.\n`);
if (rows.length) {
  console.log("| id | pool | chain | check | result |\n|---|---|---|---|---|");
  for (const r of rows) console.log(r);
} else {
  console.log("No mismatches.");
}
if (skipped.length) console.log(`\nSkipped:\n${skipped.map((s) => `- ${s}`).join("\n")}`);
process.exit(outages ? 1 : 0);
