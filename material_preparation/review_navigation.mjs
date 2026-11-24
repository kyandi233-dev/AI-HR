import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const [inputPath,outDir]=process.argv.slice(2);
const data=JSON.parse(await fs.readFile(inputPath,'utf8'));
// Existing layout was inspected from the user's screenshot and the workbook records.
// Rebuild only the authorized summary; no embedded JD/resume worksheets.
const w=Workbook.create();
const s=w.worksheets.add('职业汇总');
s.showGridLines=false;s.tabColor='#234E70';
function column(n){let r='';while(n){n--;r=String.fromCharCode(65+n%26)+r;n=Math.floor(n/26);}return r;}
const end=column(data.headers.length),last=data.rows.length+1;
const rows=data.rows.map(row=>row.map(v=>v&&typeof v==='object'&&v.date?new Date(v.date):v));
s.getRange(`A1:${end}${last}`).values=[data.headers,...rows];
s.getRange(`A1:${end}${last}`).format.font={name:'Microsoft YaHei',size:11,color:'#1F2937'};
s.getRange(`A1:${end}${last}`).format.verticalAlignment='center';
s.getRange(`A1:${end}${last}`).format.wrapText=true;
s.getRange(`A1:${end}1`).format={fill:'#234E70',font:{name:'Microsoft YaHei',size:11,bold:true,color:'#FFFFFF'},rowHeight:38,horizontalAlignment:'center'};
const widths=[10,30,37,16,17,12,15,15,18,17,18,17,17,17,17,17,38,14,17,24,42];
for(let i=0;i<data.headers.length;i++){
  s.getRange(`${column(i+1)}1:${column(i+1)}${last}`).format.columnWidth=widths[i]??24;
  if(['是否选用','审核备注','审核人','审核日期'].includes(data.headers[i])||data.headers[i].endsWith('是否纳入')){
    s.getRange(`${column(i+1)}2:${column(i+1)}${last}`).format.fill='#FFF2CC';
  }
  if(data.headers[i]==='是否选用'||data.headers[i].endsWith('是否纳入')){
    s.getRange(`${column(i+1)}2:${column(i+1)}${last}`).dataValidation={rule:{type:'list',values:['1','0','待定']}};
  }
  if(data.headers[i]==='审核日期')s.getRange(`${column(i+1)}2:${column(i+1)}${last}`).setNumberFormat('yyyy-mm-dd');
}
for(let i=0;i<rows.length;i++){
  s.getRange(`A${i+2}:${end}${i+2}`).format.rowHeight=Math.max(34,Math.ceil(String(rows[i][2]).length/37)*18+6);
  for(let j=0;j<data.headers.length;j++){
    if(typeof rows[i][j]==='string'&&rows[i][j].startsWith('=HYPERLINK(')){
      s.getCell(i+1,j).formulas=[[rows[i][j]]];
      s.getCell(i+1,j).format.font={name:'Microsoft YaHei',size:11,color:'#0563C1',underline:'single'};
    }
  }
}
for(const item of data.links)s.getRange(item.cell).format.font={name:'Microsoft YaHei',size:11,color:'#0563C1',underline:'single'};
s.freezePanes.freezeRows(1);s.freezePanes.freezeColumns(4);
s.tables.add(`A1:${end}${last}`,true,'OccupationReview');
w.recalculate();
console.log((await w.inspect({kind:'region',sheetId:'职业汇总',range:'F1:P11',maxChars:1500})).ndjson);
const output=await SpreadsheetFile.exportXlsx(w);await output.save(path.join(outDir,'authored.xlsx'));
const image=await w.render({sheetName:'职业汇总',range:'F1:P11',format:'png',scale:1});
await fs.writeFile(path.join(outDir,'review.png'),new Uint8Array(await image.arrayBuffer()));
