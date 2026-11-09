// Scroll jank on the real GPU: scroll 30 px per frame for 3 s; frame-time stats.
// node --experimental-websocket web/perf/scroll-jank.mjs http://localhost:8000 / /desk
import { spawn } from "node:child_process"; import { mkdtempSync } from "node:fs"; import { tmpdir } from "node:os"; import { join } from "node:path";
const [base, ...paths] = process.argv.slice(2);
const port = 9500 + Math.floor(Math.random()*90);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new","--use-angle=metal","--enable-gpu","--ignore-gpu-blocklist",`--remote-debugging-port=${port}`,`--user-data-dir=${mkdtempSync(join(tmpdir(),"kkj-"))}`,"about:blank"],{stdio:"ignore"});
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms)); let t;
for (let i=0;i<50&&!t;i++){try{t=(await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(x=>x.type==="page")}catch{await sleep(200)}}
const ws=new WebSocket(t.webSocketDebuggerUrl); await new Promise(r=>ws.onopen=r); let id=0; const p=new Map();
ws.onmessage=m=>{const d=JSON.parse(m.data); if(p.has(d.id)){p.get(d.id)(d.result);p.delete(d.id)}};
const send=(method,params={})=>new Promise(r=>{const i=++id;p.set(i,r);ws.send(JSON.stringify({id:i,method,params}))});
await send("Emulation.setDeviceMetricsOverride",{width:1440,height:900,deviceScaleFactor:2,mobile:false});
for (const path of paths) {
  const runs=[];
  for (let rep=0; rep<3; rep++) {
    await send("Page.navigate",{url:base+path}); await sleep(5000);
    const r=await send("Runtime.evaluate",{awaitPromise:true,returnByValue:true,expression:`new Promise(res=>{const ts=[];let last=performance.now();const t0=last;const max=document.documentElement.scrollHeight-innerHeight;let y=0,dir=1;const f=()=>{const now=performance.now();ts.push(now-last);last=now;y+=30*dir;if(y>=max||y<=0)dir*=-1;scrollTo(0,y);if(now-t0<3000)requestAnimationFrame(f);else res(ts.slice(1));};requestAnimationFrame(f);})`});
    runs.push(...r.result.value);
  }
  const s=[...runs].sort((a,b)=>a-b); const q=(x)=>s[Math.floor(s.length*x)].toFixed(1);
  console.log(`${path.padEnd(10)} frames ${String(runs.length).padStart(4)}  median ${q(0.5)} ms  p95 ${q(0.95)} ms  janky(>25ms) ${(100*runs.filter(x=>x>25).length/runs.length).toFixed(1)}%`);
}
chrome.kill(); process.exit(0);
