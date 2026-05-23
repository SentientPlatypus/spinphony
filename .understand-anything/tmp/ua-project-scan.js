#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync, spawnSync } = require('child_process');

const PROJECT_ROOT = process.argv[2];
const OUTPUT_FILE = process.argv[3];

if (!PROJECT_ROOT || !OUTPUT_FILE) {
  process.stderr.write('Usage: ua-project-scan.js <project-root> <output-file>\n');
  process.exit(1);
}

if (!fs.existsSync(PROJECT_ROOT)) {
  process.stderr.write(`Cannot access directory: ${PROJECT_ROOT}\n`);
  process.exit(1);
}

// ── Step 1: File Discovery ────────────────────────────────────────────────────
let allFiles = [];
try {
  const result = spawnSync('git', ['ls-files'], { cwd: PROJECT_ROOT, encoding: 'utf8' });
  if (result.status === 0 && result.stdout.trim()) {
    allFiles = result.stdout.trim().split('\n').filter(Boolean);
  } else {
    throw new Error('git ls-files failed');
  }
} catch (e) {
  // Fallback: recursive listing
  function walk(dir, base) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return; }
    for (const entry of entries) {
      const rel = base ? `${base}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(path.join(dir, entry.name), rel);
      else allFiles.push(rel);
    }
  }
  walk(PROJECT_ROOT, '');
}

// ── Step 2: Exclusion Filtering ───────────────────────────────────────────────
const EXCLUDE_DIR_SEGMENTS = new Set([
  'node_modules', '.git', 'vendor', 'venv', '.venv', '__pycache__',
  'dist', 'build', 'out', 'coverage', '.next', '.cache', '.turbo',
  'target', 'obj', '.idea', '.vscode',
  // Project-specific from .understandignore
  'Debug', 'input-songs'
]);

const EXCLUDE_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
  '.woff', '.woff2', '.ttf', '.eot',
  '.mp3', '.mp4', '.pdf', '.zip', '.tar', '.gz',
  '.avi', '.wav',
  // From .understandignore: binary/compiled
  '.d', '.o', '.ko', '.obj', '.elf', '.lib', '.a', '.dll', '.so', '.exe', '.out'
]);

const EXCLUDE_FILENAMES = new Set([
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
  'LICENSE', '.gitignore', '.editorconfig', '.prettierrc'
]);

function shouldExclude(filePath) {
  const segments = filePath.split('/');
  const filename = segments[segments.length - 1];
  const ext = path.extname(filename).toLowerCase();

  // Check directory segments
  for (let i = 0; i < segments.length - 1; i++) {
    if (EXCLUDE_DIR_SEGMENTS.has(segments[i])) return true;
    if (segments[i].endsWith('.lock')) return true;
  }

  // Check filename
  if (EXCLUDE_FILENAMES.has(filename)) return true;
  if (filename.endsWith('.lock')) return true;
  if (/\.eslintrc/.test(filename)) return true;
  if (filename.endsWith('.log')) return true;

  // Check extension
  if (EXCLUDE_EXTENSIONS.has(ext)) return true;

  // Generated files
  if (filename.endsWith('.min.js') || filename.endsWith('.min.css')) return true;
  if (filename.endsWith('.map')) return true;
  if (/\.generated\./.test(filename)) return true;

  return false;
}

const filteredFiles = allFiles.filter(f => !shouldExclude(f));

// ── Step 3: Language Detection ────────────────────────────────────────────────
const EXT_TO_LANG = {
  '.ts': 'typescript', '.tsx': 'typescript',
  '.js': 'javascript', '.jsx': 'javascript',
  '.py': 'python',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.rb': 'ruby',
  '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.h': 'cpp', '.hpp': 'cpp',
  '.c': 'c',
  '.cs': 'csharp',
  '.swift': 'swift',
  '.kt': 'kotlin',
  '.php': 'php',
  '.vue': 'vue',
  '.svelte': 'svelte',
  '.sh': 'shell', '.bash': 'shell',
  '.ps1': 'powershell',
  '.bat': 'batch', '.cmd': 'batch',
  '.md': 'markdown', '.rst': 'markdown',
  '.yaml': 'yaml', '.yml': 'yaml',
  '.json': 'json',
  '.jsonc': 'jsonc',
  '.toml': 'toml',
  '.sql': 'sql',
  '.graphql': 'graphql', '.gql': 'graphql',
  '.proto': 'protobuf',
  '.tf': 'terraform', '.tfvars': 'terraform',
  '.html': 'html', '.htm': 'html',
  '.css': 'css', '.scss': 'css', '.sass': 'css', '.less': 'css',
  '.xml': 'xml',
  '.cfg': 'config', '.ini': 'config', '.env': 'config',
};

const BASENAME_TO_LANG = {
  'Dockerfile': 'dockerfile',
  'Makefile': 'makefile',
  'Jenkinsfile': 'jenkinsfile',
};

function detectLanguage(filePath) {
  const basename = path.basename(filePath);
  if (BASENAME_TO_LANG[basename]) return BASENAME_TO_LANG[basename];
  const ext = path.extname(basename).toLowerCase();
  if (EXT_TO_LANG[ext]) return EXT_TO_LANG[ext];
  return ext ? ext.slice(1).toLowerCase() : 'unknown';
}

// ── Step 4: File Category Detection ──────────────────────────────────────────
function detectCategory(filePath) {
  const basename = path.basename(filePath);
  const ext = path.extname(basename).toLowerCase();
  const segments = filePath.split('/');

  // Infra patterns (check first - highest priority for infra files)
  if (basename === 'Dockerfile' || basename.startsWith('docker-compose')) return 'infra';
  if (['.tf', '.tfvars'].includes(ext)) return 'infra';
  if (basename === 'Makefile' || basename === 'Jenkinsfile' || basename === 'Procfile' || basename === 'Vagrantfile') return 'infra';
  if (segments.includes('.github') && segments.includes('workflows')) return 'infra';
  if (basename === '.gitlab-ci.yml') return 'infra';
  if (segments.includes('.circleci')) return 'infra';
  if (filePath.endsWith('.k8s.yaml') || filePath.endsWith('.k8s.yml')) return 'infra';
  if (segments.includes('k8s') || segments.includes('kubernetes')) return 'infra';

  // Docs
  if (['.md', '.rst', '.txt'].includes(ext)) return 'docs';

  // Config
  if (['.yaml', '.yml', '.json', '.jsonc', '.toml', '.xml', '.cfg', '.ini', '.env'].includes(ext)) return 'config';
  if (['tsconfig.json', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod'].includes(basename)) return 'config';

  // Data
  if (['.sql', '.graphql', '.gql', '.proto', '.prisma', '.csv'].includes(ext)) return 'data';
  if (basename.endsWith('.schema.json')) return 'data';

  // Script
  if (['.sh', '.bash', '.ps1', '.bat'].includes(ext)) return 'script';

  // Markup
  if (['.html', '.htm', '.css', '.scss', '.sass', '.less'].includes(ext)) return 'markup';

  // Default: code
  return 'code';
}

// ── Step 5: Line Counting ─────────────────────────────────────────────────────
function countLines(files) {
  const counts = {};
  if (files.length === 0) return counts;

  const BATCH_SIZE = 100;
  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    const batch = files.slice(i, i + BATCH_SIZE);
    const absPaths = batch.map(f => path.join(PROJECT_ROOT, f));
    try {
      const result = spawnSync('wc', ['-l', ...absPaths], { encoding: 'utf8' });
      if (result.stdout) {
        const lines = result.stdout.trim().split('\n');
        for (const line of lines) {
          const match = line.trim().match(/^(\d+)\s+(.+)$/);
          if (match) {
            const absPath = match[2];
            const relPath = path.relative(PROJECT_ROOT, absPath);
            counts[relPath] = parseInt(match[1], 10);
          }
        }
      }
    } catch (e) {
      // If wc fails, default to 0
      for (const f of batch) counts[f] = 0;
    }
  }
  return counts;
}

const lineCounts = countLines(filteredFiles);

// ── Step 6: Framework Detection ───────────────────────────────────────────────
const frameworks = new Set();

// Python detection
const requirementsPath = path.join(PROJECT_ROOT, 'requirements.txt');
if (fs.existsSync(requirementsPath)) {
  const content = fs.readFileSync(requirementsPath, 'utf8');
  const pyFrameworks = ['django', 'fastapi', 'flask', 'sqlalchemy', 'alembic', 'celery',
    'pydantic', 'uvicorn', 'gunicorn', 'aiohttp', 'tornado', 'starlette', 'pytest',
    'hypothesis', 'channels', 'djangorestframework'];
  for (const line of content.split('\n')) {
    const pkg = line.trim().split(/[>=<!]/)[0].toLowerCase();
    if (pyFrameworks.includes(pkg)) frameworks.add(pkg);
    // Also detect numpy, scipy etc.
    if (pkg === 'numpy') frameworks.add('NumPy');
    if (pkg === 'scipy') frameworks.add('SciPy');
    if (pkg === 'sounddevice') frameworks.add('sounddevice');
    if (pkg === 'pyserial' || pkg === 'serial') frameworks.add('PySerial');
  }
}

// Infrastructure detection
const hasDockerfile = filteredFiles.some(f => path.basename(f) === 'Dockerfile');
const hasDockerCompose = filteredFiles.some(f => /docker-compose\.(yml|yaml)$/.test(f));
const hasTerraform = filteredFiles.some(f => f.endsWith('.tf'));
const hasGHActions = filteredFiles.some(f => f.includes('.github/workflows/'));
const hasGitLabCI = filteredFiles.some(f => path.basename(f) === '.gitlab-ci.yml');
const hasJenkinsfile = filteredFiles.some(f => path.basename(f) === 'Jenkinsfile');

if (hasDockerfile) frameworks.add('Docker');
if (hasDockerCompose) frameworks.add('Docker Compose');
if (hasTerraform) frameworks.add('Terraform');
if (hasGHActions) frameworks.add('GitHub Actions');
if (hasGitLabCI) frameworks.add('GitLab CI');
if (hasJenkinsfile) frameworks.add('Jenkins');

// ── Step 7: Complexity Estimation ─────────────────────────────────────────────
function estimateComplexity(count) {
  if (count <= 30) return 'small';
  if (count <= 150) return 'moderate';
  if (count <= 500) return 'large';
  return 'very-large';
}

// ── Step 8: Project Name ──────────────────────────────────────────────────────
let projectName = path.basename(PROJECT_ROOT);

// Try package.json
const pkgJsonPath = path.join(PROJECT_ROOT, 'package.json');
if (fs.existsSync(pkgJsonPath)) {
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
    if (pkg.name) projectName = pkg.name;
  } catch (_) {}
}

// Try pyproject.toml
const pyprojectPath = path.join(PROJECT_ROOT, 'pyproject.toml');
if (fs.existsSync(pyprojectPath)) {
  try {
    const content = fs.readFileSync(pyprojectPath, 'utf8');
    const match = content.match(/^\[project\][^[]*name\s*=\s*"([^"]+)"/ms);
    if (match) projectName = match[1];
  } catch (_) {}
}

// README head
let readmeHead = '';
const readmePath = path.join(PROJECT_ROOT, 'README.md');
if (fs.existsSync(readmePath)) {
  try {
    const lines = fs.readFileSync(readmePath, 'utf8').split('\n').slice(0, 10);
    readmeHead = lines.join('\n');
  } catch (_) {}
}

// raw description
let rawDescription = '';
if (fs.existsSync(pkgJsonPath)) {
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
    if (pkg.description) rawDescription = pkg.description;
  } catch (_) {}
}

// ── Step 9: Import Resolution ─────────────────────────────────────────────────
const fileSet = new Set(filteredFiles);

function resolveRelativeImport(fromFile, importPath, extensions) {
  const fromDir = path.dirname(fromFile);
  const resolved = path.normalize(path.join(fromDir, importPath));
  if (fileSet.has(resolved)) return resolved;
  for (const ext of extensions) {
    const candidate = resolved + ext;
    if (fileSet.has(candidate)) return candidate;
    const indexCandidate = path.join(resolved, `index${ext}`);
    if (fileSet.has(indexCandidate)) return indexCandidate;
  }
  return null;
}

const JS_TS_EXTENSIONS = ['.ts', '.tsx', '.js', '.jsx'];
const PY_EXTENSIONS = ['.py'];

function extractPythonImports(content, fromFile) {
  const imports = [];
  const fromDir = path.dirname(fromFile);

  // Relative imports: from .x import y, from ..x import y
  const relativeFromRe = /^from\s+(\.+)([^\s]*)\s+import\s+(.+)$/gm;
  let m;
  while ((m = relativeFromRe.exec(content)) !== null) {
    const dots = m[1].length;
    const modPath = m[2];
    const names = m[3].split(',').map(s => s.trim().split(' ')[0]);

    let baseDir = fromDir;
    for (let i = 1; i < dots; i++) baseDir = path.dirname(baseDir);

    const modFilePath = modPath ? path.join(baseDir, modPath.replace(/\./g, '/')) : baseDir;
    const candidates = [
      modFilePath + '.py',
      path.join(modFilePath, '__init__.py')
    ];
    for (const c of candidates) {
      const rel = path.normalize(c);
      if (fileSet.has(rel)) { imports.push(rel); break; }
    }
  }

  // Absolute imports: import a.b.c and from a.b.c import x
  const absoluteImportRe = /^import\s+([\w.]+)/gm;
  while ((m = absoluteImportRe.exec(content)) !== null) {
    const modPath = m[1].replace(/\./g, '/');
    const candidates = [modPath + '.py', path.join(modPath, '__init__.py')];
    for (const c of candidates) {
      if (fileSet.has(c)) { imports.push(c); break; }
    }
  }

  const absoluteFromRe = /^from\s+([\w][\w.]*)\s+import\s+(.+)$/gm;
  while ((m = absoluteFromRe.exec(content)) !== null) {
    const modPath = m[1].replace(/\./g, '/');
    const names = m[2].split(',').map(s => s.trim().split(' ')[0]);
    const candidates = [modPath + '.py', path.join(modPath, '__init__.py')];
    let matched = false;
    for (const c of candidates) {
      if (fileSet.has(c)) {
        imports.push(c);
        matched = true;
        // If it's __init__.py, also probe submodules
        if (c.endsWith('__init__.py')) {
          for (const name of names) {
            const sub1 = modPath + '/' + name + '.py';
            const sub2 = modPath + '/' + name + '/__init__.py';
            if (fileSet.has(sub1)) imports.push(sub1);
            else if (fileSet.has(sub2)) imports.push(sub2);
          }
        }
        break;
      }
    }
  }

  return [...new Set(imports)];
}

function extractCImports(content, fromFile) {
  const imports = [];
  const fromDir = path.dirname(fromFile);
  const includeRe = /#include\s+["<]([^">]+)[">]/g;
  let m;
  while ((m = includeRe.exec(content)) !== null) {
    const incPath = m[1];
    const probes = [
      path.normalize(path.join(fromDir, incPath)),
      path.normalize(path.join('include', incPath)),
      path.normalize(path.join('src', incPath)),
      incPath,
    ];
    for (const p of probes) {
      if (fileSet.has(p)) { imports.push(p); break; }
    }
  }
  return [...new Set(imports)];
}

function extractJsTsImports(content, fromFile) {
  const imports = [];
  const importRe = /(?:import\s+(?:.*?\s+from\s+)?|require\s*\(\s*)['"]([^'"]+)['"]/g;
  let m;
  while ((m = importRe.exec(content)) !== null) {
    const imp = m[1];
    if (!imp.startsWith('.')) continue; // Skip non-relative
    const resolved = resolveRelativeImport(fromFile, imp, JS_TS_EXTENSIONS);
    if (resolved) imports.push(resolved);
  }
  return [...new Set(imports)];
}

const importMap = {};
for (const file of filteredFiles) {
  const category = detectCategory(file);
  if (category !== 'code') {
    importMap[file] = [];
    continue;
  }
  const lang = detectLanguage(file);
  const absPath = path.join(PROJECT_ROOT, file);
  let content = '';
  try { content = fs.readFileSync(absPath, 'utf8'); } catch (_) { importMap[file] = []; continue; }

  let resolved = [];
  if (lang === 'python') resolved = extractPythonImports(content, file);
  else if (lang === 'c' || lang === 'cpp') resolved = extractCImports(content, file);
  else if (lang === 'typescript' || lang === 'javascript') resolved = extractJsTsImports(content, file);

  importMap[file] = resolved;
}

// ── Assemble output ───────────────────────────────────────────────────────────
const fileObjects = filteredFiles.map(f => ({
  path: f,
  language: detectLanguage(f),
  sizeLines: lineCounts[f] !== undefined ? lineCounts[f] : 0,
  fileCategory: detectCategory(f),
})).sort((a, b) => a.path.localeCompare(b.path));

const allLanguages = [...new Set(fileObjects.map(f => f.language))].sort();

const output = {
  scriptCompleted: true,
  name: projectName,
  rawDescription,
  readmeHead,
  languages: allLanguages,
  frameworks: [...frameworks].sort(),
  files: fileObjects,
  totalFiles: fileObjects.length,
  filteredByIgnore: 0,
  estimatedComplexity: estimateComplexity(fileObjects.length),
  importMap,
};

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2), 'utf8');
process.exit(0);
