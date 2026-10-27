import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,writeFileSync,readFileSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as pause} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {apply} from '../lib/index.js';

const python=process.env.QA2_PYTHON ?? execFileSync('python3',['-c','import sys; print(sys.executable)'],{encoding:'utf8'}).trim();
const source=process.env.QA2_CLI_SOURCE ?? fileURLToPath(new URL('../../../../',import.meta.url));

for(const mode of ['timeout','cancel'])test(`QA2-P1-01 real registered run ${mode} never reports a clean orphan`,async()=>{
  const ws=mkdtempSync(join(tmpdir(),'rs-qa2-dsh-'));
  let pid;
  const env={...process.env,PYTHONPATH:source+'/src'};
  const saved=process.env.PYTHONPATH;process.env.PYTHONPATH=source+'/src';
  try {
    execFileSync(python,['-c',`
import sys,pathlib
from tests.helpers import base_contract,write_contract,approve
ws=pathlib.Path(sys.argv[1]);(ws/'work').mkdir();(ws/'outputs').mkdir()
(ws/'work/job.py').write_text("import os,signal,time\\nfrom pathlib import Path\\nfor sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): signal.signal(sig,signal.SIG_IGN)\\nPath('outputs/contract.pid').write_text(str(os.getpid()))\\nwhile True: time.sleep(.1)\\n")
c=write_contract(ws,'contract.json',base_contract(caps={'wall_timeout_sec':8,'stdout_max_bytes':1024,'stderr_max_bytes':1024}));approve(ws,c)
`,ws],{cwd:source,env});
    const command=join(ws,'cli');
    writeFileSync(command,`#!/bin/sh\nexec ${python} -m runspecimen "$@"\n`,{mode:0o700});
    const tools=[];
    apply({tools:{register:t=>tools.push(t)},systemPrompt:{section(){},getSectionOrder(){return 1;}}},
      {command,cwd:ws,timeoutMs:mode==='timeout'?4000:10000,graceMs:500});
    const controller=new AbortController();
    const pending=tools.find(t=>t.name==='runspecimen_run').execute({workspace:ws,contract:join(ws,'contract.json')},{signal:controller.signal});
    const deadline=Date.now()+5000;
    while(!existsSync(join(ws,'outputs/contract.pid'))){assert.ok(Date.now()<deadline,'contract readiness deadline');await pause(10);}
    pid=Number(readFileSync(join(ws,'outputs/contract.pid'),'utf8'));
    if(mode==='cancel')controller.abort();
    const result=await pending;
    let alive=true;try{process.kill(pid,0);}catch(e){if(e.code==='ESRCH')alive=false;else throw e;}
    const status=JSON.parse(execFileSync(command,['status','--workspace',ws,'--campaign-id','camp','--run-id','run-a'],{env,encoding:'utf8'}));
    console.log(JSON.stringify({mode,result,alive,status}));
    assert.equal(result.ok,false);
    assert.ok(!alive || result.cleanupFailed===true,'must not report confirmed cleanup while the approved contract is alive');
    if(status.phase==='running')assert.equal(result.cleanupFailed,true,'phase running must remain explicitly unresolved');
    if(process.env.QA2_EXPECT_STOP==='1'){
      assert.equal(alive,false,'signal-aware CLI must stop the approved contract');
      assert.equal(status.phase,'failed');
      assert.equal(status.state.run_result,'interrupted');
      assert.equal(status.workspace_lease_held_by_other,false);
    }
  } finally {
    if(saved===undefined)delete process.env.PYTHONPATH;else process.env.PYTHONPATH=saved;
    if(pid){try{process.kill(-pid,'SIGKILL');}catch(e){if(e.code!=='ESRCH')throw e;}}
    rmSync(ws,{recursive:true,force:true});
  }
});
