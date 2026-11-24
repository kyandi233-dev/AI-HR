import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const [input,outDir]=process.argv.slice(2);
const specs=JSON.parse(await fs.readFile(input,'utf8'));
function col(n){let a='';while(n){n--;a=String.fromCharCode(65+n%26)+a;n=Math.floor(n/26);}return a;}
for(let index=0;index<specs.length;index++){
  const spec=specs[index],w=Workbook.create(),s=w.worksheets.add('材料审核');
  const last=Math.max(6,spec.rows.length+5),end=col(spec.headers.length);
  s.showGridLines=false;s.tabColor='#234E70';
  s.getRange(`A1:${end}${last}`).format.font={name:'Microsoft YaHei',size:11,color:'#1F2937'};
  s.getRange('A2').values=[[spec.reviewer+' · '+(spec.group==='occupation'?'职业材料审核':'道德材料审核')]];
  s.getRange('A2').format.font={name:'Microsoft YaHei',size:15,bold:true,color:'#234E70'};
  s.getRange('A2').format.rowHeight=28;
  s.getRange('A3').values=[[`已列入材料：${spec.rows.length}项。只填写黄色列；不直接改写材料正文。`]];
  s.getRange('A4').values=[[spec.group==='occupation'?'检查自然性、职业合理性和内部一致性；经验或技能不足本身不等于材料不可用。':spec.rows.length?'按配对检查可理解性、自然性、主题、两版一致性及直接专业关联。':'暂无已选用且已生成的道德正文；大纲不作为已生成材料列入。']];
  s.getRange(`A5:${end}5`).values=[spec.headers];
  s.getRange(`A5:${end}5`).format={fill:'#234E70',font:{name:'Microsoft YaHei',size:11,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:34,verticalAlignment:'center'};
  if(spec.rows.length)s.getRange(`A6:${end}${last}`).values=spec.rows.map(row=>row.map(v=>v&&typeof v==='object'&&v.date?new Date(v.date):v));
  const widths=spec.group==='occupation'?[25,37,17,11,15,16,18,23,48,17,26,22]:[24,20,20,18,25,52,17,22,22];
  for(let i=0;i<spec.headers.length;i++){
    const letter=col(i+1),name=spec.headers[i];s.getRange(`${letter}1:${letter}${last}`).format.columnWidth=widths[i];
    if(['审核结论','问题类型','问题说明','审核日期'].includes(name))s.getRange(`${letter}6:${letter}${last}`).format.fill='#FFF2CC';
    if(name==='审核结论')s.getRange(`${letter}6:${letter}${last}`).dataValidation={rule:{type:'list',values:['可用','需重新生成','不采用']}};
    if(name==='问题类型')s.getRange(`${letter}6:${letter}${last}`).dataValidation={rule:{type:'list',values:spec.group==='occupation'?['自然性','职业合理性','内部一致性','其他']:['可理解性','自然性','主题归属','两版配对','直接专业关联','其他']}};
    if(name==='审核日期')s.getRange(`${letter}6:${letter}${last}`).setNumberFormat('yyyy-mm-dd');
  }
  s.getRange(`A6:${end}${last}`).format.wrapText=true;s.getRange(`A6:${end}${last}`).format.verticalAlignment='center';
  s.getRange(`A6:${end}${last}`).format.rowHeight=40;
  for(const link of spec.links)s.getRange(link.cell).format.font={name:'Microsoft YaHei',size:11,color:'#0563C1',underline:'single'};
  s.freezePanes.freezeRows(5);s.freezePanes.freezeColumns(spec.group==='occupation'?4:2);
  s.tables.add(`A5:${end}${last}`,true,'ReviewerMaterials');
  w.recalculate();
  const out=await SpreadsheetFile.exportXlsx(w);await out.save(path.join(outDir,index+'.authored.xlsx'));
  if(index===0||spec.group!==specs[index-1].group){
    const image=await w.render({sheetName:'材料审核',range:spec.group==='occupation'?'A1:J11':'A1:G8',format:'png',scale:1});
    await fs.writeFile(path.join(outDir,spec.group+'.png'),new Uint8Array(await image.arrayBuffer()));
  }
}
