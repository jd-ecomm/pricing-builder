const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, PageOrientation, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, ExternalHyperlink, ImageRun
} = require('docx');

// ---- week constants (only these change week to week) ----
const WEEK_ENDING = 'August 26, 2026';
const GENERATED   = 'August 27, 2026';
const L7_STR      = 'August 20 to 26';
const P7_STR      = 'August 13 to 19';
const OUT_PATH    = '/mnt/user-data/outputs/JD_Pricing_Actions_2026-08-26.docx';
const NOTE_GAP    = true;  // set true when this build follows a multi-week lapse

const D = JSON.parse(fs.readFileSync('/home/claude/section_data.json', 'utf8'));
const logo = fs.readFileSync('/mnt/project/jdsportslogoblackandwhite.png');

const YELLOW='FFE000', BLACK='000000', WHITE='FFFFFF';
const GREY='666666', GREYCAP='8A8A8A', HDRGREY='111111';
const GREEN='1F8A4C', RED='C0392B', DIM='999999';
const FONT='Arial';
const CONTENT_W=14400;
const baseline=D.meta.baseline;

const money=v=>(v==null?'':'$'+Math.round(v).toLocaleString());
const pct1=v=>(v==null?'':(v*100).toFixed(1)+'%');
const spct=v=>(v==null?'':(v>0?'+':'')+(v*100).toFixed(1)+'%');
const intc=v=>(v==null?'':Math.round(v).toLocaleString());
function run(t,o={}){return new TextRun({text:t,font:FONT,...o});}

function h1(text){
  return new Paragraph({spacing:{before:320,after:60},
    children:[new TextRun({text,font:FONT,bold:true,size:30,color:BLACK})],
    border:{bottom:{style:BorderStyle.SINGLE,size:18,color:YELLOW,space:4}}});
}
function subh(text){
  return new Paragraph({spacing:{before:200,after:100},
    children:[new TextRun({text,font:FONT,bold:true,size:22,color:BLACK})]});
}
function body(text,o={}){return new Paragraph({spacing:{after:120},children:[run(text,{size:19,...o})]});}
function bullet(runs){
  return new Paragraph({bullet:{level:0},spacing:{after:70},
    children:Array.isArray(runs)?runs:[run(runs,{size:19})]});
}
function noteItalic(text){
  return new Paragraph({spacing:{before:80,after:160},children:[run(text,{italics:true,size:16,color:GREY})]});
}
function spacer(){return new Paragraph({children:[],spacing:{after:120}});}

function cell(children,{w,fill,align,head=false}={}){
  const bd={style:BorderStyle.SINGLE,size:2,color:'D9D9D9'};
  return new TableCell({
    width:{size:w,type:WidthType.DXA},
    borders:{top:bd,bottom:bd,left:bd,right:bd},
    shading:fill?{fill,type:ShadingType.CLEAR,color:'auto'}:undefined,
    margins:{top:40,bottom:40,left:90,right:90},
    verticalAlign:VerticalAlign.CENTER,
    children:(Array.isArray(children)?children:[children]).map(c=>
      typeof c==='string'
        ? new Paragraph({alignment:align||AlignmentType.LEFT,
            children:[new TextRun({text:c,font:FONT,size:head?15:17,bold:head,color:head?WHITE:BLACK})]})
        : c)
  });
}
function headerRow(cols){
  return new TableRow({tableHeader:true,children:cols.map(c=>
    cell(c.label,{w:c.w,fill:HDRGREY,align:c.align||AlignmentType.LEFT,head:true}))});
}
function titleCell(title,url,w){
  const inner=url
    ? new ExternalHyperlink({link:url,children:[new TextRun({text:title,font:FONT,size:17,color:'1155CC',underline:{}})]})
    : new TextRun({text:title,font:FONT,size:17});
  return cell(new Paragraph({children:[inner]}),{w});
}
function viewCell(url,w){
  if(!url) return cell('',{w,align:AlignmentType.CENTER});
  return cell(new Paragraph({alignment:AlignmentType.CENTER,
    children:[new ExternalHyperlink({link:url,children:[new TextRun({text:'View',font:FONT,size:16,color:'1155CC',underline:{}})]})]}),{w});
}
function num(v,w,{color,bold}={}){
  return cell(new Paragraph({alignment:AlignmentType.RIGHT,
    children:[new TextRun({text:String(v),font:FONT,size:17,color:color||BLACK,bold:!!bold})]}),{w});
}
function sessCell(v,w){
  if(v==null) return cell(new Paragraph({alignment:AlignmentType.RIGHT,children:[run('No data',{size:15,italics:true,color:DIM})]}),{w});
  return num(intc(v),w);
}
function cvrCell(v,w){
  if(v==null) return cell(new Paragraph({alignment:AlignmentType.RIGHT,children:[run('n/a',{size:16,italics:true,color:DIM})]}),{w});
  const color=v>=baseline?GREEN:RED;
  return num((v*100).toFixed(2)+'%',w,{color,bold:true});
}
function gapCell(g,w,{bold=false}={}){
  return num((g>0?'+':'')+(g*100).toFixed(1)+'%',w,{bold});
}
function deltaCell(v,w){
  if(v==null) return num('\u221e',w,{color:DIM});
  return num(spct(v),w,{color:v>=0?GREEN:RED});
}
function dcvrCell(v,w){
  if(v==null) return num('',w);
  return num((v>=0?'+':'')+(v*100).toFixed(2)+'pp',w,{color:v>=0?GREEN:RED});
}
function makeTable(cols,rows){
  return new Table({width:{size:CONTENT_W,type:WidthType.DXA},columnWidths:cols.map(c=>c.w),
    rows:[headerRow(cols),...rows]});
}
function wswn(what,sowhat,next){
  const lab=2600,val=CONTENT_W-lab;
  const mk=(label,text)=>new TableRow({children:[
    cell(new Paragraph({children:[new TextRun({text:label,font:FONT,bold:true,size:18,color:BLACK})]}),{w:lab,fill:'FFF7B0'}),
    cell(new Paragraph({children:[new TextRun({text,font:FONT,size:18})]}),{w:val})
  ]});
  return new Table({width:{size:CONTENT_W,type:WidthType.DXA},columnWidths:[lab,val],
    rows:[mk('What',what),mk('So What',sowhat),mk("What's Next",next)]});
}

const kids=[];

// title block
kids.push(new Paragraph({spacing:{after:20},children:[new ImageRun({data:logo,type:'png',transformation:{width:120,height:34}})]}));
kids.push(new Paragraph({spacing:{after:20},children:[new TextRun({text:'JD SPORTS CANADA      \u00B7      BUYING & MERCHANDISING',font:FONT,bold:true,size:18,color:GREYCAP,characterSpacing:60})]}));
kids.push(new Paragraph({spacing:{after:40},children:[new TextRun({text:'Pricing & Performance Briefing',font:FONT,bold:true,size:44,color:BLACK})]}));
kids.push(new Paragraph({spacing:{after:60},border:{bottom:{style:BorderStyle.SINGLE,size:26,color:YELLOW,space:6}},
  children:[new TextRun({text:`Week ending ${WEEK_ENDING}      \u00B7      Generated ${GENERATED}`,font:FONT,size:19,color:GREY})]}));

// EXEC
kids.push(h1('Executive Summary'));
kids.push(body(`This briefing analyses ${intc(D.meta.total)} tracked Product IDs (${intc(D.meta.groups)} product groups) against Google Shopping's click-weighted competitor median. The L7 sales window is ${L7_STR}.`));
kids.push(body('Headline movements:',{bold:true}));
kids.push(bullet(`Catalogue position: ${intc(D.meta.above)} SKUs over market, ${intc(D.meta.at)} at market (within 2%), ${intc(D.meta.below)} below market. On-sale count ${intc(D.meta.on_sale)}. Out of stock: ${intc(D.meta.oos)}.`));
kids.push(bullet(`Site L7 CVR reads ${(baseline*100).toFixed(2)}% on full landing-session coverage. The recovery list (Section 1) holds ${D.counts.s1} qualifying products with active demand, and the markdown-response list (Section 2) holds ${D.counts.s2}.`));
kids.push(bullet(`Running change logs extended to ${intc(D.meta.changes_total)} effective-price changes and ${intc(D.meta.mkt_total)} market-price changes across the benchmark period. ${D.meta.snapshots} weekly position snapshots are now in the trend history.`));
kids.push(spacer());
kids.push(body("Changes since last week's report:",{bold:true}));
if(NOTE_GAP){
  kids.push(bullet('This build follows a gap since the last run. The price-change and market-change logs therefore capture every move since the previous build in one batch, so their weekly increment is larger than usual. The L7 versus prior-7 comparisons are still clean consecutive weeks drawn from the daily sales data and are unaffected.'));
}
kids.push(bullet('Same structure and definitions carried forward: Gap is (Ecomm minus Market) / Market computed from the two prices in each row; CVR shows n/a where the denominator is unavailable; product titles wrap fully; titles and URLs are hyperlinked.'));
kids.push(bullet(`Benchmark universe ${intc(D.meta.total)} Product IDs${D.meta.prev_total?' ('+intc(D.meta.prev_total)+' last build)':''}, reflecting Google Merchant Centre benchmark coverage. About half of the in-stock catalogue sits outside the benchmark and is not represented here.`));

// SECTION 1
kids.push(h1('1. Biggest Pricing Opportunity'));
kids.push(body('In-stock products priced at least 5% below market with enough demand signal (50+ clicks across the group in 28 days) and active L7 demand. Ranked by recovery score (L7 orders times per-unit headroom), so the highest-volume products with the most margin to recover rise to the top.'));
kids.push(subh('Recovery candidates: under-priced products with active demand'));
{
  const cols=[{label:'Product',w:3500},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1100},
    {label:'Ecomm',w:820,align:AlignmentType.RIGHT},{label:'Market',w:820,align:AlignmentType.RIGHT},
    {label:'Gap',w:900,align:AlignmentType.RIGHT},{label:'Headroom',w:1080,align:AlignmentType.RIGHT},
    {label:'L7 Ord',w:820,align:AlignmentType.RIGHT},{label:'L7 Rev',w:1020,align:AlignmentType.RIGHT},
    {label:'Sess',w:1150,align:AlignmentType.RIGHT},{label:'CVR',w:950,align:AlignmentType.RIGHT},
    {label:'Var',w:620,align:AlignmentType.RIGHT}];
  const rows=D.s1.map(r=>new TableRow({children:[
    titleCell(r.t,r.url,3500),viewCell(r.url,620),cell(r.b,{w:1100}),
    num(money(r.p),820),num(money(r.m),820),gapCell(r.gap,900),
    num('$'+Math.round(r.headroom)+'/unit',1080),num(intc(r.ol7),820),num(money(r.rl7),1020),
    sessCell(r.sess,1150),cvrCell(r.cvr,950),num(intc(r.nv),620)]}));
  kids.push(makeTable(cols,rows));
}
kids.push(noteItalic(`Filtered to ${D.counts.s1} qualifying products. Showing top 30 by recovery score. De-duplicated by title.`));
kids.push(subh('Where to focus first'));
{
  const a=D.s1[0],b=D.s1[1];
  kids.push(bullet(`${a.t}: ${intc(a.ol7)} L7 orders at ${money(a.p)} vs ${money(a.m)} market (${(a.gap*100).toFixed(0)}% gap), ${money(a.rl7)} L7 revenue. The highest-volume recovery candidate. Lift toward ${money(a.p*1.27)} to close part of the gap while keeping the price advantage that is driving demand.`));
  kids.push(bullet(`${b.t}: ${intc(b.ol7)} L7 orders at ${money(b.p)} vs ${money(b.m)} (${(b.gap*100).toFixed(0)}% gap). Stage a lift alongside the other top recovery colourways.`));
  kids.push(bullet('Treat the top of this list as a coordinated price-up set rather than one-offs, moving in 5 to 10% steps toward market median with a 14-day monitoring window.'));
}
kids.push(spacer());
kids.push(wswn(
  `${D.counts.s1} in-stock products are 5% or more below market with active demand. ${D.s1[0].t} leads on volume (${intc(D.s1[0].ol7)} L7 orders, ${money(D.s1[0].rl7)} revenue).`,
  'These are proven sellers priced below where the market has settled, so a staged lift recovers margin on demand that already exists, which makes it both high-value and low-risk.',
  'Confirm lift prices for the top five and stage them in Shopify. Target 5 to 10% below market median, hold 14 days, monitor orders and sessions.'
));

// SECTION 1B
kids.push(subh('Secondary opportunity: over-market products with conversion drag'));
if(D.s1b.length===0){
  kids.push(body('No products qualified this week (over-market, 100+ L7 sessions, CVR below the site baseline).',{color:GREY}));
}else{
  const cols=[{label:'Product',w:4200},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1200},
    {label:'Ecomm',w:900,align:AlignmentType.RIGHT},{label:'Market',w:900,align:AlignmentType.RIGHT},
    {label:'Gap',w:1000,align:AlignmentType.RIGHT},{label:'L7 Ord',w:900,align:AlignmentType.RIGHT},
    {label:'Sess',w:1100,align:AlignmentType.RIGHT},{label:'CVR',w:1000,align:AlignmentType.RIGHT},
    {label:'Var',w:700,align:AlignmentType.RIGHT}];
  const rows=D.s1b.map(r=>new TableRow({children:[titleCell(r.t,r.url,4200),viewCell(r.url,620),cell(r.b,{w:1200}),
    num(money(r.p),900),num(money(r.m),900),gapCell(r.gap,1000,{bold:true}),num(intc(r.ol7),900),
    sessCell(r.sess,1100),cvrCell(r.cvr,1000),num(intc(r.nv),700)]}));
  kids.push(makeTable(cols,rows));
  kids.push(noteItalic(`${D.counts.s1b} qualifying. These are priced above market and converting below baseline: candidates for a price-down or promotion review.`));
}

// SECTION 2
kids.push(h1('2. What Worked: Recent Price Change Response'));
kids.push(body('Markdown actions that drove genuine order response. Guardrails apply: at least 5 L7 orders, 100 L7 sessions, and a non-zero prior week, so growth off negligible bases is excluded. Score = (L7 orders times 2) plus a capped order-lift bonus.'));
kids.push(subh('Strong responders: markdowns delivering measurable lift'));
{
  const cols=[{label:'Product',w:3500},{label:'URL',w:560,align:AlignmentType.CENTER},{label:'Brand',w:1050},
    {label:'Markdown',w:980,align:AlignmentType.RIGHT},{label:'L7 Ord',w:760,align:AlignmentType.RIGHT},
    {label:'\u0394 Ord',w:820,align:AlignmentType.RIGHT},{label:'L7 Rev',w:980,align:AlignmentType.RIGHT},
    {label:'\u0394 Rev',w:820,align:AlignmentType.RIGHT},{label:'Sess',w:1050,align:AlignmentType.RIGHT},
    {label:'\u0394 Sess',w:840,align:AlignmentType.RIGHT},{label:'CVR',w:900,align:AlignmentType.RIGHT},
    {label:'\u0394 CVR',w:840,align:AlignmentType.RIGHT}];
  const rows=D.s2.map(r=>new TableRow({children:[titleCell(r.t,r.url,3500),viewCell(r.url,560),cell(r.b,{w:1050}),
    num(spct(r.md),980),num(intc(r.ol7),760),deltaCell(r.doo,820),num(money(r.rl7),980),deltaCell(r.dr,820),
    sessCell(r.sess,1050),deltaCell(r.ds,840),cvrCell(r.cvr,900),dcvrCell(r.dc,840)]}));
  kids.push(makeTable(cols,rows));
}
kids.push(noteItalic(`Guardrails: minimum 5 L7 orders, 100 L7 sessions, non-zero prior week. Score = (L7 orders times 2) plus capped order-lift bonus. L7 window ${L7_STR}; prior 7 is ${P7_STR}. \u221e marks a prior week of zero in that metric.`));
kids.push(subh('Standouts worth replicating'));
{
  const s2=D.s2;
  kids.push(bullet(`${s2[0].t}: markdown ${spct(s2[0].md)} driving ${intc(s2[0].ol7)} L7 orders, ${spct(s2[0].doo)} on orders week on week. The strongest sustained-velocity winner this week.`));
  if(s2[1]) kids.push(bullet(`${s2[1].t}: ${intc(s2[1].ol7)} L7 orders at ${spct(s2[1].md)} markdown, ${spct(s2[1].doo)} week on week.`));
  if(s2[2]) kids.push(bullet(`${s2[2].t}: ${intc(s2[2].ol7)} L7 orders at ${spct(s2[2].md)} markdown, ${spct(s2[2].doo)} week on week.`));
}
kids.push(spacer());
kids.push(wswn(
  `${D.counts.s2} products cleared the order and session guardrails. The top of the list is sustaining velocity, not one-week spikes.`,
  'These are proven elastic products. The ones still selling hard are the candidates to hold at a shallower markdown rather than snapping back to MSRP and losing the demand we built.',
  'Hold the top responders at roughly half their current markdown depth, still competitive versus market median, and review at 14 days.'
));

// SECTION 3
kids.push(h1('3. Top 20 Over Market: Significantly Higher Than Competitors'));
kids.push(body('Products priced more than 5% above market with meaningful demand (50+ clicks in 28 days). Sorted by gap times clicks. CVR shown where the PDP recorded landing sessions.'));
{
  const cols=[{label:'Product',w:4600},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1300},
    {label:'Ecomm',w:1000,align:AlignmentType.RIGHT},{label:'Market',w:1000,align:AlignmentType.RIGHT},
    {label:'Gap',w:1180,align:AlignmentType.RIGHT},{label:'CVR',w:1100,align:AlignmentType.RIGHT},
    {label:'Clicks 28d',w:1100,align:AlignmentType.RIGHT}];
  const rows=D.over.map(r=>new TableRow({children:[titleCell(r.t,r.url,4600),viewCell(r.url,620),cell(r.b,{w:1300}),
    num(money(r.p),1000),num(money(r.m),1000),gapCell(r.gap,1180,{bold:true}),cvrCell(r.cvr,1100),num(intc(r.clicks),1100)]}));
  kids.push(makeTable(cols,rows));
}
kids.push(noteItalic(`${D.counts.over} SKUs qualify as over market with demand. Showing top 20.`));
kids.push(spacer());
kids.push(wswn(
  `${D.counts.over} in-stock SKUs sit more than 5% above market with real click demand.`,
  'Margin-protected today but exposed to conversion drag if competitors hold lower. Cleanest candidates to either fold into a promotion or hold firm on, depending on stock cover.',
  'Review the top over-market clickers against stock cover. Hold price where stock is tight; consider a targeted markdown only where cover is heavy and CVR is soft.'
));

// SECTION 4
kids.push(h1('4. Top 20 Below Market: Significantly Lower Than Competitors'));
kids.push(body('Products priced more than 5% below market with meaningful demand. Sorted by absolute gap times clicks.'));
{
  const cols=[{label:'Product',w:4600},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1300},
    {label:'Ecomm',w:1000,align:AlignmentType.RIGHT},{label:'Market',w:1000,align:AlignmentType.RIGHT},
    {label:'Gap',w:1180,align:AlignmentType.RIGHT},{label:'CVR',w:1100,align:AlignmentType.RIGHT},
    {label:'Clicks 28d',w:1100,align:AlignmentType.RIGHT}];
  const rows=D.below.map(r=>new TableRow({children:[titleCell(r.t,r.url,4600),viewCell(r.url,620),cell(r.b,{w:1300}),
    num(money(r.p),1000),num(money(r.m),1000),gapCell(r.gap,1180),cvrCell(r.cvr,1100),num(intc(r.clicks),1100)]}));
  kids.push(makeTable(cols,rows));
}
kids.push(noteItalic(`${D.counts.below} SKUs qualify as below market with demand. Showing top 20.`));
kids.push(spacer());
kids.push(wswn(
  `${D.counts.below} in-stock SKUs sit more than 5% below market with click demand.`,
  'This is where the largest price-up headroom sits: products carrying demand at a discount to where the market has settled, so a clean staged lift recovers margin without necessarily losing volume.',
  'Build the lift execution sheet: every top 20 below-market SKU needs a target lift price (5 to 10% below market median), staged for go-live, with a 14-day monitoring trigger.'
));

// SECTION 5
kids.push(h1('5. High Sessions, Low CVR'));
kids.push(body(`Highest-traffic PDPs (top decile by L7 landing sessions, ${intc(D.meta.p90_sessions)}+ sessions) converting below the ${(baseline*100).toFixed(2)}% site baseline. Either price, page friction, or wrong-intent traffic is breaking the funnel.`));
{
  const cols=[{label:'Product',w:4400},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1300},
    {label:'Ecomm',w:1000,align:AlignmentType.RIGHT},{label:'Market',w:1000,align:AlignmentType.RIGHT},
    {label:'Gap',w:1100,align:AlignmentType.RIGHT},{label:'Sess',w:1000,align:AlignmentType.RIGHT},
    {label:'CVR',w:1000,align:AlignmentType.RIGHT},{label:'L7 Ord',w:980,align:AlignmentType.RIGHT}];
  const rows=D.s5.map(r=>new TableRow({children:[titleCell(r.t,r.url,4400),viewCell(r.url,620),cell(r.b,{w:1300}),
    num(money(r.p),1000),num(money(r.m),1000),gapCell(r.gap,1100),num(intc(r.sess),1000,{bold:true}),
    cvrCell(r.cvr,1000),num(intc(r.ol7),980)]}));
  kids.push(makeTable(cols,rows));
}
{
  const worst=D.s5.slice().sort((a,b)=>a.cvr-b.cvr)[0];
  kids.push(spacer());
  kids.push(wswn(
    `${D.counts.s5} high-traffic PDPs convert below the ${(baseline*100).toFixed(2)}% baseline.${worst?' '+worst.t+' is the weakest at '+(worst.cvr*100).toFixed(2)+'% on '+intc(worst.sess)+' landing sessions.':''}`,
    'Session-entry traffic on these pages is not converting at the rate the volume warrants. The cause is usually PDP friction (sizing availability, imagery, reviews) or wrong-intent traffic, not price, since several sit at or near market.',
    `PDP audit on the weakest performers this week${worst?', starting with '+worst.t:''}: size availability, imagery completeness and review counts versus sibling colourways. Ship fixes within five days.`
  ));
}

// SECTION 6
kids.push(h1('6. Low Sessions, High CVR'));
kids.push(body('Products converting at twice the site baseline or better, with 100 or more L7 sessions and at least 2 orders. Hidden gems where intent is high and the opportunity is traffic, not price.'));
if(D.s6.length===0){
  kids.push(body('No products qualified this week.',{color:GREY}));
}else{
  const cols=[{label:'Product',w:4400},{label:'URL',w:620,align:AlignmentType.CENTER},{label:'Brand',w:1300},
    {label:'Ecomm',w:1000,align:AlignmentType.RIGHT},{label:'Market',w:1000,align:AlignmentType.RIGHT},
    {label:'Gap',w:1100,align:AlignmentType.RIGHT},{label:'Sess',w:1000,align:AlignmentType.RIGHT},
    {label:'CVR',w:1000,align:AlignmentType.RIGHT},{label:'L7 Ord',w:980,align:AlignmentType.RIGHT}];
  const rows=D.s6.map(r=>new TableRow({children:[titleCell(r.t,r.url,4400),viewCell(r.url,620),cell(r.b,{w:1300}),
    num(money(r.p),1000),num(money(r.m),1000),gapCell(r.gap,1100),num(intc(r.sess),1000,{bold:true}),
    cvrCell(r.cvr,1000),num(intc(r.ol7),980)]}));
  kids.push(makeTable(cols,rows));
  kids.push(spacer());
  kids.push(wswn(
    `${D.counts.s6} products convert at twice the ${(baseline*100).toFixed(2)}% baseline or better on modest traffic.`,
    'High intent, low awareness. The lever is traffic, not price, so these are merchandising and marketing surfacing opportunities rather than pricing actions.',
    'Hand the top hidden gems to CRM and paid for surfacing (Klaviyo, on-site merchandising). The cleanest incremental-revenue plays that need no price change.'
  ));
}

// RECOMMENDATIONS
kids.push(h1("This Week's Pricing Recommendations"));
kids.push(body('Specific actions for the team this week, ordered roughly by speed to impact. Every line is backed by named current-week products.'));
{
  const worst=D.s5.slice().sort((a,b)=>a.cvr-b.cvr)[0]||{t:'weakest high-traffic PDP'};
  const recs=[
    ['1','PRICE-UP',"Lock the below-market price-up plan",`${D.counts.below} below-market SKUs with demand carry the largest margin headroom. Build the execution sheet: every top 20 below-market SKU needs a confirmed lift target, staged in Shopify for go-live at 5 to 10% below market median.`],
    ['2',D.s1[0].b.toUpperCase(),`${D.s1[0].t}: lift toward ${money(D.s1[0].p*1.27)}`,`${intc(D.s1[0].ol7)} L7 orders, ${money(D.s1[0].rl7)} revenue, the highest-volume recovery candidate. Current ${money(D.s1[0].p)} vs ${money(D.s1[0].m)} market (${(D.s1[0].gap*100).toFixed(0)}% gap). Close part of the gap while keeping the advantage that drives demand.`],
    ['3',D.s1[1].b.toUpperCase(),`${D.s1[1].t}: stage a coordinated lift`,`${intc(D.s1[1].ol7)} L7 orders at ${money(D.s1[1].p)} vs ${money(D.s1[1].m)} (${(D.s1[1].gap*100).toFixed(0)}% gap), ${intc(D.s1[1].sess)} L7 sessions. Move with the other top recovery colourways.`],
    ['4',D.s2[0].b.toUpperCase(),`${D.s2[0].t}: hold a shallower markdown`,`Top markdown responder (${intc(D.s2[0].ol7)} L7 orders, ${spct(D.s2[0].doo)} WoW). Keep at roughly half the current depth rather than snapping back to MSRP; it has shown genuine elasticity.`],
    ['5','MARKETING',"Surface the Section 6 hidden gems",`${D.counts.s6} products convert at twice the ${(baseline*100).toFixed(2)}% baseline or better on modest traffic. These need awareness, not markdown. Hand the top of the list to CRM and paid this week.`],
    ['6','PDP AUDIT',`${worst.t}: PDP friction check`,`Among measured pages, one of the weakest converters on real traffic. Check size availability, imagery and reviews versus sibling colourways and ship fixes within five days.`],
    ['7','OVER MARKET',"Decision on the top over-market clickers",`${D.counts.over} SKUs sit above market with demand. Decide per item: hold firm where stock is tight, or fold into a promotion where cover is heavy.`],
    ['8','COVERAGE',"Half the catalogue sits outside the benchmark",`This dashboard covers the ${intc(D.meta.groups)} benchmarked product groups. About half of in-stock products have no Google benchmark and are not represented, including some high-traffic lines. A supplementary un-benchmarked view is available on request.`],
    ['9','CADENCE',"Re-lock the weekly refresh",`This build followed a gap. Fix a weekly slot for the six-file pull and deploy so the live dashboard and its trend history stay current.`],
  ];
  const cols=[{label:'#',w:560,align:AlignmentType.CENTER},{label:'AREA',w:1700},{label:'ACTION',w:4600},{label:'DETAIL',w:7540}];
  const rows=recs.map(r=>new TableRow({children:[
    cell(new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({text:r[0],font:FONT,bold:true,size:18})]}),{w:560,fill:'FFF7B0'}),
    cell(new Paragraph({children:[new TextRun({text:r[1],font:FONT,bold:true,size:17})]}),{w:1700,fill:'F2F2F2'}),
    cell(new Paragraph({children:[new TextRun({text:r[2],font:FONT,bold:true,size:17})]}),{w:4600}),
    cell(new Paragraph({children:[new TextRun({text:r[3],font:FONT,size:17})]}),{w:7540})
  ]}));
  kids.push(makeTable(cols,rows));
}

// DATA QUALITY FLAGS
kids.push(h1('Data Quality Flags'));
if(NOTE_GAP) kids.push(bullet('This build follows a gap since the last run. Cumulative price-change and market-change logs capture the full catch-up period in one batch; the L7 versus prior-7 comparisons are clean consecutive weeks from the daily sales data.'));
kids.push(bullet(`Full landing-session coverage: ${intc(D.meta.sessful)} of ${intc(D.meta.groups)} product groups carry L7 session and CVR data. Site CVR baseline ${(baseline*100).toFixed(2)}%.`));
kids.push(bullet(`Benchmark universe ${intc(D.meta.total)} Product IDs${D.meta.prev_total?' ('+intc(D.meta.prev_total)+' last build)':''}. About half the in-stock catalogue has no Google benchmark and is invisible to this dashboard by design.`));
kids.push(bullet('Landing Page export reports sessions and conversion rate by path (no completed-checkout count); completions are derived as sessions times conversion rate. Canonical and collection-scoped paths are consolidated per product.'));

// METHODOLOGY
kids.push(h1('Methodology'));
kids.push(body(`Data sources: Google Merchant Centre Price Benchmarks export (window ${D.meta.bench_period}), Sale Price Suggestions export, GMC product feed (effective price), Shopify Daily Product Sales by SKU, and Shopify Landing Page Performance (daily sessions and conversion rate by landing-page path, no session filter).`));
kids.push(body('Product grouping: variants roll up to product level by canonical landing-page path, matched from the feed link; canonical and collection-scoped paths are consolidated per product. Ecomm Price is the median across in-stock variants. Market Price is Google\u2019s click-weighted competitor median per Product ID. Sections 3 and 4 are at Product ID (variant) level; the rest are product-group level.'));
kids.push(body('Gap definition: (Ecomm minus Market) / Market computed from the prices shown in each row, so every row reconciles.'));
kids.push(body(`Time windows: L7 is ${L7_STR}; prior 7 is ${P7_STR}. Site CVR baseline is ${(baseline*100).toFixed(2)}% over L7 across all measured PDPs. Section 2 delta columns compare L7 against prior 7; \u221e means the prior week had zero in that metric.`));
kids.push(body(`Thresholds: Section 1 recovery (more than 5% below market, in stock, 50-plus group clicks in 28 days, active L7 demand): ${D.counts.s1}, ranked by L7 orders times per-unit headroom. Section 1B drag (more than 5% over market, in stock, 100-plus L7 sessions, CVR below baseline): ${D.counts.s1b}. Section 2 (markdown in last 30 days, in stock, 5-plus L7 orders, 100-plus L7 sessions, non-zero prior week): ${D.counts.s2}. Section 3 over market and Section 4 below market (more than 5% off market, 50-plus clicks): ${D.counts.over} and ${D.counts.below}. Section 5 (top-decile sessions, ${intc(D.meta.p90_sessions)}-plus, CVR below baseline): ${D.counts.s5}. Section 6 (100-plus L7 sessions, CVR above twice baseline, 2-plus orders): ${D.counts.s6}. All product tables de-duplicated by title.`));
kids.push(body(`Cumulative tracking: running logs now hold ${intc(D.meta.changes_total)} effective-price changes and ${intc(D.meta.mkt_total)} market-price changes across the benchmark period. ${D.meta.snapshots} weekly position snapshots are in the trend history.`));
kids.push(noteItalic('Caveats: market prices reflect Google Shopping click-weighted median and do not capture promotions or local competitor pricing. Conversion rates are last-click and landing-page level. Single-product simulation does not model cannibalisation between our own SKUs.'));

const doc=new Document({
  styles:{default:{document:{run:{font:FONT,size:19}}}},
  sections:[{
    properties:{page:{size:{width:12240,height:15840,orientation:PageOrientation.LANDSCAPE},margin:{top:720,right:720,bottom:720,left:720}}},
    headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.RIGHT,
      children:[new TextRun({text:'JD SPORTS CANADA   \u00B7   Pricing & Performance Briefing',font:FONT,size:15,color:GREY})]})]})},
    footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,
      children:[new TextRun({text:`Week ending ${WEEK_ENDING}   \u00B7   Page `,font:FONT,size:15,color:GREY}),
                new TextRun({children:[PageNumber.CURRENT],font:FONT,size:15,color:GREY})]})]})},
    children:kids
  }]
});
Packer.toBuffer(doc).then(buf=>{fs.writeFileSync(OUT_PATH,buf);console.log('written',buf.length,'bytes ->',OUT_PATH);});
