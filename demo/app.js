/* Generic research review. Initial records are fictional; no model or web search runs here. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const node = (tag, cls, text) => {const n=document.createElement(tag); if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  let sample=[], records=[], selected=null, imported=false;
  const stateLabels={reviewed:'Sample review complete',needs_review:'Needs verification',missing_source:'Missing source text'};
  const exampleBriefs={
    general:['Find a small set of current openings across data analysis, design and operations. Compare what each role actually does and flag missing or ambiguous information.','What are the main responsibilities? Which requirements are essential? Is the opening still active? Which details need a human check?'],
    data:['Find current data analyst openings across several different industries. Look beyond the title to compare the work.','What kinds of data and decisions does the role support? Which tools are essential? Does the description distinguish analysis from data engineering?'],
    operations:['Find current operations and visitor-experience openings at museums or cultural organizations.','How much of the role involves visitor services, events or administration? Which duties are specified? What cannot be confirmed from the posting?']
  };
  const tidy=(value,max=20000)=>String(value??'').trim().slice(0,max);
  function brief(){
    return `AI RESEARCH BRIEF — JOB LISTING RESEARCH\n\nRESEARCH QUESTION\n${$('#brief-question').value.trim()}\n\nQUESTIONS TO ANSWER\n${$('#brief-questions').value.trim()}\n\nYOUR TASK\nUse web search and original employer or ATS pages to find a small set of current openings. Read each full description, not just the search snippet. Give the original source URL and the date you checked it. Quote a short source excerpt that supports the responsibilities or requirements. Clearly label uncertainty, duplicates, inaccessible sources, and openings that may have closed. Never infer an individual's preferences, background, eligibility or likelihood of being hired. Do not use this tool's fictional companies or sample records as sources. Do not invent missing details. This workbench does not perform this research for you.\n\nOUTPUT\nReturn a JSON file with a top-level "jobs" array (maximum 500 entries). Use this structure for each real result; replace the placeholders with sourced information:\n${JSON.stringify({jobs:[{title:'Exact posting title',company:'Employer name',role_family:'Data / Design / Operations / another general family',industry:'Industry supported by the source',source_url:'https://employer.example/careers/actual-posting',checked_at:'YYYY-MM-DD',source_excerpt:'Short exact quote supporting a factual observation',description:'Concise responsibilities summary grounded in the source',open_questions:['A specific missing or ambiguous detail to verify']} ]},null,2)}\n\nKeep location, salary, personal profiles, resumes and application history out of this demonstration. This app will mark every imported record as needing human verification; an AI-produced URL or quote is not proof it is accurate.\n`;
  }
  function preview(){ $('#prompt-preview').textContent=brief(); }
  function feedback(text,error=false){$('#brief-feedback').textContent=text;$('#brief-feedback').classList.toggle('error',error);}
  function fillFilters(){
    for(const [id,key,label] of [['#role-filter','role_family','All role families'],['#industry-filter','industry','All industries']]){
      const s=$(id);s.replaceChildren(node('option','',label));s.firstChild.value='';
      [...new Set(records.map(r=>r[key]))].sort().forEach(v=>{const o=node('option','',v);o.value=v;s.append(o);});
    }
  }
  const duplicateKey=r=>`${r.company}|${r.title}`.toLowerCase().replace(/\s+/g,' ').trim();
  function render(){
    const q=$('#q').value.toLowerCase().trim();const full=$('#search-descriptions').checked;
    let view=records.filter(r=>{
      const hay=[r.title,r.company,r.role_family,r.industry];if(full)hay.push(r.description,r.source_excerpt,...r.open_questions);
      return(!q||hay.join(' ').toLowerCase().includes(q))&&(!$('#role-filter').value||r.role_family===$('#role-filter').value)&&(!$('#industry-filter').value||r.industry===$('#industry-filter').value)&&(!$('#status-filter').value||r.status===$('#status-filter').value)&&(!$('#has-evidence').checked||Boolean(r.source_excerpt));
    });
    const counts=new Map();for(const r of view)counts.set(duplicateKey(r),(counts.get(duplicateKey(r))||0)+1);
    if($('#collapse').checked){const seen=new Set();view=view.filter(r=>{const k=duplicateKey(r);if(seen.has(k))return false;seen.add(k);return true;});}
    $('#result-count').textContent=`${view.length} shown · ${records.length} ${imported?'imported results':'fictional records'}`;
    const host=$('#list');host.replaceChildren();
    for(const r of view){
      const b=node('button','result'+(selected===r.id?' selected':''));b.type='button';b.setAttribute('aria-pressed',String(selected===r.id));b.append(node('h3','',r.title),node('p','',r.company+' · '+r.industry));
      const badges=node('div','badges');badges.append(node('span','badge',r.role_family),node('span','badge '+r.status,stateLabels[r.status]));
      if($('#collapse').checked&&counts.get(duplicateKey(r))>1)badges.append(node('span','badge',counts.get(duplicateKey(r))+' repeated records'));
      b.append(badges);b.onclick=()=>{selected=r.id;render();show(r);};host.append(b);
    }
    if(!view.length)host.append(node('p','no-results','No records match these filters. Try clearing a filter or resetting the collection.'));
  }
  function show(r){
    const host=$('#detail');host.replaceChildren();const head=node('div','detail-head');head.append(node('h2','',r.title),node('p','',r.company+' · '+r.industry),node('span','badge '+r.status,stateLabels[r.status]));host.append(head);
    const body=node('div','detail-body');body.append(node('p','notice',imported?'Imported AI research is unverified. Open the original source and check its wording, date and current availability.':'Invented example. The employer, description, evidence and review state demonstrate a workflow, not a live opening.'));
    const facts=node('dl','record-facts');
    const add=(name,value)=>{facts.append(node('dt','',name),node('dd','',value));};
    add('Role family',r.role_family);add('Source',imported?'AI-provided source · human check needed':'Fictional source excerpt');add('Checked on',r.checked_at||'Not recorded');
    if(r.source_url){const dd=node('dd');const a=node('a','',r.source_url);a.href=r.source_url;a.target='_blank';a.rel='noopener noreferrer';dd.append(a);facts.append(node('dt','','Original source'),dd);}
    body.append(node('h3','','Research record'),facts,node('h3','','Evidence from the source'));
    body.append(r.source_excerpt?node('blockquote','',r.source_excerpt):node('p','','No source excerpt was captured. This record needs more research before its details can be trusted.'));
    body.append(node('h3','','Responsibilities / context'),node('p','description',r.description||'No description was captured.'));
    body.append(node('h3','','What still needs a check?'));const ul=node('ul');for(const question of r.open_questions)ul.append(node('li','',question));if(!r.open_questions.length)ul.append(node('li','','Confirm the original page and whether this opening is still active.'));body.append(ul);host.append(body);
  }
  function resetFilters(){ $('#q').value='';$('#role-filter').value='';$('#industry-filter').value='';$('#status-filter').value='';$('#collapse').checked=true;$('#has-evidence').checked=false;$('#search-descriptions').checked=true;render(); }
  function setRecords(items,isImported){records=items;imported=isImported;selected=null;$('#data-label').textContent=isImported?'Imported research · not verified':'Fictional sample collection';fillFilters();resetFilters();if(records.length){selected=records[0].id;render();show(records[0]);}}
  function importRows(payload){
    if(!payload||!Array.isArray(payload.jobs)||!payload.jobs.length||payload.jobs.length>500)throw new Error('Use a JSON object with a jobs array containing 1–500 records.');
    return payload.jobs.map((r,i)=>{
      if(!r||typeof r!=='object'||Array.isArray(r)||typeof r.title!=='string'||!r.title.trim()||typeof r.company!=='string'||!r.company.trim())throw new Error(`Record ${i+1} needs a title and company.`);
      const source=tidy(r.source_url,2000);if(source){let u;try{u=new URL(source);}catch{throw new Error(`Record ${i+1} has an invalid source URL.`);}if(!['http:','https:'].includes(u.protocol))throw new Error(`Record ${i+1} needs an http or https source URL.`);}
      if(r.open_questions!==undefined&&(!Array.isArray(r.open_questions)||r.open_questions.some(x=>typeof x!=='string')))throw new Error(`Record ${i+1}: open_questions must be a list of strings.`);
      return {id:'import-'+i,title:tidy(r.title,300),company:tidy(r.company,300),role_family:tidy(r.role_family||'Unspecified',100),industry:tidy(r.industry||'Unspecified',100),source_url:source,checked_at:tidy(r.checked_at,40),source_excerpt:tidy(r.source_excerpt),description:tidy(r.description),open_questions:(r.open_questions||[]).slice(0,30).map(x=>tidy(x,2000)),status:'needs_review'};
    });
  }
  $('#toggle-brief').onclick=()=>{const open=$('#brief-panel').hidden;$('#brief-panel').hidden=!open;$('#toggle-brief').setAttribute('aria-expanded',String(open));$('#toggle-brief').textContent=open?'Hide AI research brief':'Create an AI research brief';};
  $('#brief-example').onchange=()=>{const fields=exampleBriefs[$('#brief-example').value];$('#brief-question').value=fields[0];$('#brief-questions').value=fields[1];preview();};
  for(const s of ['#brief-question','#brief-questions'])$(s).oninput=preview;
  $('#download-brief').onclick=()=>{const url=URL.createObjectURL(new Blob([brief()],{type:'text/plain;charset=utf-8'}));const a=node('a');a.href=url;a.download='job-research-brief.txt';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);feedback('Brief downloaded. Use it with an AI agent that has web access, then import its JSON results.');};
  $('#copy-brief').onclick=async()=>{try{await navigator.clipboard.writeText(brief());feedback('Research brief copied. Paste it into your preferred AI research tool.');}catch{feedback('Clipboard access is unavailable here. Use Download AI research brief instead.',true);}};
  $('#import-results').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>2000000)throw new Error('Choose a JSON file smaller than 2 MB.');const rows=importRows(JSON.parse(await file.text()));setRecords(rows,true);feedback(`Imported ${rows.length} records into this tab. Sources and claims still need human verification.`);}catch(error){feedback('Import not applied: '+error.message,true);}finally{e.target.value='';}};
  $('#restore-samples').onclick=()=>{setRecords(sample,false);feedback('Fictional sample collection restored. Imported results have been cleared from this tab.');};
  for(const s of ['#q','#role-filter','#industry-filter','#status-filter','#collapse','#has-evidence','#search-descriptions'])$(s).addEventListener(s==='#q'?'input':'change',render);
  $('#reset').onclick=resetFilters;
  preview();
  fetch('./data.json').then(r=>{if(!r.ok)throw new Error('Collection could not be loaded.');return r.json();}).then(d=>{sample=d.jobs;setRecords(sample,false);}).catch(()=>{$('#result-count').textContent='Collection unavailable';$('#list').append(node('p','no-results','Please reload this page, or use Create an AI research brief to import a collection.'));});
})();
