#!/usr/bin/env node

const fs = require("fs");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const HOME_ROOT = process.env.ONTOSKILLS_HOME || process.env.ONTOSKILL_HOME || path.join(os.homedir(), ".ontoskills");
const BIN_DIR = path.join(HOME_ROOT, "bin");
const ONTOLOGY_DIR = path.join(HOME_ROOT, "ontologies");
const ONTOLOGY_VENDOR_DIR = path.join(ONTOLOGY_DIR, "vendor");
const SKILLS_DIR = path.join(HOME_ROOT, "skills");
const SKILLS_VENDOR_DIR = path.join(SKILLS_DIR, "vendor");
const STATE_DIR = path.join(HOME_ROOT, "state");
const CORE_DIR = path.join(HOME_ROOT, "core");
const CACHE_DIR = path.join(STATE_DIR, "cache");
const SYSTEM_DIR = path.join(ONTOLOGY_DIR, "system");

const REGISTRY_SOURCES_PATH = path.join(STATE_DIR, "registry.sources.json");
const REGISTRY_LOCK_PATH = path.join(STATE_DIR, "registry.lock.json");
const RELEASE_LOCK_PATH = path.join(STATE_DIR, "release.lock.json");
const CONFIG_PATH = path.join(STATE_DIR, "config.json");
const INSTALLED_INDEX_PATH = path.join(ONTOLOGY_DIR, "index.installed.ttl");
const ENABLED_INDEX_PATH = path.join(SYSTEM_DIR, "index.enabled.ttl");
const CORE_ONTOLOGY_PATH = path.join(ONTOLOGY_DIR, "core.ttl");
const CORE_ONTOLOGY_URL = "https://ontoskills.sh/ontology/core.ttl";

const DEFAULT_REPOSITORY =
  process.env.ONTOSKILLS_RELEASE_REPO ||
  process.env.ONTOSKILL_RELEASE_REPO ||
  "mareasw/ontoskills";
const DEFAULT_REGISTRY_URL =
  process.env.ONTOSKILLS_REGISTRY_URL ||
  process.env.ONTOSKILL_REGISTRY_URL ||
  "https://raw.githubusercontent.com/mareasw/ontostore/main/index.json";

const MCP_SERVER_NAME = "ontomcp";
const MCP_CLIENT_FLAGS = new Map([
  ["--codex", "codex"],
  ["--claude", "claude"],
  ["--qwen", "qwen"],
  ["--cursor", "cursor"],
  ["--vscode", "vscode"],
  ["--windsurf", "windsurf"],
  ["--antigravity", "antigravity"],
  ["--opencode", "opencode"]
]);
const MCP_CLIENT_ORDER = ["codex", "claude", "qwen", "cursor", "vscode", "windsurf", "antigravity", "opencode"];

function log(message) {
  process.stdout.write(`${message}\n`);
}

function fail(message, code = 1) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function warn(message) {
  process.stderr.write(`${message}\n`);
}

async function ensureLayout() {
  for (const target of [BIN_DIR, ONTOLOGY_DIR, ONTOLOGY_VENDOR_DIR, SKILLS_DIR, SKILLS_VENDOR_DIR, STATE_DIR, CORE_DIR, CACHE_DIR, SYSTEM_DIR]) {
    await fsp.mkdir(target, { recursive: true });
  }
}

async function readJson(filePath, fallback) {
  try {
    const raw = await fsp.readFile(filePath, "utf-8");
    return JSON.parse(raw);
  } catch (error) {
    if (fallback !== undefined) {
      return fallback;
    }
    throw error;
  }
}

async function writeJson(filePath, value) {
  await fsp.mkdir(path.dirname(filePath), { recursive: true });
  await fsp.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

function commandExists(command) {
  const result = spawnSync(command, ["--help"], { stdio: "ignore" });
  return result.status === 0;
}

function runCommandResult(command, args, options = {}) {
  return spawnSync(command, args, { stdio: "pipe", encoding: "utf-8", ...options });
}

function compact(value) {
  return value.filter(Boolean);
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

async function readJsonFile(filePath, fallback = {}) {
  try {
    const raw = await fsp.readFile(filePath, "utf-8");
    return raw.trim() ? JSON.parse(raw) : fallback;
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return fallback;
    }
    throw error;
  }
}

async function writeManagedJson(filePath, mutator) {
  const current = await readJsonFile(filePath, {});
  const next = mutator(current) || current;
  await writeJson(filePath, next);
}

function parseMcpInstallArgs(args) {
  const targets = new Set();
  let scope = "global";
  let explicitScope = false;

  for (const arg of args) {
    if (arg === "--global") {
      if (explicitScope && scope !== "global") {
        fail("Use either --global or --project, not both");
      }
      scope = "global";
      explicitScope = true;
      continue;
    }
    if (arg === "--project") {
      if (explicitScope && scope !== "project") {
        fail("Use either --global or --project, not both");
      }
      scope = "project";
      explicitScope = true;
      continue;
    }
    if (arg === "--all-clients") {
      for (const target of MCP_CLIENT_ORDER) {
        targets.add(target);
      }
      continue;
    }
    if (MCP_CLIENT_FLAGS.has(arg)) {
      targets.add(MCP_CLIENT_FLAGS.get(arg));
      continue;
    }
    if (MCP_CLIENT_ORDER.includes(arg)) {
      targets.add(arg);
      continue;
    }
    fail(`Unknown install mcp option: ${arg}`);
  }

  return { scope, targets: [...targets] };
}

function buildStdIoServerSpec() {
  return {
    name: MCP_SERVER_NAME,
    command: path.join(BIN_DIR, "ontomcp"),
    args: []
  };
}

function cursorConfigPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, ".cursor", "mcp.json") : path.join(os.homedir(), ".cursor", "mcp.json");
}

function vscodeProjectConfigPath(cwd = process.cwd()) {
  return path.join(cwd, ".vscode", "mcp.json");
}

function windsurfConfigPath() {
  return path.join(os.homedir(), ".codeium", "windsurf", "mcp_config.json");
}

function opencodeConfigPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, "opencode.json") : path.join(os.homedir(), ".config", "opencode", "opencode.json");
}

function qwenSettingsPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, ".qwen", "settings.json") : path.join(os.homedir(), ".qwen", "settings.json");
}

function antigravityCandidatePaths() {
  return compact([
    process.env.ANTIGRAVITY_MCP_CONFIG,
    path.join(os.homedir(), ".antigravity", "mcp_config.json"),
    path.join(os.homedir(), ".config", "antigravity", "mcp_config.json")
  ]);
}

async function configureMcpServersJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    const mcpServers = { ...(current.mcpServers || {}) };
    mcpServers[serverSpec.name] = {
      command: serverSpec.command,
      args: ensureArray(serverSpec.args)
    };
    next.mcpServers = mcpServers;
    return next;
  });
}

async function configureOpenCodeJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    if (!next.$schema) {
      next.$schema = "https://opencode.ai/config.json";
    }
    const mcp = { ...(current.mcp || {}) };
    mcp[serverSpec.name] = {
      type: "local",
      command: [serverSpec.command, ...ensureArray(serverSpec.args)],
      enabled: true
    };
    next.mcp = mcp;
    return next;
  });
}

async function configureQwenJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    const mcpServers = { ...(current.mcpServers || {}) };
    mcpServers[serverSpec.name] = {
      command: serverSpec.command,
      args: ensureArray(serverSpec.args)
    };
    next.mcpServers = mcpServers;
    return next;
  });
}

function formatCommand(command, args = []) {
  return [command, ...args]
    .map((part) => (/[\s"'\\]/.test(part) ? JSON.stringify(part) : part))
    .join(" ");
}

function removeIfConfigured(command, args) {
  const result = runCommandResult(command, args);
  return result.status === 0;
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "imported";
}

async function loadRegistrySources() {
  return readJson(REGISTRY_SOURCES_PATH, {
    sources: [{ name: "official", index_url: DEFAULT_REGISTRY_URL, trust_tier: "verified" }]
  });
}

async function saveRegistrySources(data) {
  await writeJson(REGISTRY_SOURCES_PATH, data);
}

async function loadRegistryLock() {
  const lock = await readJson(REGISTRY_LOCK_PATH, { packages: {} });
  await syncLocalPackage(lock);
  return lock;
}

async function saveRegistryLock(lock) {
  await writeJson(REGISTRY_LOCK_PATH, lock);
}

async function loadReleaseLock() {
  return readJson(RELEASE_LOCK_PATH, { mcp: null, core: null });
}

async function saveReleaseLock(lock) {
  await writeJson(RELEASE_LOCK_PATH, lock);
}

async function loadConfig() {
  return readJson(CONFIG_PATH, { registry_default: "official" });
}

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
  for (const match of text.matchAll(/oc:(?:extends|dependsOn)\s+oc:skill_([A-Za-z0-9_-]+)/g)) {
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

  await fsp.writeFile(INSTALLED_INDEX_PATH, ttlImports([...installed].sort()), "utf-8");
  await fsp.writeFile(ENABLED_INDEX_PATH, ttlImports([...enabled].sort()), "utf-8");
  await saveRegistryLock(lock);
}

async function readTextFromRef(ref) {
  if (ref.startsWith("http://") || ref.startsWith("https://")) {
    const response = await fetch(ref, { headers: { "User-Agent": "ontoskills" } });
    if (!response.ok) {
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
  const sources = await loadRegistrySources();
  const entries = [];
  for (const source of sources.sources) {
    try {
      const index = JSON.parse(await readTextFromRef(source.index_url));
      for (const pkg of index.packages || []) {
        entries.push({ source, package: pkg });
      }
    } catch (error) {
      log(`registry source skipped: ${source.name} (${error.message || error})`);
    }
  }
  if (!entries.length) {
    fail("No reachable registry sources available");
  }
  return entries;
}

async function loadPackageManifest(entry) {
  const manifestRef = resolveChildRef(entry.source.index_url, entry.package.manifest_url);
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

async function installSkill(qualifiedId) {
  if (!qualifiedId.includes("/")) {
    fail("Install expects a qualified skill id like marea/office/xlsx");
  }
  const [packageId, skillId] = qualifiedId.split("/", 2);
  const matches = await findSkillInRegistry(qualifiedId);
  const selected = matches.find((match) => match.manifest.package_id === packageId && match.skill.id === skillId);
  if (!selected) {
    fail(`Skill not found in configured registries: ${qualifiedId}`);
  }

  const { manifestRef, manifest, entry } = selected;
  const skillMap = new Map((manifest.skills || []).map((skill) => [skill.id, skill]));
  const queue = [skillId];
  const selectedIds = new Set();
  while (queue.length) {
    const current = queue.shift();
    if (selectedIds.has(current)) {
      continue;
    }
    selectedIds.add(current);
    const currentSkill = skillMap.get(current);
    for (const dep of currentSkill?.depends_on_skills || []) {
      if (skillMap.has(dep)) {
        queue.push(dep);
      }
    }
  }

  const installRoot = path.join(ONTOLOGY_VENDOR_DIR, manifest.package_id);
  await fsp.mkdir(installRoot, { recursive: true });

  for (const skill of manifest.skills || []) {
    if (!selectedIds.has(skill.id)) {
      continue;
    }
    const sourceRef = resolveChildRef(manifestRef, skill.path);
    await copyRefToFile(sourceRef, path.join(installRoot, skill.path));
  }
  await fsp.writeFile(path.join(installRoot, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");

  const lock = await loadRegistryLock();
  const existing = lock.packages[manifest.package_id];
  const existingSkillMap = new Map(((existing && existing.skills) || []).map((skill) => [skill.skill_id, skill]));
  lock.packages[manifest.package_id] = {
    package_id: manifest.package_id,
    version: manifest.version,
    trust_tier: defaultTrustTier(manifest, entry),
    source: manifest.source || manifestRef,
    installed_at: new Date().toISOString(),
    install_root: installRoot,
    manifest_path: path.join(installRoot, "package.json"),
    skills: [...selectedIds]
      .sort()
      .map((id) => {
        const skill = skillMap.get(id);
        const previous = existingSkillMap.get(id);
        return {
          skill_id: id,
          module_path: path.resolve(path.join(installRoot, skill.path)),
          aliases: skill.aliases || [],
          enabled: previous ? previous.enabled : true,
          default_enabled: true
        };
      })
  };
  await saveRegistryLock(lock);
  await rebuildIndexes();
  log(`Installed skill ${qualifiedId}`);
}

async function enableSkill(qualifiedId, enabled) {
  const [packageId, skillId] = qualifiedId.includes("/") ? qualifiedId.split("/", 2) : ["local", qualifiedId];
  const lock = await loadRegistryLock();
  const pkg = lock.packages[packageId];
  if (!pkg) {
    fail(`Package not installed: ${packageId}`);
  }
  const skillMap = new Map(pkg.skills.map((skill) => [skill.skill_id, skill]));
  const queue = [skillId];
  const visited = new Set();
  while (queue.length) {
    const current = queue.shift();
    if (visited.has(current)) {
      continue;
    }
    visited.add(current);
    const skill = skillMap.get(current);
    if (!skill) {
      continue;
    }
    skill.enabled = enabled;
    if (enabled) {
      const { relations } = await extractSkillInfo(skill.module_path);
      for (const relation of relations) {
        queue.push(relation);
      }
    }
  }
  await saveRegistryLock(lock);
  await rebuildIndexes();
  log(`${enabled ? "Enabled" : "Disabled"} ${qualifiedId}`);
}

async function removeInstalled(target) {
  const lock = await loadRegistryLock();
  if (target.includes("/")) {
    const [packageId, skillId] = target.split("/", 2);
    const pkg = lock.packages[packageId];
    if (!pkg) {
      fail(`Package not installed: ${packageId}`);
    }
    pkg.skills = pkg.skills.filter((skill) => skill.skill_id !== skillId);
    if (!pkg.skills.length) {
      await fsp.rm(pkg.install_root, { recursive: true, force: true });
      delete lock.packages[packageId];
    }
  } else {
    const pkg = lock.packages[target];
    if (!pkg) {
      fail(`Package not installed: ${target}`);
    }
    await fsp.rm(pkg.install_root, { recursive: true, force: true });
    delete lock.packages[target];
  }
  await saveRegistryLock(lock);
  await rebuildIndexes();
  log(`Removed ${target}`);
}

async function registryAddSource(name, indexUrl) {
  const sources = await loadRegistrySources();
  sources.sources = sources.sources.filter((source) => source.name !== name);
  sources.sources.push({ name, index_url: indexUrl, trust_tier: "verified" });
  await saveRegistrySources(sources);
  log(`Configured registry source ${name}`);
}

async function registryList() {
  const sources = await loadRegistrySources();
  for (const source of sources.sources) {
    log(`${source.name}: ${source.index_url}`);
  }
}

async function searchRegistry(query) {
  const matches = await findSkillInRegistry(query);
  for (const match of matches) {
    log(`${match.qualifiedId} - ${(match.skill.description || match.manifest.description || "").trim()}`);
  }
}

function platformAssetName() {
  const platformMap = {
    darwin: "darwin",
    linux: "linux"
  };
  const archMap = {
    arm64: "arm64",
    x64: "x64"
  };
  const platform = platformMap[process.platform];
  const arch = archMap[process.arch];
  if (!platform || !arch) {
    fail(`Unsupported platform: ${process.platform}/${process.arch}`);
  }
  return `ontomcp-${platform}-${arch}.tar.gz`;
}

async function fetchLatestRelease(repo) {
  const response = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
    headers: {
      "User-Agent": "ontoskills",
      Accept: "application/vnd.github+json"
    }
  });
  if (!response.ok) {
    fail(`Failed to fetch release metadata for ${repo}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function downloadFile(url, destination) {
  const response = await fetch(url, { headers: { "User-Agent": "ontoskills" } });
  if (!response.ok) {
    fail(`Failed to download ${url}: ${response.status} ${response.statusText}`);
  }
  const buffer = Buffer.from(await response.arrayBuffer());
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  await fsp.writeFile(destination, buffer);
}

function runCommand(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: "pipe", encoding: "utf-8", ...options });
  if (result.status !== 0) {
    fail(`${command} ${args.join(" ")} failed:\n${result.stderr || result.stdout}`);
  }
  return result;
}

async function installMcp() {
  await ensureLayout();
  const release = await fetchLatestRelease(DEFAULT_REPOSITORY);
  const assetName = platformAssetName();
  const asset = (release.assets || []).find((candidate) => candidate.name === assetName);
  if (!asset) {
    fail(`Release ${release.tag_name} does not contain asset ${assetName}`);
  }
  const archivePath = path.join(CACHE_DIR, asset.name);
  const extractDir = path.join(CACHE_DIR, `mcp-${release.tag_name}`);
  await fsp.rm(extractDir, { recursive: true, force: true });
  await downloadFile(asset.browser_download_url, archivePath);
  await fsp.mkdir(extractDir, { recursive: true });
  runCommand("tar", ["-xzf", archivePath, "-C", extractDir]);

  const binaryPath = path.join(extractDir, "ontomcp");
  await fsp.copyFile(binaryPath, path.join(BIN_DIR, "ontomcp"));
  await fsp.chmod(path.join(BIN_DIR, "ontomcp"), 0o755);

  // Download core ontology from ontoskills.sh
  if (!fs.existsSync(CORE_ONTOLOGY_PATH)) {
    await downloadFile(CORE_ONTOLOGY_URL, CORE_ONTOLOGY_PATH);
  }

  const releases = await loadReleaseLock();
  releases.mcp = {
    version: release.tag_name,
    asset: asset.name,
    installed_at: new Date().toISOString()
  };
  await saveReleaseLock(releases);
  log(`Installed ontomcp ${release.tag_name}`);
}

function successResult(client, scope, mode, details) {
  return { client, scope, status: mode, details };
}

function manualResult(client, scope, details) {
  return { client, scope, status: "manual_required", details };
}

function skippedResult(client, scope, details) {
  return { client, scope, status: "skipped", details };
}

function scopeLabel(scope) {
  return scope === "project" ? "project" : "global";
}

async function configureClaudeMcp(serverSpec, scope) {
  const cliScope = scope === "project" ? "project" : "user";
  if (!commandExists("claude")) {
    return manualResult(
      "claude",
      scope,
      `Install Claude Code and run: claude mcp add --scope ${cliScope} ${serverSpec.name} -- ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }

  removeIfConfigured("claude", ["mcp", "remove", "--scope", cliScope, serverSpec.name]);
  const result = runCommandResult("claude", ["mcp", "add", "--scope", cliScope, serverSpec.name, "--", serverSpec.command, ...serverSpec.args]);
  if (result.status !== 0) {
    return manualResult("claude", scope, (result.stderr || result.stdout || "").trim() || "Claude Code registration failed");
  }
  return successResult("claude", scope, "configured", `Registered via claude mcp add (${cliScope})`);
}

async function configureCodexMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult(
      "codex",
      scope,
      `Codex project-local MCP bootstrap is not automated yet. Configure ${serverSpec.name} manually for this repository using ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }
  if (!commandExists("codex")) {
    return manualResult(
      "codex",
      scope,
      `Install Codex and run: codex mcp add ${serverSpec.name} -- ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }

  removeIfConfigured("codex", ["mcp", "remove", serverSpec.name]);
  const result = runCommandResult("codex", ["mcp", "add", serverSpec.name, "--", serverSpec.command, ...serverSpec.args]);
  if (result.status !== 0) {
    return manualResult("codex", scope, (result.stderr || result.stdout || "").trim() || "Codex registration failed");
  }
  return successResult("codex", scope, "configured", "Registered via codex mcp add");
}

async function configureQwenMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = qwenSettingsPath(scope, cwd);
  const cliScope = scope === "project" ? "project" : "user";
  if (commandExists("qwen")) {
    const removeArgs = compact(["mcp", "remove", scope === "project" ? "--scope" : null, scope === "project" ? "project" : null, serverSpec.name]);
    removeIfConfigured("qwen", removeArgs);
    const addArgs = compact([
      "mcp",
      "add",
      scope === "project" ? "--scope" : null,
      scope === "project" ? "project" : null,
      serverSpec.name,
      serverSpec.command,
      ...serverSpec.args
    ]);
    const result = runCommandResult("qwen", addArgs);
    if (result.status === 0) {
      return successResult("qwen", scope, "configured", `Registered via qwen mcp add (${cliScope})`);
    }
  }

  await configureQwenJson(configPath, serverSpec);
  return successResult("qwen", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureCursorMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = cursorConfigPath(scope, cwd);
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("cursor", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureVsCodeMcp(serverSpec, scope, cwd = process.cwd()) {
  if (scope === "global") {
    if (!commandExists("code")) {
      return manualResult(
        "vscode",
        scope,
        `Install VS Code CLI and run: code --add-mcp '${JSON.stringify({ name: serverSpec.name, command: serverSpec.command, args: serverSpec.args })}'`
      );
    }
    const payload = JSON.stringify({ name: serverSpec.name, command: serverSpec.command, args: serverSpec.args });
    const result = runCommandResult("code", ["--add-mcp", payload]);
    if (result.status !== 0) {
      return manualResult("vscode", scope, (result.stderr || result.stdout || "").trim() || "VS Code global registration failed");
    }
    return successResult("vscode", scope, "configured", "Registered via code --add-mcp");
  }

  const configPath = vscodeProjectConfigPath(cwd);
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("vscode", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureWindsurfMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult("windsurf", scope, "Windsurf project-local MCP bootstrap is not automated yet. Use workspace settings manually.");
  }
  const configPath = windsurfConfigPath();
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("windsurf", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureOpenCodeMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = opencodeConfigPath(scope, cwd);
  await configureOpenCodeJson(configPath, serverSpec);
  return successResult("opencode", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureAntigravityMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult("antigravity", scope, "Antigravity project-local MCP bootstrap is not automated yet. Add OntoMCP in the project MCP settings manually.");
  }
  for (const configPath of antigravityCandidatePaths()) {
    try {
      if (fs.existsSync(path.dirname(configPath)) || fs.existsSync(configPath)) {
        await configureMcpServersJson(configPath, serverSpec);
        return successResult("antigravity", scope, "configured_by_file", `Wrote ${configPath}`);
      }
    } catch (_error) {
      continue;
    }
  }
  return manualResult(
    "antigravity",
    scope,
    `Configure OntoMCP manually in Antigravity settings using ${formatCommand(serverSpec.command, serverSpec.args)}`
  );
}

const MCP_CLIENT_ADAPTERS = {
  codex: configureCodexMcp,
  claude: configureClaudeMcp,
  qwen: configureQwenMcp,
  cursor: configureCursorMcp,
  vscode: configureVsCodeMcp,
  windsurf: configureWindsurfMcp,
  antigravity: configureAntigravityMcp,
  opencode: configureOpenCodeMcp
};

function printMcpBootstrapSummary(results) {
  if (!results.length) {
    return;
  }
  log(`Configured OntoMCP for ${results.length} client${results.length === 1 ? "" : "s"}:`);
  for (const result of results) {
    log(`- ${result.client} [${result.scope}] ${result.status}: ${result.details}`);
  }
}

async function installMcpBootstrap(args, cwd = process.cwd()) {
  const options = parseMcpInstallArgs(args);
  await installMcp();
  if (!options.targets.length) {
    return;
  }

  const serverSpec = buildStdIoServerSpec();
  const results = [];
  for (const target of options.targets) {
    const adapter = MCP_CLIENT_ADAPTERS[target];
    if (!adapter) {
      results.push(skippedResult(target, options.scope, "No adapter available"));
      continue;
    }
    const result = await adapter(serverSpec, options.scope, cwd);
    results.push(result);
  }
  printMcpBootstrapSummary(results);
}

function findPython() {
  for (const candidate of [process.env.PYTHON, "python3"]) {
    if (!candidate) {
      continue;
    }
    const result = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (result.status === 0) {
      return candidate;
    }
  }
  fail("python3 is required to install ontocore");
}

async function installCore() {
  await ensureLayout();
  const release = await fetchLatestRelease(DEFAULT_REPOSITORY);
  const wheel = (release.assets || []).find(
    (asset) =>
      asset.name.startsWith("ontocore-") &&
      asset.name.endsWith(".whl")
  );
  if (!wheel) {
    fail(`Release ${release.tag_name} does not contain an ontocore wheel`);
  }
  const python = findPython();
  const wheelPath = path.join(CACHE_DIR, wheel.name);
  await downloadFile(wheel.browser_download_url, wheelPath);
  const venvDir = path.join(CORE_DIR, "venv");
  runCommand(python, ["-m", "venv", venvDir]);
  const pip = path.join(venvDir, "bin", "pip");
  runCommand(pip, ["install", "--upgrade", "pip"]);
  runCommand(pip, ["install", wheelPath]);

  const wrapperPath = path.join(BIN_DIR, "ontocore");
  const script = `#!/usr/bin/env bash\nexec "${path.join(venvDir, "bin", "ontocore")}" "$@"\n`;
  await fsp.writeFile(wrapperPath, script, "utf-8");
  await fsp.chmod(wrapperPath, 0o755);

  const releases = await loadReleaseLock();
  releases.core = {
    version: release.tag_name,
    asset: wheel.name,
    installed_at: new Date().toISOString()
  };
  await saveReleaseLock(releases);
  log(`Installed ontocore ${release.tag_name}`);
}

async function updateTarget(target) {
  const releases = await loadReleaseLock();
  if (target === "mcp" || target === "ontomcp") {
    return installMcp();
  }
  if (target === "core" || target === "ontocore") {
    return installCore();
  }
  if (target === "all") {
    if (releases.mcp) {
      await installMcp();
    }
    if (releases.core) {
      await installCore();
    }
    const lock = await loadRegistryLock();
    for (const pkg of Object.values(lock.packages)) {
      if (pkg.package_id === "local") {
        continue;
      }
      for (const skill of pkg.skills) {
        await installSkill(`${pkg.package_id}/${skill.skill_id}`);
      }
    }
    return;
  }
  const lock = await loadRegistryLock();
  if (target in lock.packages) {
    const pkg = lock.packages[target];
    for (const skill of pkg.skills) {
      await installSkill(`${pkg.package_id}/${skill.skill_id}`);
    }
    return;
  }
  await installSkill(target);
}

async function importSource(repoRef) {
  await ensureLayout();
  const sourceSlug = slugify(path.basename(repoRef).replace(/\.git$/, ""));
  const sourceDir = path.join(SKILLS_VENDOR_DIR, sourceSlug);
  await fsp.rm(sourceDir, { recursive: true, force: true });
  if (repoRef.startsWith("http://") || repoRef.startsWith("https://") || repoRef.endsWith(".git")) {
    runCommand("git", ["clone", "--depth", "1", repoRef, sourceDir]);
  } else {
    runCommand("cp", ["-R", repoRef, sourceDir]);
  }

  const ontocoreWrapper = path.join(BIN_DIR, "ontocore");
  if (!fs.existsSync(ontocoreWrapper)) {
    fail("ontocore is not installed. Run: ontoskills install core");
  }

  const outputDir = path.join(ONTOLOGY_VENDOR_DIR, sourceSlug);
  await fsp.rm(outputDir, { recursive: true, force: true });
  await fsp.mkdir(outputDir, { recursive: true });
  runCommand(ontocoreWrapper, ["compile", "-i", sourceDir, "-o", outputDir, "-y", "-f"], {
    env: {
      ...process.env,
      ONTOCLAW_SKILLS_DIR: sourceDir,
      ONTOCLAW_ONTOLOGY_ROOT: ONTOLOGY_DIR,
      ONTOCLAW_OUTPUT_DIR: outputDir
    }
  });

  const packageId = sourceSlug;
  const manifestPath = path.join(outputDir, "package.json");
  const skillPaths = [];
  async function collectCompiled(dir) {
    const entries = await fsp.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const target = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await collectCompiled(target);
      } else if (entry.isFile() && entry.name === "ontoskill.ttl") {
        skillPaths.push(target);
      }
    }
  }
  await collectCompiled(outputDir);

  const skills = [];
  for (const modulePath of skillPaths.sort()) {
    const { skillId } = await extractSkillInfo(modulePath);
    if (!skillId) {
      continue;
    }
    skills.push({
      skill_id: skillId,
      module_path: path.resolve(modulePath),
      aliases: [],
      enabled: true,
      default_enabled: true
    });
  }

  const manifest = {
    package_id: packageId,
    version: `import-${new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14)}`,
    source: repoRef
  };
  await fsp.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");

  const lock = await loadRegistryLock();
  lock.packages[packageId] = {
    package_id: packageId,
    version: manifest.version,
    trust_tier: "community",
    source: repoRef,
    installed_at: new Date().toISOString(),
    install_root: outputDir,
    manifest_path: manifestPath,
    skills
  };
  await saveRegistryLock(lock);
  await rebuildIndexes();
  log(`Imported source repository ${repoRef} as ${packageId}`);
}

async function doctor() {
  await ensureLayout();
  const releaseLock = await loadReleaseLock();
  const registryLock = await loadRegistryLock();
  log(`home: ${HOME_ROOT}`);
  log(`bin: ${BIN_DIR}`);
  log(`ontologies: ${ONTOLOGY_DIR}`);
  log(`state: ${STATE_DIR}`);
  log(`mcp: ${releaseLock.mcp ? releaseLock.mcp.version : "not installed"}`);
  log(`core: ${releaseLock.core ? releaseLock.core.version : "not installed"}`);
  log(`packages: ${Object.keys(registryLock.packages).join(", ") || "(none)"}`);

  try {
    const release = await fetchLatestRelease(DEFAULT_REPOSITORY);
    if (releaseLock.mcp && releaseLock.mcp.version !== release.tag_name) {
      log(`update available: mcp ${releaseLock.mcp.version} -> ${release.tag_name}`);
    }
    if (releaseLock.core && releaseLock.core.version !== release.tag_name) {
      log(`update available: core ${releaseLock.core.version} -> ${release.tag_name}`);
    }
  } catch (_error) {
    log("update check: skipped (release metadata unavailable)");
  }

  for (const pkg of Object.values(registryLock.packages)) {
    if (pkg.package_id === "local") {
      continue;
    }
    try {
      const latest = await registryPackageVersion(pkg.package_id);
      if (latest && latest !== pkg.version) {
        log(`update available: ${pkg.package_id} ${pkg.version} -> ${latest}`);
      }
    } catch (_error) {
      log(`update check skipped for package ${pkg.package_id}`);
    }
  }
}

async function uninstallAll() {
  await fsp.rm(HOME_ROOT, { recursive: true, force: true });
  log(`Removed ${HOME_ROOT}`);
}

function usage() {
  log(`ontoskills commands:
  ontoskills install ontomcp
  ontoskills install ontomcp [--global|--project] [--all-clients|--codex|--claude|--qwen|--cursor|--vscode|--windsurf|--antigravity|--opencode]
  ontoskills install ontocore
  ontoskills install <qualified-skill-id>
  ontoskills update ontomcp|ontocore|all|<qualified-skill-id>|<package-id>
  ontoskills store add-source <name> <index_url>
  ontoskills store list
  ontoskills search <query>
  ontoskills enable <qualified-skill-id>
  ontoskills disable <qualified-skill-id>
  ontoskills remove <qualified-skill-id>|<package-id>
  ontoskills rebuild-index
  ontoskills import-source <repo-or-path>
  ontoskills list-installed
  ontoskills doctor
  ontoskills uninstall --all`);
}

async function listInstalled() {
  const lock = await loadRegistryLock();
  for (const pkg of Object.values(lock.packages)) {
    log(`${pkg.package_id} ${pkg.version}`);
    const enabled = pkg.skills.filter((skill) => skill.enabled).map((skill) => skill.skill_id);
    const disabled = pkg.skills.filter((skill) => !skill.enabled).map((skill) => skill.skill_id);
    log(`  enabled: ${enabled.join(", ") || "(none)"}`);
    log(`  disabled: ${disabled.join(", ") || "(none)"}`);
  }
}

async function main() {
  const [, , command, ...args] = process.argv;

  if (!command || command === "--help" || command === "help") {
    usage();
    return;
  }

  await ensureLayout();

  if (command === "install") {
    const target = args[0];
    if (!target) fail("Missing install target");
    if (target === "mcp" || target === "ontomcp") return installMcpBootstrap(args.slice(1));
    if (target === "core" || target === "ontocore") return installCore();
    if (target.includes("/")) return installSkill(target);
    fail("Install target must be ontomcp, ontocore, or a qualified skill id");
  }

  if (command === "update") {
    const target = args[0] || "all";
    return updateTarget(target);
  }

  if (command === "registry" || command === "store") {
    if (args[0] === "add-source") {
      if (args.length < 3) fail(`Usage: ontoskills ${command} add-source <name> <index_url>`);
      return registryAddSource(args[1], args[2]);
    }
    if (args[0] === "list") {
      return registryList();
    }
    fail(`Unknown ${command} command`);
  }

  if (command === "search") {
    return searchRegistry(args.join(" "));
  }

  if (command === "enable") {
    const target = args[0];
    if (!target) fail("Missing qualified skill id");
    return enableSkill(target, true);
  }

  if (command === "disable") {
    const target = args[0];
    if (!target) fail("Missing qualified skill id");
    return enableSkill(target, false);
  }

  if (command === "remove") {
    const target = args[0];
    if (!target) fail("Missing target");
    return removeInstalled(target);
  }

  if (command === "rebuild-index") {
    await rebuildIndexes();
    log("Rebuilt indexes");
    return;
  }

  if (command === "import-source") {
    const repoRef = args[0];
    if (!repoRef) fail("Missing repo or path");
    return importSource(repoRef);
  }

  if (command === "doctor") {
    return doctor();
  }

  if (command === "list-installed") {
    return listInstalled();
  }

  if (command === "uninstall" && args[0] === "--all") {
    return uninstallAll();
  }

  fail(`Unknown command: ${command}`);
}

if (require.main === module) {
  main().catch((error) => {
    fail(error && error.stack ? error.stack : String(error));
  });
}

module.exports = {
  MCP_CLIENT_ORDER,
  parseMcpInstallArgs,
  buildStdIoServerSpec,
  configureMcpServersJson,
  configureOpenCodeJson,
  configureQwenJson,
  cursorConfigPath,
  vscodeProjectConfigPath,
  windsurfConfigPath,
  opencodeConfigPath,
  qwenSettingsPath,
  antigravityCandidatePaths,
  installMcpBootstrap,
  configureCursorMcp,
  configureVsCodeMcp,
  configureWindsurfMcp,
  configureOpenCodeMcp,
  configureAntigravityMcp,
  configureQwenMcp
};
