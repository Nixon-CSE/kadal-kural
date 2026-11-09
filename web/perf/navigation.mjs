// Click-to-content: click each nav link and time until the page heading is on screen.
// node --experimental-websocket web/perf/navigation.mjs http://localhost:8000
import { spawn } from "node:child_process"; import { mkdtempSync } from "node:fs"; import { tmpdir } from "node:os"; import { join } from "node:path";
const [base] = process.argv.slice(2);
const port = 9300 + Math.floor(Math.random()*90);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new","--use-angle=metal","--enable-gpu","--ignore-gpu-blocklist",`--remote-debugging-port=${port}`,`--user-data-dir=${mkdtempSync(join(tmpdir(),"kkn-"))}`,"about:blank"],{stdio:"ignore"});
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms)); let t;
for (let i=0;i<50&&!t;i++){try{t=(await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(x=>x.type==="page")}catch{await sleep(200)}}
const ws=new WebSocket(t.webSocketDebuggerUrl); await new Promise(r=>ws.onopen=r); let id=0; const p=new Map();
ws.onmessage=m=>{const d=JSON.parse(m.data); if(p.has(d.id)){p.get(d.id)(d.result);p.delete(d.id)}};
const send=(method,params={})=>new Promise(r=>{const i=++id;p.set(i,r);ws.send(JSON.stringify({id:i,method,params}))});
await send("Emulation.setDeviceMetricsOverride",{width:1440,height:900,deviceScaleFactor:2,mobile:false});
await send("Page.navigate",{url:base+"/"}); await sleep(5000);
const targets=[["Ledger","Ledger"],["Buyers","Buyers"],["Insights","Insights"],["Phone line","Phone line"],["Desk","Ready"],["Home","Every spoken"]];
const times=[];
for (const [link, marker] of targets) {
  const r=await send("Runtime.evaluate",{awaitPromise:true,returnByValue:true,expression:`new Promise(res=>{const a=[...document.querySelectorAll('header nav a')].find(x=>x.textContent.trim().startsWith(${JSON.stringify(link)}));const t0=performance.now();a.click();const chk=()=>{const h=[...document.querySelectorAll('main h1, main p')].find(e=>e.textContent.includes(${JSON.stringify(marker)}) && getComputedStyle(e.closest('main > div')||e).opacity>0.9);if(h)res(Math.round(performance.now()-t0));else if(performance.now()-t0>4000)res(-1);else requestAnimationFrame(chk)};requestAnimationFrame(chk);})`});
  times.push(r.result.value); console.log(`  → ${link.padEnd(11)} ${r.result.value} ms`); await sleep(800);
}
const ok=times.filter(x=>x>=0); console.log(`  median ${ok.sort((a,b)=>a-b)[Math.floor(ok.length/2)]} ms`);
chrome.kill(); process.exit(0);
