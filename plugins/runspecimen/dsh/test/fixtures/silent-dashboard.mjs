#!/usr/bin/env node
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
const workspace=process.argv[process.argv.indexOf('--workspace')+1];
console.log(`fixture pid ${process.pid}`);
writeFileSync(join(workspace,'ready'),String(process.pid));
setInterval(()=>{},1000);
