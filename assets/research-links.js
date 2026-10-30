/* Curated public links and an explicitly reviewed local draft; no submissions. */
(()=>{'use strict';
const root=document.getElementById('research-links'),dataNode=document.getElementById('research-links-data');if(!root||!dataNode)return;
const data=JSON.parse(dataNode.textContent),copy=data.copy;
const decorate=()=>{for(const item of data.cases)for(const id of item.source.comment_ids||[]){const comment=document.getElementById('comment-'+id);if(!comment||comment.querySelector('[data-research-case="'+item.id+'"]'))continue;const p=document.createElement('p'),a=document.createElement('a');a.textContent=copy.open+' · '+item.title;a.href=item.url;a.dataset.researchCase=item.id;p.append(a);comment.append(p);}};
decorate();document.addEventListener('ipvx-discussion-refreshed',decorate);
const discussion=document.querySelector('[data-community-rfc]'),publicList=discussion?.querySelector('.community-public');
if(publicList&&/^rfc-000[1-7]$/.test(discussion.dataset.communityRfc)){
 const rfc=discussion.dataset.communityRfc,language=document.documentElement.lang,experiments='experiments'+(language==='ru'?'':'.'+language)+'.html';
 const linkPublished=()=>{for(const entry of publicList.querySelectorAll('.community-entry')){const id=Number(entry.dataset.entryId);if(!Number.isSafeInteger(id)||id<=0||entry.querySelector('[data-experiment-draft]'))continue;entry.id='entry-'+id;const a=document.createElement('a'),p=document.createElement('p');a.textContent=copy.proposal;a.dataset.experimentDraft='';a.href=experiments+'?source='+encodeURIComponent('https://ipvx.org/'+rfc+'.html#entry-'+id)+'#experiment-draft';p.append(a);entry.append(p);}};
 new MutationObserver(linkPublished).observe(publicList,{childList:true,subtree:true});linkPublished();
}
const form=document.getElementById('research-draft-form');if(!form)return;
const details=document.getElementById('experiment-draft'),status=document.getElementById('research-draft-status'),output=document.getElementById('research-draft-output'),preview=document.getElementById('research-draft-text'),download=document.getElementById('research-draft-download'),submit=document.getElementById('research-draft-submit');
const params=new URLSearchParams(location.search);const selected=data.cases.find(item=>item.id===params.get('case'));
if(selected){form.elements.source.value=selected.source.url+'\n'+(selected.source.comment_ids||selected.source.event_ids||[]).join(', ');form.elements.hypothesis.value=selected.hypothesis;details.open=true;}
// Only stable public RFC entry locators, never text, credentials or intake IDs.
if(params.has('source')){const source=params.get('source');if(/^https:\/\/ipvx\.org\/rfc-000[1-7]\.html#entry-[1-9][0-9]{0,15}$/.test(source)){form.elements.source.value=source;details.open=true;}else{status.textContent=copy.invalid_source;details.open=true;}}
if(location.hash==='#experiment-draft')details.open=true;
let blobUrl=null;
form.addEventListener('input',event=>{event.target.setCustomValidity?.('');output.hidden=true;status.textContent='';if(blobUrl){URL.revokeObjectURL(blobUrl);blobUrl=null;}});
form.addEventListener('submit',event=>{event.preventDefault();for(const field of form.querySelectorAll('textarea'))field.setCustomValidity(field.value.trim()?'':copy.required);if(!form.reportValidity())return;
 const keys=['source','hypothesis','task','failures','scope','artifacts'];
 const text='# IPvX — '+copy.proposal+'\n\n'+copy.boundary+'\n\n'+keys.map(key=>'## '+copy[key==='hypothesis'?'question':key]+'\n\n'+form.elements[key].value.trim()).join('\n\n')+'\n';
 preview.value=text;if(blobUrl)URL.revokeObjectURL(blobUrl);blobUrl=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));download.href=blobUrl;
 const url=new URL('https://github.com/relcom-technologies/ipvx-research/issues/new');url.searchParams.set('template','experiment.yml');url.searchParams.set('draft',text);const fits=url.href.length<=7000;
 submit.href=fits?url.href:'https://github.com/relcom-technologies/ipvx-research/issues/new?template=experiment.yml';status.textContent=fits?copy.ready:copy.long;output.hidden=false;
});
window.addEventListener('pagehide',()=>{if(blobUrl)URL.revokeObjectURL(blobUrl);});
})();
