#!/usr/bin/env node

/**
 * Version Sync Script
 *
 * Synchronizes the version from root package.json to all sub-packages.
 * Run this before creating a release to ensure all packages have the same version.
 *
 * Usage:
 *   node scripts/sync-version.js
 *   npm run sync-version
 */

const fs = require('fs');
const path = require('path');

// Root package.json is the single source of truth
const rootPackageJsonPath = path.join(__dirname, '..', 'package.json');
const rootPackageJson = JSON.parse(fs.readFileSync(rootPackageJsonPath, 'utf-8'));
const version = rootPackageJson.version;

console.log(`📦 Syncing version: ${version}\n`);

// List of package.json files to sync
const packageJsonPaths = [
  "frontend/apps/web/package.json",
  "frontend/apps/admin/package.json",
  "frontend/packages/api-client/package.json",
  "frontend/packages/i18n/package.json",
  "frontend/packages/logger/package.json",
  "frontend/packages/types/package.json",
  "frontend/packages/ui/package.json",
  "frontend/package.json",
];

// Backend pyproject.toml files to sync
const pyprojectPaths = [
  'backend/pyproject.toml',
];

let hasErrors = false;

// Sync package.json files
for (const relativePath of packageJsonPaths) {
  const fullPath = path.join(__dirname, '..', relativePath);

  if (!fs.existsSync(fullPath)) {
    console.log(`⚠️  Skipping (not found): ${relativePath}`);
    continue;
  }

  try {
    const packageJson = JSON.parse(fs.readFileSync(fullPath, 'utf-8'));
    const oldVersion = packageJson.version;

    if (oldVersion === version) {
      console.log(`✓  Already up to date: ${relativePath}`);
    } else {
      packageJson.version = version;
      fs.writeFileSync(fullPath, JSON.stringify(packageJson, null, 2) + '\n', 'utf-8');
      console.log(`✓  Updated: ${relativePath} (${oldVersion} → ${version})`);
    }
  } catch (error) {
    console.error(`✗  Error updating ${relativePath}: ${error.message}`);
    hasErrors = true;
  }
}

// Sync pyproject.toml files
for (const relativePath of pyprojectPaths) {
  const fullPath = path.join(__dirname, '..', relativePath);

  if (!fs.existsSync(fullPath)) {
    console.log(`⚠️  Skipping (not found): ${relativePath}`);
    continue;
  }

  try {
    let content = fs.readFileSync(fullPath, 'utf-8');

    // Match version line in pyproject.toml (e.g., version = "0.1.0")
    const versionRegex = /^version\s*=\s*"([^"]+)"/m;
    const match = content.match(versionRegex);

    if (match) {
      const oldVersion = match[1];

      if (oldVersion === version) {
        console.log(`✓  Already up to date: ${relativePath}`);
      } else {
        content = content.replace(versionRegex, `version = "${version}"`);
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✓  Updated: ${relativePath} (${oldVersion} → ${version})`);
      }
    } else {
      console.log(`⚠️  No version found in: ${relativePath}`);
    }
  } catch (error) {
    console.error(`✗  Error updating ${relativePath}: ${error.message}`);
    hasErrors = true;
  }
}

console.log('\n' + (hasErrors ? '❌ Sync completed with errors' : '✅ Version sync complete!'));
console.log(`\nNext steps:`);
console.log(`  1. Review the changes: git diff`);
console.log(`  2. Commit: git commit -am "chore: bump version to ${version}"`);
console.log(`  3. Tag: git tag v${version}`);
console.log(`  4. Push: git push && git push --tags`);

process.exit(hasErrors ? 1 : 0);
