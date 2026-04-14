const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const fsp = require("fs");
const os = require("os");
const path = require("path");

// Redirect ONTOSKILLS_HOME to a temp dir for test isolation
const TEST_HOME = path.join(os.tmpdir(), `ontoskills-embed-test-${process.pid}`);
process.env.ONTOSKILLS_HOME = TEST_HOME;

// Clear require cache so paths.js picks up new ONTOSKILLS_HOME
delete require.cache[require.resolve("../lib/paths")];
delete require.cache[require.resolve("../lib/registry")];
delete require.cache[require.resolve("../lib/install")];

const { EMBEDDINGS_DIR, ONTOLOGY_DIR, ONTOLOGY_AUTHOR_DIR, SYSTEM_DIR, ensureLayout, writeJson } = require("../lib/paths");
const { mergeEmbeddings } = require("../lib/registry");

// Helper: create a fake intents.json
function makeIntentsJson(intents, model = "sentence-transformers/all-MiniLM-L6-v2", dimension = 384) {
  return {
    model,
    dimension,
    intents: intents.map(({ intent, skills }) => ({
      intent,
      embedding: new Array(dimension).fill(0.1),
      skills,
    })),
  };
}

// Setup/teardown
test.before(async () => {
  await ensureLayout();
});

test.after(async () => {
  await fs.rm(TEST_HOME, { recursive: true, force: true });
});

// =============================================================================
// mergeEmbeddings() tests
// =============================================================================

test("mergeEmbeddings creates system/embeddings/intents.json from author intents.json files", async () => {
  // Create an author package with an intents.json
  const pkgDir = path.join(ONTOLOGY_AUTHOR_DIR, "test-author", "test-pkg", "my-skill");
  await fs.mkdir(pkgDir, { recursive: true });

  const intentsData = makeIntentsJson([
    { intent: "create_pdf", skills: ["pdf-skill"] },
  ]);
  await writeJson(path.join(pkgDir, "intents.json"), intentsData);

  // Run merge
  await mergeEmbeddings();

  // Check output
  const mergedPath = path.join(EMBEDDINGS_DIR, "intents.json");
  assert.ok(fsp.existsSync(mergedPath), "Merged intents.json should exist");

  const merged = JSON.parse(await fs.readFile(mergedPath, "utf-8"));
  assert.equal(merged.model, "sentence-transformers/all-MiniLM-L6-v2");
  assert.equal(merged.dimension, 384);
  assert.equal(merged.intents.length, 1);
  assert.equal(merged.intents[0].intent, "create_pdf");
  assert.deepEqual(merged.intents[0].skills, ["pdf-skill"]);
});

test("mergeEmbeddings merges duplicate intents across packages", async () => {
  // Package 1
  const pkg1Dir = path.join(ONTOLOGY_AUTHOR_DIR, "author-a", "pkg", "skill-a");
  await fs.mkdir(pkg1Dir, { recursive: true });
  await writeJson(path.join(pkg1Dir, "intents.json"), makeIntentsJson([
    { intent: "send_email", skills: ["gmail"] },
  ]));

  // Package 2 with same intent
  const pkg2Dir = path.join(ONTOLOGY_AUTHOR_DIR, "author-b", "pkg", "skill-b");
  await fs.mkdir(pkg2Dir, { recursive: true });
  await writeJson(path.join(pkg2Dir, "intents.json"), makeIntentsJson([
    { intent: "send_email", skills: ["outlook"] },
  ]));

  await mergeEmbeddings();

  const merged = JSON.parse(await fs.readFile(path.join(EMBEDDINGS_DIR, "intents.json"), "utf-8"));
  const emailIntent = merged.intents.find((i) => i.intent === "send_email");
  assert.ok(emailIntent, "Should find the merged intent");
  // Skills from both packages should be present (sorted, deduplicated)
  assert.ok(emailIntent.skills.includes("gmail"));
  assert.ok(emailIntent.skills.includes("outlook"));
});

test("mergeEmbeddings is idempotent — calling twice produces same result", async () => {
  const mergedPath = path.join(EMBEDDINGS_DIR, "intents.json");

  await mergeEmbeddings();
  const first = await fs.readFile(mergedPath, "utf-8");

  await mergeEmbeddings();
  const second = await fs.readFile(mergedPath, "utf-8");

  assert.equal(first, second, "Repeated merge should produce identical output");
});

test("mergeEmbeddings handles empty author dir — writes empty intents list", async () => {
  // Clean author dir
  await fs.rm(ONTOLOGY_AUTHOR_DIR, { recursive: true, force: true });
  await fs.mkdir(ONTOLOGY_AUTHOR_DIR, { recursive: true });

  await mergeEmbeddings();

  const mergedPath = path.join(EMBEDDINGS_DIR, "intents.json");
  assert.ok(fsp.existsSync(mergedPath));

  const merged = JSON.parse(await fs.readFile(mergedPath, "utf-8"));
  assert.equal(merged.intents.length, 0);
});

test("mergeEmbeddings skips non-intents.json files in author", async () => {
  const pkgDir = path.join(ONTOLOGY_AUTHOR_DIR, "author-x", "pkg", "skill-x");
  await fs.mkdir(pkgDir, { recursive: true });

  // Only a TTL file, no intents.json
  await fs.writeFile(path.join(pkgDir, "ontoskill.ttl"), "fake ttl content");

  await mergeEmbeddings();

  const merged = JSON.parse(await fs.readFile(path.join(EMBEDDINGS_DIR, "intents.json"), "utf-8"));
  assert.equal(merged.intents.length, 0, "No intents from author without intents.json");
});

test("EMBEDDINGS_DIR constant points to system/embeddings", () => {
  assert.equal(EMBEDDINGS_DIR, path.join(SYSTEM_DIR, "embeddings"));
});
