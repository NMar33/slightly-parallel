const ot=require('opentype.js'),fs=require('fs');
const faces={sg:'fonts/Schibsted-700.ttf',bs:'fonts/BigShouldersDisplay-700.ttf',sg5:'fonts/Schibsted-500.ttf'};
const out={};
for(const [k,f] of Object.entries(faces)){
  const font=ot.loadSync(f); const upm=font.unitsPerEm;
  const m=(g)=>{const b=font.charToGlyph(g).getBoundingBox();return {x1:b.x1/upm,x2:b.x2/upm,y1:b.y1/upm,y2:b.y2/upm}};
  const metrics={upm,asc:m('l').y2, xh:m('x').y2, cap:m('H').y2, desc:m('p').y1, os2:{asc:font.tables.os2.sTypoAscender/upm,desc:font.tables.os2.sTypoDescender/upm}};
  const lay=(text,tr=0)=>{const gs=font.stringToGlyphs(text);let x=0;const recs=[];for(let i=0;i<gs.length;i++){const g=gs[i];const p=g.getPath(0,0,1);const b=g.getBoundingBox();recs.push({ch:text[i],x,adv:g.advanceWidth/upm,d:p.toPathData(4),bb:{x1:b.x1/upm,x2:b.x2/upm,y1:-b.y2/upm,y2:-b.y1/upm}});x+=g.advanceWidth/upm+tr;if(i<gs.length-1)x+=font.getKerningValue(g,gs[i+1])/upm;}return {recs,width:x-tr};};
  out[k]={metrics,lower:lay('slightly parallel',-0.015),upper:lay('SLIGHTLY PARALLEL',0.01),parallel:lay('parallel',-0.015),PARALLEL:lay('PARALLEL',0.01),s:lay('s'),p:lay('p')};
}
fs.writeFileSync('out/metrics.json',JSON.stringify(out));
console.log(Object.keys(out), JSON.stringify(out.bs.metrics), JSON.stringify(out.sg.metrics));
// JetBrains Mono 500: every printable ASCII glyph as a path (for labels without a font)
{ const font=ot.loadSync('fonts/JetBrainsMono-500.ttf'); const upm=font.unitsPerEm; const g={};
  for(let c=32;c<127;c++){const ch=String.fromCharCode(c);const gl=font.charToGlyph(ch);g[ch]={d:gl.getPath(0,0,1).toPathData(4),adv:gl.advanceWidth/upm};}
  for(const ch of ['·','°','—','∥','…']){const gl=font.charToGlyph(ch);g[ch]={d:gl.getPath(0,0,1).toPathData(4),adv:gl.advanceWidth/upm};}
  out.mono=g; fs.writeFileSync('out/metrics.json',JSON.stringify(out)); console.log('mono glyphs',Object.keys(g).length); }
