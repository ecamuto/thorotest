"use strict";
/** Terminal output helpers: color only on a TTY (or FORCE_COLOR), plain otherwise. */

const useColor =
  process.env.FORCE_COLOR === "1" ||
  (process.stdout.isTTY && process.env.NO_COLOR === undefined && process.env.TERM !== "dumb");

const wrap = (code) => (s) => (useColor ? `\x1b[${code}m${s}\x1b[0m` : String(s));

const red = wrap("31");
const green = wrap("32");
const yellow = wrap("33");
const dim = wrap("2");
const bold = wrap("1");

function printJson(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
}

module.exports = { red, green, yellow, dim, bold, printJson };
