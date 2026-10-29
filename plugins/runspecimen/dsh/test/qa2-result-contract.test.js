import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';
const runtime=process.env.QA2_RUNTIME_URL ?? new URL('../',import.meta.url).href;
const {apply}=await import(new URL('lib/index.js',runtime));
const {runCli}=await import(new URL('lib/cli.js',runtime));

function tools(config={}){
  const ts=[];apply({tools:{register:t=>ts.push(t)},systemPrompt:{section(){},getSectionOrder(){return 1;}}},config);
  return ts;
}

test('QA2-P3-02 compiled result schema rejects an empty success/failure record',()=>{
  const schema=tools()[0].output.schema;
  assert.ok(validateJsonSchemaValue(schema,{}).length>0);
  assert.deepEqual(validateJsonSchemaValue(schema,{ok:false,exitCode:-1,truncated:false,output:'refused'}),[]);
});

test('QA2-P3-02 registered missing CLI returns a typed spawn failure',async()=>{
  const t=tools({command:'/nonexistent-qa2-cli',timeoutMs:3000,graceMs:20}).find(t=>t.name==='runspecimen_about');
  const r=await t.execute({},{});
  assert.equal(r.ok,false);assert.equal(r.exitCode,-1);assert.equal(r.terminationKind,'spawn');assert.match(r.output,/not found/);
  assert.deepEqual(validateJsonSchemaValue(t.output.schema,r),[]);
});

test('QA2-P3-02 dashboard startup failure carries typed cause fields',async()=>{
  const dir=mkdtempSync(join(tmpdir(),'rs-qa2-dashboard-'));
  const command=join(dir,'silent.mjs');
  writeFileSync(command,`#!${process.execPath}\nsetInterval(()=>{},1000);\n`,{mode:0o700});
  try{
    const t=tools({command,timeoutMs:500,graceMs:20}).find(t=>t.name==='runspecimen_dashboard');
    const r=await t.execute({workspace:dir,contract:'fixture.json'},{});
    assert.equal(r.ok,false);assert.equal(r.timedOut,true);assert.equal(r.triggerKind,'timeout');assert.equal(r.terminationKind,'timeout');
    assert.deepEqual(validateJsonSchemaValue(t.output.schema,r),[]);
  }finally{rmSync(dir,{recursive:true,force:true});}
});

test('QA2-P3-02 dsh-tools peer matches the tested direct dependency',()=>{
  const p=JSON.parse(readFileSync(new URL('package.json',runtime),'utf8'));
  assert.equal(p.peerDependencies['@deepseek-ai/dsh-tools'],p.dependencies['@deepseek-ai/dsh-tools']);
});

for(const mode of ['fast','signal'])test(`QA2-P3-01/P3-02 known-empty membership ${mode}`,async()=>{
  const dir=mkdtempSync(join(tmpdir(),'rs-qa2-membership-'));
  const hook=join(dir,'empty-group.mjs');
  writeFileSync(hook,`
import {createRequire,syncBuiltinESMExports} from 'node:module';
if(process.argv[1]?.endsWith('/group-supervisor.js')){
const cp=createRequire(import.meta.url)('node:child_process');const original=cp.spawnSync;
cp.spawnSync=(command,args,options)=>command==='/bin/ps'?{status:0,stdout:'',stderr:''}:original(command,args,options);
syncBuiltinESMExports();}
`);
  const previous=process.env.NODE_OPTIONS;process.env.NODE_OPTIONS='--import='+pathToFileURL(hook).href;
  try{
    const start=Date.now();
    const r=await runCli({command:process.execPath,argv:['-e',mode==='fast'?'process.exit(0)':"process.kill(process.pid,'SIGTERM')"],cwd:dir,timeoutMs:5000,maxOutputBytes:1024});
    console.log(JSON.stringify({mode,elapsedMs:Date.now()-start,result:r}));
    if(mode==='fast'){assert.equal(r.exitCode,0);assert.ok(Date.now()-start<1000,'known-empty group must not wait the 2000ms grace');}
    else{assert.equal(r.cliSignal,'SIGTERM');assert.match(r.text,/SIGTERM/);assert.equal(r.cliOutcomeObserved,true);}
  }finally{
    if(previous===undefined)delete process.env.NODE_OPTIONS;else process.env.NODE_OPTIONS=previous;
    rmSync(dir,{recursive:true,force:true});
  }
});
