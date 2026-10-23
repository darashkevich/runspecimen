// Keep the process-group leader alive until the owner has completed cleanup.
// IPC reports the command outcome; the supervisor exits only on group SIGKILL
// or loss of its owning parent. Never execute caller text through a shell.
import {spawn,spawnSync} from 'node:child_process';
const [command,...argv]=JSON.parse(process.argv[2]);
process.on('SIGTERM',()=>{});
process.on('disconnect',()=>{process.kill(-process.pid,'SIGKILL');});
const child=spawn(command,argv,{stdio:['ignore','inherit','inherit']});
let error;
child.on('error',e=>{error={code:e.code,message:e.message};});
child.on('close',(code,signal)=>{
  // Membership is only for honest result classification, never signal authority.
  const result=spawnSync('/bin/ps',['-axo','pid=,pgid=,stat='],{encoding:'utf8',timeout:1000});
  const others=result.status!==0 || result.stdout.split('\n').some(line=>{
    const [pid,pgid,state]=line.trim().split(/\s+/);
    return Number(pgid)===process.pid && Number(pid)!==process.pid && Number(pid)!==result.pid && !state?.startsWith('Z');
  });
  process.send?.({type:'command-exit',code,signal,error,others});
});
