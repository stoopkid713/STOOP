#!/usr/bin/env node
// create-issues.mjs — idempotent migration of punchlist items into GitHub issues + the STOOP board.
//
// Reads ./issues.json, creates each as an issue on stoopkid713/STOOP with labels, adds it to the
// project, and sets Priority + Status fields. Idempotent: each issue body carries a
// `<!-- migrated:KEY -->` marker; a re-run skips any KEY already present, so a partial run resumes
// cleanly with no duplicates.
//
// Usage:  node tools/board-migration/create-issues.mjs [projectNumber=1]
// Requires: gh logged in as stoopkid713 with the `project` scope.

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const PROJECT = process.argv[2] || "1";
const OWNER = "stoopkid713";
const REPO = "stoopkid713/STOOP";

const gh = (args) => execFileSync("gh", args, { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
const ghJSON = (args) => JSON.parse(gh(args));

// Resolve project node id + field/option ids once.
const projectId = ghJSON(["project", "view", PROJECT, "--owner", OWNER, "--format", "json"]).id;
const fieldList = ghJSON(["project", "field-list", PROJECT, "--owner", OWNER, "--format", "json"]);
const field = (name) => {
  const f = fieldList.fields.find((x) => x.name === name);
  if (!f) throw new Error(`field not found: ${name}`);
  return f;
};
const statusField = field("Status");
const priorityField = field("Priority");
const optId = (f, name) => {
  const o = f.options.find((x) => x.name === name);
  if (!o) throw new Error(`no option "${name}" on field ${f.name}`);
  return o.id;
};

// Build the set of already-migrated markers from existing issue bodies (one list call, no fragile search).
const existing = ghJSON(["issue", "list", "--repo", REPO, "--state", "all", "--limit", "400", "--json", "body"]);
const seen = new Set();
for (const i of existing) {
  for (const m of (i.body || "").match(/<!-- migrated:[\w-]+ -->/g) || []) seen.add(m);
}

const issues = JSON.parse(readFileSync(new URL("./issues.json", import.meta.url), "utf8"));

let created = 0, skipped = 0;
for (const it of issues) {
  const marker = `<!-- migrated:${it.key} -->`;
  if (seen.has(marker)) { console.log("skip:", it.key); skipped++; continue; }

  const body = `${it.body}\n\n${marker}`;
  const url = gh(["issue", "create", "--repo", REPO, "--title", it.title, "--body", body,
    ...it.labels.flatMap((l) => ["--label", l])]).trim();

  const item = ghJSON(["project", "item-add", PROJECT, "--owner", OWNER, "--url", url, "--format", "json"]);
  gh(["project", "item-edit", "--id", item.id, "--project-id", projectId,
    "--field-id", priorityField.id, "--single-select-option-id", optId(priorityField, it.priority)]);
  gh(["project", "item-edit", "--id", item.id, "--project-id", projectId,
    "--field-id", statusField.id, "--single-select-option-id", optId(statusField, it.status)]);

  console.log("created:", it.key, "->", url);
  created++;
}
console.log(`\ndone: ${created} created, ${skipped} skipped`);
