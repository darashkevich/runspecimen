import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {runCli} from '../lib/cli.js';

for(const mode of ['missing','slow'])test(`QA2-P2-03 actual ${mode} ps outcome preserves successful CLI exit`,async()=>{
  const dir=mkdtempSync(join(tmpdir(),'rs-qa2-ps-'));
  const hook=join(dir,'ps-fixture.mjs');
  writeFileSync(hook,`
import {createRequire,syncBuiltinESMExports} from 'node:module';
if(process.argv[1]?.endsWith('/group-supervisor.js')){
  const cp=createRequire(import.meta.url)('node:child_process');const original=cp.spawnSync;
  cp.spawnSync=function(command,args,options){
    if(command==='/bin/ps')return ${mode==='missing'
      ? "original('/nonexistent-qa2-ps',args,options)"
      : "original(process.execPath,['-e','setTimeout(()=>{},2000)'],options)"};
    return original(command,args,options);
  };
  syncBuiltinESMExports();
}
`);
  const previous=process.env.NODE_OPTIONS;
  process.env.NODE_OPTIONS='--import='+pathToFileURL(hook).href;
  try {
    const result=await runCli({command:'/usr/bin/true',argv:[],cwd:dir,timeoutMs:5000,maxOutputBytes:1024,graceMs:20});
    console.log(JSON.stringify({mode,result}));
    assert.equal(result.exitCode,0,'failed membership classification must not replace actual CLI exit 0');
    assert.doesNotMatch(result.text,/exited leaving child processes/);
    assert.equal(result.cliExitCode,0);assert.equal(result.cliSignal,null);assert.equal(result.cliOutcomeObserved,true);assert.equal(result.cleanupClassification,'unavailable');
  }finally{
    if(previous===undefined)delete process.env.NODE_OPTIONS;else process.env.NODE_OPTIONS=previous;
    rmSync(dir,{recursive:true,force:true});
  }
});
