const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");

const {
  HOME_ROOT,
  BIN_DIR,
  CACHE_DIR,
  CORE_DIR,
  ONTOLOGY_AUTHOR_DIR,
  EMBEDDINGS_DIR,
  SKILLS_AUTHOR_DIR,
  CORE_ONTOLOGY_PATH,
  CORE_ONTOLOGY_URL,
  DEFAULT_REPOSITORY,
  DEFAULT_REGISTRY_URL,
  ensureLayout,
  ensureArray,
  slugify,
  runCommand,
  commandExists,
  fail,
  log,
} = require("./paths");

const {
  loadRegistryLock,
  loadReleaseLock,
  saveReleaseLock,
  rebuildIndexes,
  mergeEmbeddings,
  findSkillInRegistry,
  loadPackageManifest,
  loadRegistryEntries,
  defaultTrustTier,
  registryPackageVersion,
  extractSkillInfo,
  copyRefToFile,
} = require("./registry");

// --- Skill install/remove ---

async function installSkill(qualifiedId, options = {}) {
  if (!qualifiedId.includes("/")) {
    fail("Install expects a qualified skill id like marea/office/xlsx");
  }
  const withEmbeddings = options.withEmbeddings || false;
  const segments = qualifiedId.split("/");
  if (segments.length < 3) {
    fail(`Skill-level install requires a qualified id like author/package/skill, got: ${qualifiedId}`);
  }
  const packageId = segments.slice(0, 2).join("/");
  const skillId = segments.slice(2).join("/");
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

  const installRoot = path.join(ONTOLOGY_AUTHOR_DIR, manifest.package_id);
  await fsp.mkdir(installRoot, { recursive: true });

  for (const skill of manifest.skills || []) {
    if (!selectedIds.has(skill.id)) {
      continue;
    }
    const sourceRef = resolveChildRefForInstall(manifestRef, skill.path);
    await copyRefToFile(sourceRef, path.join(installRoot, skill.path));

    // Download per-skill intents.json (embedding file)
    if (withEmbeddings && manifest.embedding_files) {
      const embeddingFile = manifest.embedding_files.find((f) => f.startsWith(skill.path.replace(/\/ontoskill\.ttl$/, "") + "/intents.json") || f === skill.path.replace(/\/ontoskill\.ttl$/, "/intents.json"));
      if (embeddingFile) {
        const embRef = resolveChildRefForInstall(manifestRef, embeddingFile);
        await copyRefToFile(embRef, path.join(installRoot, embeddingFile));
      }
    }
  }
  await fsp.writeFile(path.join(installRoot, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");

  // Download global embedding model files (once, cached)
  if (withEmbeddings) {
    await downloadEmbeddingModel(manifestRef);
  }

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

  // Merge per-skill intents into global system/embeddings/intents.json
  if (withEmbeddings) {
    await mergeEmbeddings();
  }

  log(`Installed skill ${qualifiedId}`);
}

async function installSingleTarget(target, options = {}) {
  // Resolve a single-segment install target:
  // 1. Matches an author (prefix match) → install all author packages
  // 2. Matches a package by short name (unique) → install that package
  // 3. Ambiguous → ask user to disambiguate
  const withEmbeddings = options.withEmbeddings || false;
  const entries = await loadRegistryEntries();

  const authorMatches = entries.filter((e) => e.package.package_id.startsWith(target + "/"));
  const shortNameMatches = entries.filter((e) => {
    const parts = e.package.package_id.split("/");
    return parts[parts.length - 1] === target || e.package.package_id.endsWith("/" + target);
  });

  // Collect all unique interpretations
  const allMatches = [...new Set([...authorMatches, ...shortNameMatches])];

  if (!allMatches.length) {
    fail(`No packages found matching '${target}' in configured registries`);
  }

  // If it matches as author only → install all author packages
  if (authorMatches.length > 0 && shortNameMatches.length === 0) {
    for (const entry of authorMatches) {
      try {
        await installPackage(entry.package.package_id, { withEmbeddings });
      } catch (e) {
        warn(`Failed to install ${entry.package.package_id}: ${e.message || e}`);
      }
    }
    log(`Installed author ${target}: ${authorMatches.length} package(s)`);
    return;
  }

  // If it matches as short name only (unique) → install that package
  if (shortNameMatches.length === 1 && authorMatches.length === 0) {
    const pkg = shortNameMatches[0].package.package_id;
    await installPackage(pkg, { withEmbeddings });
    return;
  }

  // Ambiguous — show options and ask
  const candidates = [...new Set([
    ...authorMatches.map((e) => ({ type: "author", id: target, display: `${target}/ (${authorMatches.length} packages)` })),
    ...shortNameMatches.map((e) => ({ type: "package", id: e.package.package_id, display: e.package.package_id })),
  ])];

  // Deduplicate by id
  const unique = [];
  const seen = new Set();
  for (const c of candidates) {
    const key = `${c.type}:${c.id}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(c);
    }
  }

  log(`Ambiguous target '${target}'. Did you mean:`);
  for (let i = 0; i < unique.length; i++) {
    log(`  ${i + 1}. ${unique[i].display}`);
  }
  fail(`Please specify: ${unique.map((c) => c.id).join(", ")}`);
}

async function installPackage(packageId, options = {}) {
  const withEmbeddings = options.withEmbeddings || false;
  const entries = await loadRegistryEntries();
  const match = entries.find((e) => e.package.package_id === packageId);
  if (!match) {
    fail(`Package not found in configured registries: ${packageId}`);
  }

  const { manifestRef, manifest } = await loadPackageManifest(match);
  const installRoot = path.join(ONTOLOGY_AUTHOR_DIR, manifest.package_id);
  await fsp.mkdir(installRoot, { recursive: true });

  // Copy all skill modules
  const modules = new Set([...(manifest.modules || []), ...(manifest.skills || []).map((s) => s.path)]);
  for (const mod of modules) {
    const sourceRef = resolveChildRefForInstall(manifestRef, mod);
    await copyRefToFile(sourceRef, path.join(installRoot, mod));
  }

  // Download per-skill intents.json files
  if (withEmbeddings && manifest.embedding_files) {
    for (const ef of manifest.embedding_files) {
      const embRef = resolveChildRefForInstall(manifestRef, ef);
      await copyRefToFile(embRef, path.join(installRoot, ef));
    }
  }

  await fsp.writeFile(path.join(installRoot, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");

  // Download global embedding model files (once, cached)
  if (withEmbeddings) {
    await downloadEmbeddingModel(manifestRef);
  }

  const lock = await loadRegistryLock();
  lock.packages[manifest.package_id] = {
    package_id: manifest.package_id,
    version: manifest.version,
    trust_tier: manifest.trust_tier || defaultTrustTier(),
    installed_at: new Date().toISOString(),
    skills: (manifest.skills || []).map((skill) => ({
      skill_id: skill.id,
      module_path: path.join(installRoot, skill.path),
      aliases: skill.aliases || [],
      enabled: skill.default_enabled !== false,
      default_enabled: skill.default_enabled !== false,
    })),
  };
  await saveRegistryLock(lock);
  await rebuildIndexes();
  await mergeEmbeddings();

  log(`Installed ${manifest.package_id}: ${(manifest.skills || []).length} skill(s)`);
}

async function downloadEmbeddingModel(manifestRef) {
  // Model (~87MB) from HuggingFace, tokenizer from registry (695KB)
  const MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2";
  const HF_MODEL_URL = `https://huggingface.co/${MODEL_REPO}/resolve/main/onnx/model.onnx`;
  const registryRoot = manifestRef.replace(/\/packages\/.*$/, "");
  const modelDest = path.join(EMBEDDINGS_DIR, "model.onnx");
  const tokDest = path.join(EMBEDDINGS_DIR, "tokenizer.json");

  // Download ONNX model from HuggingFace (cached, one-time ~87MB)
  if (!fs.existsSync(modelDest)) {
    try {
      const response = await fetch(HF_MODEL_URL, { redirect: "follow" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const buffer = Buffer.from(await response.arrayBuffer());
      await fsp.mkdir(EMBEDDINGS_DIR, { recursive: true });
      await fsp.writeFile(modelDest, buffer);
    } catch (_error) {
      // Model not available — semantic search will be unavailable
    }
  }

  // Download tokenizer from registry (small, reliable)
  if (!fs.existsSync(tokDest)) {
    try {
      const ref = resolveChildRefForInstall(registryRoot, "embeddings/tokenizer.json");
      await copyRefToFile(ref, tokDest);
    } catch (_error) {
      // Non-fatal
    }
  }
}

function resolveChildRefForInstall(baseRef, childPath) {
  if (baseRef.startsWith("http://") || baseRef.startsWith("https://") || baseRef.startsWith("file://")) {
    return new URL(childPath, baseRef).toString();
  }
  return path.resolve(path.dirname(baseRef), childPath);
}

async function enableSkill(qualifiedId, enabled) {
  let packageId, skillId;
  const segments = qualifiedId.split("/");
  if (segments.length === 1) {
    packageId = "local";
    skillId = segments[0];
  } else if (segments[0] === "local") {
    packageId = "local";
    skillId = segments.slice(1).join("/");
  } else if (segments.length >= 3) {
    packageId = segments.slice(0, 2).join("/");
    skillId = segments.slice(2).join("/");
  } else {
    packageId = segments[0];
    skillId = segments[1];
  }
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
    const segments = target.split("/");
    let packageId, skillId;
    if (segments[0] === "local") {
      packageId = "local";
      skillId = segments.slice(1).join("/");
    } else if (segments.length >= 3) {
      packageId = segments.slice(0, 2).join("/");
      skillId = segments.slice(2).join("/");
    } else {
      packageId = segments[0];
      skillId = segments[1];
    }
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
  await mergeEmbeddings();
  log(`Removed ${target}`);
}

// --- MCP binary install ---

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

// --- Core install ---

function findPython() {
  for (const candidate of [process.env.PYTHON, "python3"]) {
    if (!candidate) {
      continue;
    }
    const { spawnSync } = require("child_process");
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

// --- Update ---

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

// --- Source import ---

async function importSource(repoRef) {
  await ensureLayout();
  const sourceSlug = slugify(path.basename(repoRef).replace(/\.git$/, ""));
  const sourceDir = path.join(SKILLS_AUTHOR_DIR, sourceSlug);
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

  const outputDir = path.join(ONTOLOGY_AUTHOR_DIR, sourceSlug);
  await fsp.rm(outputDir, { recursive: true, force: true });
  await fsp.mkdir(outputDir, { recursive: true });
  runCommand(ontocoreWrapper, ["compile", "-i", sourceDir, "-o", outputDir, "-y", "-f"], {
    env: {
      ...process.env,
      ONTOCLAW_SKILLS_DIR: sourceDir,
      ONTOCLAW_ONTOLOGY_ROOT: path.join(HOME_ROOT, "ontologies"),
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

module.exports = {
  installSkill,
  installPackage,
  installSingleTarget,
  enableSkill,
  removeInstalled,
  installMcp,
  installCore,
  updateTarget,
  importSource,
  fetchLatestRelease,
  downloadFile,
  registryPackageVersion,
};
