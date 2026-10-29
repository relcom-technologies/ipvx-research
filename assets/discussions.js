/* A published public mirror, never the private intake or a privileged API. */
(()=>{'use strict';
const root=document.getElementById('external-discussion');if(!root)return;
const list=document.getElementById('discussion-messages'),button=document.getElementById('discussion-refresh'),status=document.getElementById('discussion-refresh-status');
const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const date=value=>new Date(value).toLocaleString(document.documentElement.lang,{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});
let busy=false;
async function refresh(){if(busy)return;busy=true;button.disabled=true;status.textContent=root.dataset.loading;
try{
 const response=await fetch('data/community-discussions.json',{credentials:'omit',cache:'no-store'});if(!response.ok)throw new Error('load');const data=await response.json();
 if(data.kind!=='public_discussion_snapshot'||!Array.isArray(data.comments)||data.comments.length>1000||data.mirrored_comment_count!==data.comments.length||!Number.isFinite(Date.parse(data.observed_at)))throw new Error('format');
 const ids=new Set(data.comments.map(row=>row.id));
 const nodes=data.comments.map(row=>{
  if(!uuid.test(row.id)||typeof row.text!=='string'||row.text.length>16000||typeof row.claimed_author!=='string'||row.claimed_author.length>100||typeof row.project_account!=='boolean'||row.a2a_submission!==false)throw new Error('format');
  const details=make('details'),summary=make('summary'),time=make('time',date(row.created_at));details.className='collab-message';details.id='comment-'+row.id;time.dateTime=row.created_at;summary.append(make('span',row.claimed_author),' ',make('span',row.project_account?root.dataset.projectLabel:root.dataset.externalLabel),' ',time);details.append(summary);
  if(ids.has(row.parent_id)){const p=make('p',root.dataset.parentLabel+' '),a=make('a',row.parent_id.slice(0,8));p.className='small';a.href='#comment-'+row.parent_id;p.append(a);details.append(p);}
  const body=make('div',row.text);body.className='collab-message-text';body.lang='en';details.append(body,make('p','Moltbook · '+row.id));return details;
 });
 list.replaceChildren(...nodes);document.getElementById('discussion-count').textContent=String(nodes.length);document.getElementById('discussion-observed').textContent=date(data.observed_at);document.getElementById('discussion-source-count').textContent=String(data.reported_comment_count??'—');document.getElementById('discussion-returned-count').textContent=String(data.returned_comment_count);document.getElementById('discussion-account-count').textContent=String(new Set(data.comments.filter(row=>!row.project_account).map(row=>row.claimed_author)).size);status.textContent='';
 const anchor=decodeURIComponent(location.hash.slice(1));if(anchor.startsWith('comment-')){const target=document.getElementById(anchor);if(target)target.open=true;}
}catch{status.textContent=root.dataset.error;}finally{busy=false;button.disabled=false;}}
button.addEventListener('click',refresh);
list.addEventListener('click',event=>{const a=event.target.closest('a');if(!a||!a.hash.startsWith('#comment-'))return;const target=document.getElementById(a.hash.slice(1));if(target)target.open=true;});
refresh();
async function liaison(){try{const response=await fetch('data/liaison-status.json',{credentials:'omit',cache:'no-store'});if(!response.ok)return;const data=await response.json();if(data.schema_version!==1||data.project_account!=='IPvXResearchLiaison')return;const state=document.getElementById('liaison-runtime-status'),meta=document.getElementById('liaison-runtime-meta');if(data.state==='attention_required')state.textContent=state.dataset.error;else if(data.state==='running_draft_service')state.textContent=data.paid_api_run_verified?state.dataset.ready:state.dataset.observing;else return;meta.textContent=meta.dataset.time+': '+date(data.updated_at)+(typeof data.reserved_usd_today==='number'?' · '+meta.dataset.reserved+': '+data.reserved_usd_today.toFixed(4):'');}catch{/* Keep the explicitly labelled static service state. */}}
liaison();
})();
