const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");

const {
  REGISTRY_SOURCES_PATH,
  REGISTRY_LOCK_PATH,
  RELEASE_LOCK_PATH,
  CONFIG_PATH,
  ENABLED_INDEX_PATH,
  ONTOLOGY_DIR,
  ONTOLOGY_VENDOR_DIR,
  EMBEDDINGS_DIR,
  CORE_ONTOLOGY_URL,
  DEFAULT_REGISTRY_URL,
  readJson,
  writeJson,
  warn,
  compact,
} = require("./paths");

// --- Registry sources ---

async function loadRegistrySources() {
  return readJson(REGISTRY_SOURCES_PATH, {
    sources: [{ name: "official", index_url: DEFAULT_REGISTRY_URL, trust_tier: "verified" }]
  });
}

async function saveRegistrySources(data) {
  await writeJson(REGISTRY_SOURCES_PATH, data);
}

// --- Registry lock ---

async function loadRegistryLock() {
  const lock = await readJson(REGISTRY_LOCK_PATH, { packages: {} });
  await syncLocalPackage(lock);
  return lock;
}

async function saveRegistryLock(lock) {
  await writeJson(REGISTRY_LOCK_PATH, lock);
}

// --- Release lock ---

async function loadReleaseLock() {
  return readJson(RELEASE_LOCK_PATH, { mcp: null, core: null });
}

async function saveReleaseLock(lock) {
  await writeJson(RELEASE_LOCK_PATH, lock);
}

// --- Config ---

async function loadConfig() {
  return readJson(CONFIG_PATH, { registry_default: "official" });
}

// --- Local skill discovery ---

function isIgnoredDir(name) {
  return new Set(["system", "vendor", "official", "community"]).has(name);
}

async function walkForOntoskills(dir, found = []) {
  const entries = await fsp.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (path.resolve(target) === path.resolve(ONTOLOGY_VENDOR_DIR)) {
        continue;
      }
      if (path.resolve(path.dirname(target)) === path.resolve(ONTOLOGY_DIR) && isIgnoredDir(entry.name)) {
        continue;
      }
      await walkForOntoskills(target, found);
    } else if (entry.isFile() && entry.name === "ontoskill.ttl") {
      found.push(target);
    }
  }
  return found;
}

async function extractSkillInfo(modulePath) {
  const text = await fsp.readFile(modulePath, "utf-8");
  const idMatch = text.match(/dcterms:identifier\s+"([^"]+)"/);
  const skillId = idMatch ? idMatch[1] : null;
  const relations = new Set();
  for (const match of text.matchAll(/oc:(?:extends|dependsOn|dependsOnSkill)\s+oc:skill_([A-Za-z0-9_-]+)/g)) {
    relations.add(match[1].replace(/_/g, "-"));
  }
  return { skillId, relations };
}

async function syncLocalPackage(lock) {
  const localPaths = await walkForOntoskills(ONTOLOGY_DIR, []);
  const previous = new Map(
    ((lock.packages.local && lock.packages.local.skills) || []).map((skill) => [path.resolve(skill.module_path), skill])
  );
  const skills = [];
  for (const modulePath of localPaths.sort()) {
    if (modulePath.startsWith(path.resolve(ONTOLOGY_VENDOR_DIR))) {
      continue;
    }
    const { skillId } = await extractSkillInfo(modulePath);
    if (!skillId) {
      continue;
    }
    const existing = previous.get(path.resolve(modulePath));
    skills.push({
      skill_id: skillId,
      module_path: path.resolve(modulePath),
      aliases: existing ? existing.aliases : [],
      enabled: existing ? existing.enabled : true,
      default_enabled: true
    });
  }
  if (skills.length) {
    lock.packages.local = {
      package_id: "local",
      version: "workspace",
      trust_tier: "local",
      source: null,
      installed_at: new Date().toISOString(),
      install_root: ONTOLOGY_DIR,
      manifest_path: "",
      skills
    };
  } else {
    delete lock.packages.local;
  }
}

// --- Index generation ---

function ttlImports(importPaths, includeCore = true) {
  const entries = [];
  if (includeCore) {
    entries.push(`<${CORE_ONTOLOGY_URL}>`);
  }
  for (const target of importPaths.sort()) {
    entries.push(`<file://${path.resolve(target)}>`);
  }
  const joined = entries.join(",\n        ");
  return `@prefix dcterms: <http://purl.org/dc/terms/> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n\n<https://ontoskills.sh/ontology> a owl:Ontology ;\n    dcterms:created "${new Date().toISOString()}" ;\n    dcterms:description "Index manifest referencing compiled skill modules" ;\n    dcterms:title "OntoSkills Index" ;\n    owl:imports ${joined} .\n`;
}

async function rebuildIndexes() {
  const lock = await loadRegistryLock();
  const installed = new Set();
  const enabled = new Set();

  for (const pkg of Object.values(lock.packages)) {
    for (const skill of pkg.skills) {
      installed.add(path.resolve(skill.module_path));
      if (skill.enabled) {
        enabled.add(path.resolve(skill.module_path));
      }
    }
  }

  await fsp.writeFile(ENABLED_INDEX_PATH, ttlImports([...enabled].sort()), "utf-8");
  await saveRegistryLock(lock);
}

// --- Embedding merge ---

async function walkForIntentsJson(dir, found = []) {
  const entries = await fsp.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkForIntentsJson(target, found);
    } else if (entry.isFile() && entry.name === "intents.json") {
      found.push(target);
    }
  }
  return found;
}

async function mergeEmbeddings() {
  await fsp.mkdir(EMBEDDINGS_DIR, { recursive: true });

  // Scan all vendor packages for intents.json files
  let intentsFiles = [];
  try {
    intentsFiles = await walkForIntentsJson(ONTOLOGY_VENDOR_DIR);
  } catch (_error) {
    // Vendor dir may not exist yet
  }

  // Build merged intent map (keyed by intent string)
  const intentMap = new Map();
  let model = "sentence-transformers/all-MiniLM-L6-v2";
  let dimension = 384;

  for (const filePath of intentsFiles) {
    try {
      const data = JSON.parse(await fsp.readFile(filePath, "utf-8"));
      if (data.model) model = data.model;
      if (data.dimension) dimension = data.dimension;

      for (const entry of data.intents || []) {
        const key = entry.intent;
        if (!intentMap.has(key)) {
          intentMap.set(key, { intent: key, embedding: entry.embedding, skills: [...(entry.skills || [])] });
        } else {
          // Merge skills (union, deduplicated)
          const existing = intentMap.get(key);
          const mergedSkills = new Set([...existing.skills, ...(entry.skills || [])]);
          existing.skills = [...mergedSkills].sort();
        }
      }
    } catch (_error) {
      // Skip malformed intents.json files
    }
  }

  const merged = {
    model,
    dimension,
    intents: [...intentMap.values()].sort((a, b) => a.intent.localeCompare(b.intent)),
  };

  const mergedPath = path.join(EMBEDDINGS_DIR, "intents.json");
  await writeJson(mergedPath, merged);
}

// --- Remote registry access ---

async function readTextFromRef(ref) {
  if (ref.startsWith("http://") || ref.startsWith("https://")) {
    const response = await fetch(ref, { headers: { "User-Agent": "ontoskills" } });
    if (!response.ok) {
      const { fail } = require("./paths");
      fail(`Failed to fetch ${ref}: ${response.status} ${response.statusText}`);
    }
    return response.text();
  }
  if (ref.startsWith("file://")) {
    return fsp.readFile(new URL(ref), "utf-8");
  }
  return fsp.readFile(ref, "utf-8");
}

async function copyRefToFile(ref, destination) {
  const { fail } = require("./paths");
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  if (ref.startsWith("http://") || ref.startsWith("https://")) {
    const response = await fetch(ref, { headers: { "User-Agent": "ontoskills" } });
    if (!response.ok) {
      fail(`Failed to download ${ref}: ${response.status} ${response.statusText}`);
    }
    const buffer = Buffer.from(await response.arrayBuffer());
    await fsp.writeFile(destination, buffer);
    return;
  }
  if (ref.startsWith("file://")) {
    await fsp.copyFile(new URL(ref), destination);
    return;
  }
  await fsp.copyFile(ref, destination);
}

function resolveChildRef(baseRef, childPath) {
  if (baseRef.startsWith("http://") || baseRef.startsWith("https://") || baseRef.startsWith("file://")) {
    return new URL(childPath, baseRef).toString();
  }
  return path.resolve(path.dirname(baseRef), childPath);
}

async function loadRegistryEntries() {
  const { fail } = require("./paths");
  const sources = await loadRegistrySources();
  const entries = [];
  for (const source of sources.sources) {
    try {
      const index = JSON.parse(await readTextFromRef(source.index_url));
      for (const pkg of index.packages || []) {
        entries.push({ source, package: pkg });
      }
    } catch (error) {
      const { log } = require("./paths");
      log(`registry source skipped: ${source.name} (${error.message || error})`);
    }
  }
  if (!entries.length) {
    fail("No reachable registry sources available");
  }
  return entries;
}

async function loadPackageManifest(entry) {
  const manifestRef = resolveChildRef(entry.source.index_url, entry.package.manifest_path || entry.package.manifest_url);
  const manifest = JSON.parse(await readTextFromRef(manifestRef));
  return { manifestRef, manifest };
}

async function registryPackageVersion(packageId) {
  const entries = await loadRegistryEntries();
  for (const entry of entries) {
    if (entry.package.package_id !== packageId) {
      continue;
    }
    const { manifest } = await loadPackageManifest(entry);
    return manifest.version || null;
  }
  return null;
}

async function findSkillInRegistry(query) {
  const entries = await loadRegistryEntries();
  const matches = [];
  for (const entry of entries) {
    const { manifestRef, manifest } = await loadPackageManifest(entry);
    for (const skill of manifest.skills || []) {
      const qualifiedId = `${manifest.package_id}/${skill.id}`;
      const haystack = [skill.id, qualifiedId, ...(skill.aliases || []), ...(skill.intents || []), skill.description || ""]
        .join(" ")
        .toLowerCase();
      if (!query || haystack.includes(query.toLowerCase())) {
        matches.push({ entry, manifestRef, manifest, skill, qualifiedId });
      }
    }
  }
  return matches;
}

function defaultTrustTier(manifest, entry) {
  return manifest.trust_tier || entry.package.trust_tier || entry.source.trust_tier || "verified";
}

// --- Registry source management ---

async function registryAddSource(name, indexUrl) {
  const { log } = require("./paths");
  const sources = await loadRegistrySources();
  sources.sources = sources.sources.filter((source) => source.name !== name);
  sources.sources.push({ name, index_url: indexUrl, trust_tier: "verified" });
  await saveRegistrySources(sources);
  log(`Configured registry source ${name}`);
}

async function registryList() {
  const { log } = require("./paths");
  const sources = await loadRegistrySources();
  for (const source of sources.sources) {
    log(`${source.name}: ${source.index_url}`);
  }
}

async function searchRegistry(query) {
  const { log } = require("./paths");
  const matches = await findSkillInRegistry(query);
  for (const match of matches) {
    log(`${match.qualifiedId} - ${(match.skill.description || match.manifest.description || "").trim()}`);
  }
}

module.exports = {
  loadRegistrySources,
  saveRegistrySources,
  loadRegistryLock,
  saveRegistryLock,
  loadReleaseLock,
  saveReleaseLock,
  loadConfig,
  syncLocalPackage,
  walkForOntoskills,
  extractSkillInfo,
  rebuildIndexes,
  mergeEmbeddings,
  ttlImports,
  readTextFromRef,
  copyRefToFile,
  resolveChildRef,
  loadRegistryEntries,
  loadPackageManifest,
  registryPackageVersion,
  findSkillInRegistry,
  defaultTrustTier,
  registryAddSource,
  registryList,
  searchRegistry,
};
