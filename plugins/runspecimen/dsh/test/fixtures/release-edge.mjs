import {spawn} from 'node:child_process';
import {writeFileSync,writeSync} from 'node:fs';
const [mode,path]=process.argv.slice(2);
if(mode==='cooperative-tree') {
 const child=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});process.send('ready');setInterval(()=>{},10000);"],{stdio:['ignore','ignore','ignore','ipc']});
 process.on('SIGTERM',()=>process.exit(0));child.on('message',()=>writeFileSync(path,JSON.stringify({pid:process.pid,descendant:child.pid})));
 setInterval(()=>{},10000);
} else if(mode==='no-url') {writeFileSync(path,JSON.stringify({pid:process.pid}));setInterval(()=>{},10000);}
else if(mode==='stderr-tail') {writeSync(2,'e'.repeat(2048));writeSync(2,'IMPORTANT_LATE_ERROR');}
else if(mode==='stderr-size') {writeSync(2,'e'.repeat(2048));}
