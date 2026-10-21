#!/usr/bin/env node
process.stdout.write(JSON.stringify({cwd:process.cwd(),argv:process.argv.slice(2)}));
