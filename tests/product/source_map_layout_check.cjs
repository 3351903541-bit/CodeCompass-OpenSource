const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/product/source-map.js'),'utf8'),context);
// Source/file ordering deliberately differs from the ten-step study sequence.
const files=['a.py','b.py'].map(p=>({id:'file:'+p,path:p,kind:'file',steps:[],selected:true}));
const nodes=[...files];
for(let step=10;step>=1;step--){const f=files[step%2];f.steps.push(step);nodes.push({id:'s'+step,kind:'symbol',label:'step'+step,path:f.path,steps:[step],selected:true,span:{start_line:110-step}});}
nodes.push({id:'extra',kind:'symbol',label:'extra',path:'a.py',steps:[],selected:false,span:{start_line:1}});
for(const expanded of [new Set(),new Set(['a.py','b.py'])]){
 const layout=context.sourceMapPositions({nodes},files,expanded,'all');
 for(let step=1;step<10;step++){
  const a=layout.positions.get('s'+step),b=layout.positions.get('s'+(step+1));
  assert(a.y+a.h<b.y,'Study nodes must progress downward without overlap, across files too');
  const arrow=context.sourceMapStudyArrow(a,b).match(/^M([\d.]+),([\d.]+) L([\d.]+),([\d.]+)$/);
  assert(arrow,'Study connections must be straight segments');
  assert.equal(arrow[1],arrow[3],'Study arrows must stay in their vertical lane');
  assert(Number(arrow[4])>Number(arrow[2]),'Study arrows must point down');
 }
 if(expanded.size)assert(layout.positions.get('extra').y>layout.positions.get('s10').y,'Expanded source must not interrupt the numbered sequence');
 assert.equal(layout.positions.get('s1').n.steps[0],1);
}
const filtered=context.sourceMapPositions({nodes},[files[0]],new Set(),'route');
assert([...filtered.positions.values()].every(p=>p.n.path==='a.py'));
console.log('PASS: ten-step order, cross-file layout, forward arrows, expansion and filtering');
