import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const [input, outDir] = process.argv.slice(2);
const payload = JSON.parse(await fs.readFile(input, 'utf8'));
const BLUE = '#234E70', TEXT = '#243746', YELLOW = '#FFF2CC';
const font = {name: 'Microsoft YaHei', size: 11, color: TEXT};
function col(n) { let s=''; while(n) { n--; s=String.fromCharCode(65+n%26)+s; n=Math.floor(n/26); } return s; }
function displayWidth(value) { return [...String(value ?? '')].reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0); }
function table(sheet, headers, rows, widths, name) {
  const end=col(headers.length), last=Math.max(6,rows.length+5);
  sheet.showGridLines=false; sheet.tabColor=BLUE;
  sheet.getRange(`A1:${end}${last}`).format.font=font;
  sheet.getRange(`A5:${end}5`).values=[headers];
  sheet.getRange(`A5:${end}5`).format={fill:BLUE,font:{...font,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:34,verticalAlignment:'center'};
  if(rows.length)sheet.getRange(`A6:${end}${rows.length+5}`).values=rows;
  sheet.getRange(`A6:${end}${last}`).format.wrapText=true;
  sheet.getRange(`A6:${end}${last}`).format.verticalAlignment='center';
  headers.forEach((h,i)=>sheet.getRange(`${col(i+1)}1:${col(i+1)}${last}`).format.columnWidth=widths[i]);
  rows.forEach((row,i)=>{
    const lines=Math.max(1,...row.map((x,j)=>headers[j]==='材料版本'?1:Math.ceil(displayWidth(x)/Math.max(6,widths[j]-2))));
    sheet.getRange(`A${i+6}:${end}${i+6}`).format.rowHeight=Math.max(32,lines*15+8);
  });
  sheet.freezePanes.freezeRows(5); sheet.freezePanes.freezeColumns(2);
  if(rows.length)sheet.tables.add(`A5:${end}${last}`,true,name);
  return last;
}
function title(s, text, note) {
  s.getRange('A1').values=[[text]];
  s.getRange('A1').format.font={...font,size:15,bold:true,color:BLUE};
  s.getRange('A1').format.rowHeight=30;
  s.getRange('A3').values=[[note]];
  s.getRange('A3').format.font={...font,size:10,color:'#526777'};
  s.getRange('A3').format.rowHeight=24;
}
function standards(w) {
  const s=w.worksheets.add('定义与标准');
  const p=payload.protocol;
  const rows=Object.values(p.foundations).map(x=>[x.label,x.definition,x.author_operationalization,x.project_adaptation]);
  table(s,['主题','文献定义','MFV作者操作化与编写边界','本研究的迁移要求'],rows,[20,46,80,70],'FoundationStandards');
  title(s,'定义与审查标准','质量评分1=很差、7=很好；道德效价1=非常不道德、4=中性、7=非常道德。');
  s.getRange('A4').values=[['先打开正文再填写黄色列；待生成任务不可作材料审核结论。']];
  let row=14;
  const sections=[['原作者通用规则',p.author_general_rules],['本研究配对规则',p.study_rules],
                  ['评价说明',[p.human_validation_note,p.review_scale_note,'明显专业证据只作文本初筛，正式岗位关联性仍需结合对应JD；三人意见不自动转为最终纳入决定。']],
                  ['文献来源',p.references.map(x=>`${x.citation} ${x.location} ${x.url}`)]];
  for(const [label,lines] of sections){
    s.getRange(`A${row}:D${row}`).format.fill='#EAF0F5';s.getRange(`A${row}`).values=[[label]];
    s.getRange(`A${row}`).format.font={...font,bold:true};row++;
    for(const line of lines){
      s.getRange(`B${row}:D${row}`).merge();s.getRange(`B${row}`).values=[[line]];
      s.getRange(`B${row}:D${row}`).format={font,wrapText:true,verticalAlignment:'center',rowHeight:Math.max(32,Math.ceil(displayWidth(line)/180)*16+8)};
      row++;
    }row++;
  }
  return s;
}
function sources(w) {
  const s=w.worksheets.add('MFV原条目');
  const labels={care:'关怀',fairness:'公平',loyalty:'忠诚',authority:'权威',sanctity:'纯洁',liberty:'自由',social_norm:'非道德社会规范'};
  const metrics=['care','fairness','loyalty','authority','sanctity','liberty','not_wrong'];
  const headers=['来源编号','材料库编号','主题','英文原文','中文译文','原条目推荐','用于改编任务',
                 '关怀归类','公平归类','忠诚归类','权威归类','纯洁归类','自由归类','认为无错','错误程度0–4'];
  const rows=payload.catalog.items.map(x=>[x.source_id,x.library_item_number,labels[x.foundation],x.original_en,x.translation_zh,
                 x.recommended?'是':'否',x.use_as_seed?'是':'否',...metrics.map(k=>x.classification_proportions[k]),x.wrongness_mean_0_4]);
  table(s,headers,rows,[17,14,23,68,64,15,18,13,13,13,13,13,13,13,17],'MfvOriginalItems');
  title(s,'MFV原条目 · 132条','116条道德情境用于改编，16条社会规范控制仅作参考；原条目评分不等于改编效度。');
  s.getRange('A4').values=[['来源：'+payload.catalog.provenance.source_url+'；推荐状态参照Clifford等（2015）表6。']];
  s.getRange('H6:N137').setNumberFormat('0%');s.getRange('O6:O137').setNumberFormat('0.0');
  return s;
}

for(let index=0;index<payload.specs.length;index++){
  const spec=payload.specs[index],w=Workbook.create();
  const s=w.worksheets.add(spec.kind==='master'?'材料汇总':'材料审核');
  const widths=spec.headers.map(h=>({'材料编号':24,'道德主题':20,'来源方式':15,'MFV编号':13,'原条目推荐':15,
    '生成状态':15,'配对正文':16,'完整提示词':18,'生成备注':48,'问题说明':48,'决策备注':48,'材料版本':22,
    '主要主题':24,'明显专业证据':23,'审核结论':18,'审核日期':17,'最终是否纳入':20}[h]??15));
  const rows=spec.rows.map(row=>row.map(v=>v&&typeof v==='object'&&v.date?new Date(v.date):v));
  const last=table(s,spec.headers,rows,widths,'MoralityReview');
  title(s,spec.title,'黄色列为人工填写；只审查已生成正文。此文件可刷新，按材料编号与版本保留意见。');
  s.getRange('A4').values=[['未调用模型时正文链接为空；总表导入三人意见，最终是否纳入由研究者填写。']];
  s.getRange('A2').values=[['计划任务']];s.getRange('B2').values=[[rows.length]];
  const statusCol=col(spec.headers.indexOf('生成状态')+1);
  s.getRange('D2').values=[['已生成正文']];s.getRange('E2').formulas=[[`=COUNTIFS(${statusCol}6:${statusCol}${last},"已生成")`]];
  s.getRange('G2').values=[['待生成']];s.getRange('H2').formulas=[[`=COUNTIFS(${statusCol}6:${statusCol}${last},"待生成")`]];
  for(let i=0;i<spec.headers.length;i++){
    const h=spec.headers[i],letter=col(i+1),r=s.getRange(`${letter}6:${letter}${last}`);
    if(spec.manual.includes(h))r.format.fill=YELLOW;
    if(['可理解性','自然性','负面效价','中性效价','配对合理性'].includes(h))s.dataValidations.add({range:`${letter}6:${letter}${last}`,rule:{type:'whole',operator:'between',formula1:1,formula2:7}});
    if(h==='主要主题')r.dataValidation={rule:{type:'list',values:['关怀/伤害','公平/欺骗','忠诚/背叛','权威/颠覆','神圣/纯洁','自由/压迫','无明显道德主题','多主题难区分']}};
    if(h==='明显专业证据')r.dataValidation={rule:{type:'list',values:['未见明显证据','有','待结合岗位']}};
    if(h==='审核结论')r.dataValidation={rule:{type:'list',values:['可用','需修改','不采用']}};
    if(h==='最终是否纳入')r.dataValidation={rule:{type:'list',values:['纳入','修改后复审','不纳入']}};
    if(h==='审核日期')r.setNumberFormat('yyyy-mm-dd');
  }
  for(const link of spec.links)s.getRange(link.cell).format.font={...font,color:'#0563C1',underline:'single'};
  const statusRange=s.getRange(`${statusCol}6:${statusCol}${last}`);
  statusRange.conditionalFormats.add('containsText',{text:'失败',format:{fill:'#FCE4D6',font:{color:'#9C251D'}}});
  statusRange.conditionalFormats.add('containsText',{text:'不适配',format:{fill:'#FCE4D6',font:{color:'#9C251D'}}});
  if(spec.kind==='master')sources(w);
  standards(w);
  w.recalculate();
  const counts=s.getRange('E2:H2').values;
  const expectedGenerated=rows.filter(r=>r[spec.headers.indexOf('生成状态')]==='已生成').length;
  if(counts[0][0]!==expectedGenerated||counts[0][3]!==rows.filter(r=>r[spec.headers.indexOf('生成状态')]==='待生成').length)throw Error('状态计数不一致');
  const errors=await w.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20},maxChars:600});
  console.log(JSON.stringify({file:spec.kind,index,counts,scan:errors.ndjson}));
  const exported=await SpreadsheetFile.exportXlsx(w);await exported.save(path.join(outDir,index+'.authored.xlsx'));
  const previews=spec.kind==='master'?[['材料汇总','A1:H10'],['MFV原条目','A1:G9'],['定义与标准','A1:D11']]:[['材料审核','A1:H10'],['定义与标准','A1:D11']];
  for(const [sheetName,range] of previews){
    const png=await w.render({sheetName,range,format:'png',scale:1});
    await fs.writeFile(path.join(outDir,index+'_'+sheetName+'.png'),new Uint8Array(await png.arrayBuffer()));
  }
}
