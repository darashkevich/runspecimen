// Keep the process-group leader alive until the owner has completed cleanup.
// IPC reports the command outcome. Exit after acknowledged cleanup when the
// group is known empty; otherwise retain group-owned escalation authority.
import {spawn,spawnSync} from 'node:child_process';
const [command,...argv]=JSON.parse(process.argv[2]);
process.on('SIGTERM',()=>{});
// Only this executing process may signal its own group. No numeric target is
// accepted over IPC; parent-side exit fields never grant signal authority.
let cleaning=false,commandDone=false,classification='unavailable';
function cleanup(graceMs) {
  if(cleaning)return;
  cleaning=true;
  if(commandDone && classification==='none')process.exit(0);
  process.kill(-process.pid,'SIGTERM');
  setTimeout(()=>process.kill(-process.pid,'SIGKILL'),graceMs);
}
process.on('message',message=>{
  if(message?.type==='cleanup' && Number.isSafeInteger(message.graceMs) && message.graceMs>=0 && message.graceMs<=3_600_000)
    process.send?.({type:'cleanup-ack',requestId:message.requestId},error=>{if(!error)cleanup(message.graceMs);});
});
// Parent loss cannot leave a cleanup escalation or descendants abandoned.
process.on('disconnect',()=>{process.kill(-process.pid,'SIGKILL');});
const child=spawn(command,argv,{stdio:['ignore','inherit','inherit']});
let error;
child.on('error',e=>{error={code:e.code,message:e.message};});
child.on('close',(code,signal)=>{
  commandDone=true;
  // Membership is only for honest result classification, never signal authority.
  // During cleanup, publish the real outcome without blocking its deadline on ps.
  if(!cleaning){
    const result=spawnSync('/bin/ps',['-axo','pid=,pgid=,stat='],{encoding:'utf8',timeout:1000});
    if(result.status===0){
      const others=result.stdout.split('\n').some(line=>{
        const [pid,pgid,state]=line.trim().split(/\s+/);
        return Number(pgid)===process.pid && Number(pid)!==process.pid && Number(pid)!==result.pid && !state?.startsWith('Z');
      });
      classification=others?'leftovers':'none';
    }
  }
  process.send?.({type:'command-exit',code,signal,error,classification,others:classification==='leftovers'});
});
