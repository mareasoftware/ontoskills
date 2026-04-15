#!/usr/bin/env node

const { log, fail, ensureLayout } = require("./lib/paths");
const { rebuildIndexes, registryPackageVersion, loadRegistryLock, loadReleaseLock, fetchLatestRelease, searchRegistry, registryAddSource, registryList } = require("./lib/registry");
const { installSkill, installPackage, installSingleTarget, enableSkill, removeInstalled, installCore, installMcp, updateTarget, importSource } = require("./lib/install");
const { installMcpBootstrap } = require("./lib/mcp-config");

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

async function doctor() {
  const { HOME_ROOT, BIN_DIR, ONTOLOGY_DIR, STATE_DIR, DEFAULT_REPOSITORY } = require("./lib/paths");
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
  const fsp = require("fs/promises");
  const { HOME_ROOT } = require("./lib/paths");
  await fsp.rm(HOME_ROOT, { recursive: true, force: true });
  log(`Removed ${HOME_ROOT}`);
}

async function main() {
  const [, , command, ...args] = process.argv;

  if (!command || command === "--help" || command === "help") {
    usage();
    return;
  }

  await ensureLayout();

  if (command === "install") {
    const withEmbeddings = args.includes("--with-embeddings");
    const filteredArgs = args.filter((a) => a !== "--with-embeddings");
    const target = filteredArgs[0];
    if (!target) fail("Missing install target");
    if (target === "mcp" || target === "ontomcp") return installMcpBootstrap(filteredArgs.slice(1));
    if (target === "core" || target === "ontocore") return installCore();
    if (target.includes("/")) {
      const segments = target.split("/").filter(Boolean);
      if (segments.length === 2) return installPackage(target, { withEmbeddings });
      return installSkill(target, { withEmbeddings });
    }
    // Single-segment target → smart resolution (author, short name, or ask)
    return installSingleTarget(target, { withEmbeddings });
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
