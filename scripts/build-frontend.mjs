// ThoroTest frontend production build.
//
// The frontend is intentionally bundler-free at the module level: files are
// classic scripts sharing top-level globals, loaded in the order declared in
// index.html. This build keeps that architecture and only does what
// production serving needs:
//
//   1. Transpile every .jsx to plain .js (esbuild, React.createElement) and
//      minify — no more in-browser Babel.
//   2. Minify the plain .js files (api.js, data.js, i18n.js, locales).
//   3. Copy static assets (index.html, styles.css, fonts.css, fonts/).
//   4. Vendor the React production UMD builds from node_modules — no CDN.
//   5. Stamp ?v=<hash> on local script/css URLs in index.html (cache busting).
//
// Output: frontend/dist/ — served by the backend. Run with --watch to rebuild
// .jsx/.js on change during development.
import { build, context } from "esbuild";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(root, "frontend");
const outDir = path.join(srcDir, "dist");
const watch = process.argv.includes("--watch");

function listFiles(dir, ext) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => path.join(dir, f));
}

const jsxEntries = [
  path.join(srcDir, "app.jsx"),
  ...listFiles(path.join(srcDir, "components"), ".jsx"),
  ...listFiles(path.join(srcDir, "views"), ".jsx"),
];

const jsEntries = [
  path.join(srcDir, "react-globals.js"),
  path.join(srcDir, "api.js"),
  path.join(srcDir, "data.js"),
  path.join(srcDir, "i18n.js"),
  ...listFiles(path.join(srcDir, "locales"), ".js"),
];

// Scoping must match how these files historically executed:
//  - .jsx files ran under Babel standalone, each in its own function scope —
//    they share state exclusively through window.X and every file declares
//    its own `const { useState … } = React`. Wrap each in an IIFE, otherwise
//    those top-level consts collide as classic scripts (SyntaxError).
//  - plain .js files ran as classic scripts with genuinely global top-level
//    bindings — keep script format (no wrapper) for them.
const commonOpts = {
  outdir: outDir,
  outbase: srcDir,
  bundle: false,
  minify: true,
  target: "es2019",
  logLevel: "info",
};

const jsxOpts = {
  ...commonOpts,
  entryPoints: jsxEntries,
  format: "iife",
  jsx: "transform",
  loader: { ".jsx": "jsx" },
};

const jsOpts = {
  ...commonOpts,
  entryPoints: jsEntries,
};

const staticFiles = ["styles.css", "fonts.css"];
const staticDirs = ["fonts"];

const vendorFiles = [
  ["node_modules/react/umd/react.production.min.js", "vendor/react.production.min.js"],
  ["node_modules/react-dom/umd/react-dom.production.min.js", "vendor/react-dom.production.min.js"],
];

function copyStatic() {
  for (const f of staticFiles) {
    fs.copyFileSync(path.join(srcDir, f), path.join(outDir, f));
  }
  for (const d of staticDirs) {
    fs.cpSync(path.join(srcDir, d), path.join(outDir, d), { recursive: true });
  }
  for (const [from, to] of vendorFiles) {
    const dest = path.join(outDir, to);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(root, from), dest);
  }
}

function writeIndexHtml() {
  // Stamp a build hash on local asset URLs so browsers pick up new releases.
  const hash = createHash("sha256");
  for (const f of [...jsxEntries, ...jsEntries, path.join(srcDir, "styles.css"), path.join(srcDir, "index.html")]) {
    hash.update(fs.readFileSync(f));
  }
  const v = hash.digest("hex").slice(0, 10);
  let html = fs.readFileSync(path.join(srcDir, "index.html"), "utf8");
  html = html.replace(/(src|href)="((?!https?:|\/\/)[^"]+\.(?:js|css))"/g, `$1="$2?v=${v}"`);
  fs.writeFileSync(path.join(outDir, "index.html"), html);
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
copyStatic();
writeIndexHtml();

if (watch) {
  const ctxJsx = await context(jsxOpts);
  const ctxJs = await context(jsOpts);
  await ctxJsx.watch();
  await ctxJs.watch();
  // Re-copy static assets and re-stamp index.html when they change.
  for (const f of [...staticFiles, "index.html"]) {
    fs.watch(path.join(srcDir, f), () => {
      try {
        copyStatic();
        writeIndexHtml();
        console.log(`[static] ${f} updated`);
      } catch (e) {
        console.error(e);
      }
    });
  }
  console.log("Watching frontend/ — Ctrl-C to stop.");
} else {
  await build(jsxOpts);
  await build(jsOpts);
  console.log(`Built ${jsxEntries.length + jsEntries.length} scripts → frontend/dist/`);
}
