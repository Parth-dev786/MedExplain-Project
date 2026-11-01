const csrfToken=document.querySelector('meta[name="csrf-token"]')?.content||'';
const form=document.getElementById('uploadForm');
const input=document.getElementById('reportFile');
const drop=document.getElementById('dropzone');
const fileRow=document.getElementById('fileRow');
const fileName=document.getElementById('fileName');
const analyzeBtn=document.getElementById('analyzeBtn');
const progressWrap=document.getElementById('progressWrap');
let currentFile=null,reportCount=0,lastData=null;
const history=[];

function localDateString(date=new Date()){const y=date.getFullYear(),m=String(date.getMonth()+1).padStart(2,'0'),d=String(date.getDate()).padStart(2,'0');return `${y}-${m}-${d}`}
function toast(message){const el=document.getElementById('toast');el.textContent=message;el.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.remove('show'),3600)}
function esc(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function setFile(file){if(!file)return;const ext=file.name.split('.').pop().toLowerCase();if(!['pdf','png','jpg','jpeg','webp'].includes(ext)){toast('Please choose a PDF or image file.');return}if(file.size>25*1024*1024){toast('File must be smaller than 25 MB.');return}currentFile=file;fileName.textContent=file.name;fileRow.hidden=false;drop.style.display='none'}
function showView(name){const views={overview:'overviewView',reports:'reportsView',learn:'learnView',history:'historyView',qr:'qrView',insurance:'insuranceView',medicines:'medicinesView',progress:'progressView',prescriptions:'prescriptionsView',medschedule:'medscheduleView',xrays:'xraysView'};Object.entries(views).forEach(([key,id])=>{const el=document.getElementById(id);el.hidden=key!==name;el.classList.toggle('active-view',key===name)});document.querySelectorAll('.nav').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===name));document.getElementById('pageTitle').textContent=({overview:'Overview',reports:'My reports',learn:'Health library',history:'Medical history',qr:'QR passport',insurance:'Insurance advisor',medicines:'Medicine information',progress:'Health progress',prescriptions:'Prescriptions',medschedule:'Medicine timer',xrays:'X-ray records'})[name]||'Overview';window.scrollTo({top:0,behavior:'smooth'});if(name==='reports')renderHistory();if(name==='history')loadPersistentHistory();if(name==='qr')loadQrReportOptions();if(name==='progress')loadProgress();if(name==='medschedule')loadSchedules();if(name==='xrays')loadXrays()}
async function renderHistory(){
 const target=document.getElementById('historyContent'); if(!target)return;
 target.className='history-list'; target.textContent='Loading reports…';
 try{
  const response=await fetch('/api/history'); const data=await response.json();
  if(!response.ok)throw new Error(data.error||'Could not load reports');
  const reports=data.reports||[];
  if(!reports.length){target.className='history-empty';target.innerHTML='<span>▤</span><b>No reports yet</b><p>Upload a report or explore the sample report to see your analysis history here.</p><button class="primary-btn compact" data-goto="overview">Analyse a report <span>→</span></button>';return}
  target.innerHTML=reports.map(item=>`<div class="history-row"><div><b>${esc(item.filename)}</b><small>${esc(new Date(item.created_at).toLocaleString())} · Saved report</small></div><strong>${esc(item.summary?.total??item.results?.length??0)} parameters</strong></div>`).join('');
 }catch(error){target.textContent='Could not load reports: '+error.message}
}
input.addEventListener('change',e=>setFile(e.target.files[0]));
document.getElementById('removeFile').onclick=()=>{currentFile=null;input.value='';fileRow.hidden=true;drop.style.display='flex'};
['dragenter','dragover'].forEach(event=>drop.addEventListener(event,e=>{e.preventDefault();drop.classList.add('drag')}));
['dragleave','drop'].forEach(event=>drop.addEventListener(event,e=>{e.preventDefault();drop.classList.remove('drag')}));
drop.addEventListener('drop',e=>setFile(e.dataTransfer.files[0]));
form.addEventListener('submit',async e=>{e.preventDefault();if(!currentFile){toast('Choose a report first.');return}const fd=new FormData();fd.append('report',currentFile);await runAnalysis('/api/analyze',fd)});
document.getElementById('demoBtn').onclick=()=>runAnalysis('/api/demo');
document.getElementById('heroUpload').onclick=()=>document.getElementById('uploadArea').scrollIntoView({behavior:'smooth',block:'center'});
async function runAnalysis(url,body=null){analyzeBtn.disabled=true;analyzeBtn.innerHTML='Reading every page… <span>◌</span>';progressWrap.hidden=false;document.getElementById('progressText').textContent='Scanning pages and supported test names…';try{const response=await fetch(url,{method:body?'POST':'GET',body});const data=await response.json();if(!response.ok)throw new Error(data.error||'Analysis failed');renderResults(data);const pages=data.summary.pages_scanned||1;toast(`Processed ${pages} page(s); found ${data.summary.total} supported parameter(s).`);if(data.translation_status==='english_fallback'&&window.MedExplainI18n?.language!=='en')toast(window.MedExplainI18n?.t('Medical explanation translation is not configured. UI labels are translated; report explanations remain in English.')||'Report explanations remain in English until a trusted translation service is configured.')}catch(error){toast(error.message)}finally{analyzeBtn.disabled=false;analyzeBtn.innerHTML='Analyse my report <span>→</span>';progressWrap.hidden=true}}
function renderResults(data){lastData=data;reportCount++;document.getElementById('reportCount').textContent=reportCount;document.getElementById('parameterCount').textContent=data.summary.total;document.getElementById('flaggedCount').textContent=data.summary.flagged+(data.summary.needs_review?` / ${data.summary.needs_review} review`:'');document.getElementById('resultFilename').textContent=`${data.filename||'Analysis complete'} · ${data.summary.pages_scanned||1} page(s) processed`;document.getElementById('resultsSection').hidden=false;document.getElementById('parameterTotalLabel').textContent=`${data.summary.total} results`;
 document.getElementById('resultSummary').innerHTML=`<div class="summary-box"><span>Parameters detected</span><strong>${data.summary.total}</strong></div><div class="summary-box"><span>Within printed range</span><strong style="color:#16845f">${data.summary.normal}</strong></div><div class="summary-box"><span>Flagged by printed range</span><strong style="color:#bd8538">${data.summary.flagged}</strong></div><div class="summary-box"><span>Needs review</span><strong>${data.summary.needs_review||0}</strong></div>`;
 const list=document.getElementById('parameterList');list.innerHTML='';if(!data.results.length){list.innerHTML='<p class="empty-explain">No supported parameters were detected. The report may use a layout or test name this prototype does not recognise. Check the extracted text or try a clearer PDF.</p>'}
 data.results.forEach((parameter,index)=>{const item=document.createElement('button');item.type='button';item.className='parameter-item'+(index===0?' selected':'');const statusClass=parameter.status==='Within lab range'?'ok':parameter.status==='Needs review'?'review':'warn';item.innerHTML=`<div><b>${esc(parameter.name)}</b><small>${esc(parameter.organ)} · Page ${esc(parameter.page)}</small></div><div class="param-value">${esc(parameter.value)} ${esc(parameter.unit)}<br><span class="status ${statusClass}">${esc(parameter.status)}</span></div>`;item.addEventListener('click',()=>{document.querySelectorAll('.parameter-item').forEach(el=>el.classList.remove('selected'));item.classList.add('selected');showExplanation(parameter)});list.appendChild(item)});
 if(data.results.length)showExplanation(data.results[0]);const extraction=data.extraction||{};const ocr=(extraction.pages_with_ocr||[]).length?` OCR used on page(s): ${(extraction.pages_with_ocr||[]).join(', ')}.`:'';document.getElementById('disclaimer').textContent=(data.notice||'')+` Pages processed: ${extraction.pages_processed||data.summary.pages_scanned||1}.${ocr}`;
 history.unshift({filename:data.filename||'Sample report',pages:data.summary.pages_scanned||1,total:data.summary.total,time:new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})});renderHistory();document.getElementById('resultsSection').scrollIntoView({behavior:'smooth',block:'start'});
}
function showExplanation(parameter){const interval=parameter.low!==null&&parameter.low!==undefined&&parameter.high!==null&&parameter.high!==undefined?`${esc(parameter.low)}–${esc(parameter.high)} ${esc(parameter.unit)}`:'Not detected in report';document.getElementById('explanationContent').innerHTML=`<div class="explain-content"><span class="organ-tag">${esc(parameter.organ)} · Page ${esc(parameter.page)}</span><h3 class="explain-title">${esc(parameter.name)}</h3><p><b>Extracted result</b><br>${esc(parameter.value)} ${esc(parameter.unit)}</p><p><b>What is it?</b><br>${esc(parameter.about)}</p><h4>What does this result mean?</h4><p>${esc(parameter.explanation)}</p><h4>Healthy habits to learn about</h4><p>${esc(parameter.lifestyle)}</p><p style="font-size:9px;color:#7c8b8b">Printed reference interval: ${interval}. Extraction confidence: ${Math.round((parameter.confidence||0)*100)}% (heuristic, not a validated probability). Source text: ${esc(parameter.source_text||'Not available')}</p></div>`}
document.getElementById('newReportBtn').onclick=()=>{document.getElementById('resultsSection').hidden=true;currentFile=null;input.value='';fileRow.hidden=true;drop.style.display='flex';window.scrollTo({top:0,behavior:'smooth'})};
document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
document.addEventListener('click',event=>{const target=event.target.closest('[data-goto]');if(target){showView(target.dataset.goto);if(target.dataset.scroll)setTimeout(()=>document.getElementById(target.dataset.scroll)?.scrollIntoView({behavior:'smooth',block:'center'}),60)}});
const mobileMenuButton=document.getElementById('mobileMenu');
mobileMenuButton?.addEventListener('click',()=>document.querySelector('.sidebar')?.classList.toggle('mobile-open'));
document.querySelectorAll('.sidebar .nav').forEach(button=>button.addEventListener('click',()=>document.querySelector('.sidebar')?.classList.remove('mobile-open')));
document.addEventListener('click',event=>{const sidebar=document.querySelector('.sidebar');if(sidebar?.classList.contains('mobile-open')&&!sidebar.contains(event.target)&&event.target!==mobileMenuButton)sidebar.classList.remove('mobile-open')});

// Lightweight pointer tilt: decorative only; all essential controls remain standard HTML.
if(matchMedia('(hover:hover) and (pointer:fine)').matches&&!matchMedia('(prefers-reduced-motion: reduce)').matches){document.querySelectorAll('.tilt-card').forEach(card=>{card.addEventListener('pointermove',event=>{const rect=card.getBoundingClientRect();const x=(event.clientX-rect.left)/rect.width-.5;const y=(event.clientY-rect.top)/rect.height-.5;if(card.classList.contains('hero'))card.style.transform=`perspective(1200px) rotateX(${-y*1.5}deg) rotateY(${x*1.5}deg)`});card.addEventListener('pointerleave',()=>{if(card.classList.contains('hero'))card.style.transform=''})})}


// Persistent medical history, QR passport, insurance comparison and medicine library.
async function loadPersistentHistory(){
 const target=document.getElementById('persistentHistory'); if(!target)return;
 target.textContent='Loading saved reports…';
 try{const r=await fetch('/api/history');const d=await r.json();
 if(!d.reports.length){target.innerHTML='<p>No saved reports yet. Analyse a report first.</p>';return}
 target.innerHTML=d.reports.map(x=>`<article class="history-row"><div><b>${esc(x.filename)}</b><small>${esc(new Date(x.created_at).toLocaleString())} · Report ID ${esc(x.id.slice(0,10))}</small></div><strong>${esc(x.summary.total||0)} parameters</strong></article>`).join('');
 }catch(e){target.textContent='Could not load saved history.'}
}
document.getElementById('refreshHistory')?.addEventListener('click',loadPersistentHistory);

async function loadQrReportOptions(){
 const select=document.getElementById('qrReportSelect'); if(!select)return;
 select.innerHTML='<option value="">Loading saved reports…</option>';
 try{
  const response=await fetch('/api/history'); const data=await response.json();
  if(!response.ok)throw new Error(data.error||'Could not load reports');
  const reports=data.reports||[];
  if(!reports.length){select.innerHTML='<option value="">No saved reports — analyse a report first</option>';return}
  select.innerHTML='<option value="">Choose a report…</option>'+reports.map(report=>
   `<option value="${esc(report.id)}">${esc(report.filename)} · ${esc(new Date(report.created_at).toLocaleString())} · ${Number(report.summary?.total||0)} parameters</option>`
  ).join('');
 }catch(error){select.innerHTML='<option value="">Could not load reports</option>';toast(error.message)}
}
document.getElementById('generateQr')?.addEventListener('click',async()=>{
 const out=document.getElementById('qrOutput'),reportId=document.getElementById('qrReportSelect')?.value;
 if(!reportId){toast('Please select a saved medical report first.');return}
 out.textContent='Generating secure QR Passport…';
 try{
  const r=await fetch('/api/qr',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:JSON.stringify({report_id:reportId})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not generate QR');
  const token=encodeURIComponent(d.token),safeUrl=esc(d.url);
  out.innerHTML=`<img alt="Complete medical report QR code" src="/qr/${token}.png"><p><b>Complete report analysis is ready to share.</b></p><p>Scan or share this private link:</p><a href="${safeUrl}" target="_blank" rel="noopener">${safeUrl}</a><p><a href="/qr/${token}.png" download="MedExplain_Report_QR.png">Download QR PNG</a> · <a href="/qr/${token}.pdf" download="MedExplain_Report_QR.pdf">Download QR PDF</a></p>`;
  toast('Report QR Passport generated successfully.');
 }catch(e){out.textContent=e.message}
});
document.getElementById('revokeQr')?.addEventListener('click',async()=>{
 const reportId=document.getElementById('qrReportSelect')?.value;
 if(!reportId){toast('Select the report whose QR access you want to revoke.');return}
 try{
  const r=await fetch('/api/qr/revoke',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:JSON.stringify({report_id:reportId})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not revoke access');
  document.getElementById('qrOutput').textContent=d.message||'Access revoked';toast(d.message||'Access revoked');
 }catch(e){toast(e.message)}
});
document.getElementById('qrReportSelect')?.addEventListener('focus',loadQrReportOptions);
document.querySelector('[data-view="qr"]')?.addEventListener('click',loadQrReportOptions);
let qrStream=null,qrFrame=null;
document.getElementById('startScanner')?.addEventListener('click',async()=>{
 const video=document.getElementById('qrVideo'),status=document.getElementById('scanResult');
 if(!('BarcodeDetector' in window)){status.textContent='This browser does not support built-in QR camera scanning. Open the QR link directly or use a QR scanner app.';return}
 try{const detector=new BarcodeDetector({formats:['qr_code']});qrStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});video.srcObject=qrStream;await video.play();
 const scan=async()=>{if(!qrStream)return;try{const codes=await detector.detect(video);if(codes.length){status.innerHTML=`QR detected: <a href="${esc(codes[0].rawValue)}" target="_blank" rel="noopener">Open scanned history link</a>`;stopQrCamera();return}}catch(e){}qrFrame=requestAnimationFrame(scan)};scan();
 }catch(e){status.textContent='Camera permission unavailable. Allow camera access and use HTTPS or localhost.'}
});
function stopQrCamera(){if(qrFrame)cancelAnimationFrame(qrFrame);if(qrStream){qrStream.getTracks().forEach(t=>t.stop());qrStream=null}}
document.getElementById('stopScanner')?.addEventListener('click',stopQrCamera);
document.getElementById('compareInsurance')?.addEventListener('click',async()=>{
 const target=document.getElementById('insuranceResults');target.textContent='Loading comparison guide…';
 try{const r=await fetch('/api/insurance');const d=await r.json();target.innerHTML=`<h3>Illustrative comparison</h3><div class="plan-grid">${d.plans.map(p=>`<article class="plan-card"><span class="demo-tag">DEMO DATA</span><h3>${esc(p.name)}</h3><b>${esc(p.coverage)}</b><p>${esc(p.provider)}</p><p>${esc(p.notes)}</p></article>`).join('')}</div><p class="notice">${esc(d.notice)}</p>`}
 catch(e){target.textContent='Unable to load comparison.'}
});
async function searchMedicines(){
 const q=document.getElementById('medicineSearch').value;const target=document.getElementById('medicineResults');target.textContent='Searching…';
 try{const r=await fetch('/api/medicines?q='+encodeURIComponent(q));const d=await r.json();target.innerHTML=(d.items.length?d.items.map(m=>`<article class="medicine-card"><h3>${esc(m.generic_name)}</h3><p><b>General purpose:</b> ${esc(m.purpose)}</p><p><b>Important cautions:</b> ${esc(m.cautions)}</p><small>Category: ${esc(m.category)}</small></article>`).join(''):'<p>No matching entries. This small educational catalogue is not comprehensive.</p>')+`<p class="notice">${esc(d.notice)}</p>`}
 catch(e){target.textContent='Unable to search medicine information.'}
}
document.getElementById('searchMedicine')?.addEventListener('click',searchMedicines);
document.getElementById('medicineSearch')?.addEventListener('keydown',e=>{if(e.key==='Enter')searchMedicines()});

// Multilingual UI is managed centrally by static/language.js.
// Translate generic report explanation copy again when the user changes language.
document.addEventListener('medex:languagechange', async event => {
 if(!lastData?.source_copy) return;
 const source=lastData.source_copy;
 const fields=['organ','about','explanation','lifestyle'];
 const texts=[source.notice||''];
 source.results.forEach(item=>fields.forEach(field=>texts.push(item[field]||'')));
 try{
  const response=await fetch('/api/translate-copy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts})});
  if(!response.ok) return;
  const payload=await response.json(), translated=payload.translations||[];
  let cursor=1;
  lastData.notice=translated[0]||source.notice;
  lastData.results.forEach(item=>fields.forEach(field=>{item[field]=translated[cursor++]||source.results[lastData.results.indexOf(item)]?.[field]||item[field]}));
  const extraction=lastData.extraction||{};
  const ocr=(extraction.pages_with_ocr||[]).length?` OCR used on page(s): ${(extraction.pages_with_ocr||[]).join(', ')}.`:'';
  document.getElementById('disclaimer').textContent=(lastData.notice||'')+` Pages processed: ${extraction.pages_processed||lastData.summary.pages_scanned||1}.${ocr}`;
  const selected=[...document.querySelectorAll('.parameter-item')].findIndex(el=>el.classList.contains('selected'));
  if(lastData.results.length) showExplanation(lastData.results[Math.max(0,selected)]);
  if(payload.translation_status==='english_fallback'&&event.detail.language!=='en') toast(window.MedExplainI18n?.t('Medical explanation translation is not configured. UI labels are translated; report explanations remain in English.')||'Medical explanation translation is not configured.');
 }catch(error){console.warn('Report copy translation unavailable',error)}
});

// MedExplain 3.0: report trend comparison, prescription OCR, dose reminders and X-ray record storage.
async function loadProgress(){
 const target=document.getElementById('progressResults'); if(!target)return; target.textContent='Loading report trends…';
 try{
  const r=await fetch('/api/progress'),d=await r.json();
  if(!d.trends.length){target.innerHTML='<p>Upload and analyse at least two reports containing the same test parameters to see comparisons.</p>';return}
  target.innerHTML=d.trends.map(t=>`<article class="trend-card"><div class="trend-head"><b>${esc(t.name)}</b><span>${t.same_unit?'Same unit':'Unit differs — compare cautiously'}</span></div><div class="trend-values"><div><small>Previous</small><strong>${esc(t.previous.value)} ${esc(t.previous.unit)}</strong><small>${esc(new Date(t.previous.date).toLocaleDateString())}</small></div><div class="trend-arrow">→</div><div><small>Current</small><strong>${esc(t.current.value)} ${esc(t.current.unit)}</strong><small>${esc(new Date(t.current.date).toLocaleDateString())}</small></div></div><p>Numerical change: <b>${t.change===null?'Not available':(t.change>0?'+':'')+t.change}</b> ${esc(t.current.unit||'')}</p><small>Previous status: ${esc(t.previous.status||'Not stated')} · Current status: ${esc(t.current.status||'Not stated')}</small></article>`).join('')+`<p class="notice">${esc(d.notice)}</p>`;
 }catch(e){target.textContent='Could not load progress data: '+e.message}
}
document.getElementById('refreshProgress')?.addEventListener('click',loadProgress);

document.getElementById('prescriptionForm')?.addEventListener('submit',async e=>{
 e.preventDefault();const f=document.getElementById('prescriptionFile').files[0],out=document.getElementById('prescriptionOutput');
 if(!f){out.textContent='Choose a prescription first.';return}
 const fd=new FormData();fd.append('prescription',f);out.textContent='Extracting readable text…';
 try{const r=await fetch('/api/prescriptions',{method:'POST',body:fd}),d=await r.json();if(!r.ok)throw new Error(d.error||'Could not read prescription');
 const medicines=Array.isArray(d.medicines)?d.medicines:[];
 const medicineHtml=medicines.length?medicines.map(m=>`<article class="trend-card"><h3>${esc(m.name)}</h3><p><b>Common purpose:</b> ${esc(m.purpose)}</p><p><b>Category:</b> ${esc(m.category)}</p><small>${esc(m.match_type)}. ${esc(m.warning)}</small></article>`).join(''):'<div class="notice"><b>No medicine name could be identified confidently.</b><p>The OCR text may be unclear, handwritten, abbreviated, or a brand name not in the local reference. MedExplain will not guess. Ask a pharmacist/doctor to confirm the name.</p></div>';
 out.innerHTML=`<article class="medicine-card"><h3>${esc(d.filename)}</h3><p>${esc(d.message)}</p><h3>Medicine names identified</h3>${medicineHtml}<details><summary>View raw OCR text (verify against original)</summary><pre class="extracted-text">${esc(d.text)}</pre></details><p><b>Important:</b> The common purpose listed is general medicine information, not a diagnosis. Strength, dose, timing and duration are not inferred. Confirm all details with your doctor/pharmacist before using them in Medicine Timer.</p></article>`;
 }catch(err){out.textContent=err.message}
});

async function loadSchedules(){
 const target=document.getElementById('scheduleList');if(!target)return;target.textContent='Loading schedules…';
 try{
  const r=await fetch('/api/schedules'),d=await r.json(),today=localDateString();
  const active=d.schedules.filter(s=>s.start_date<=today&&s.end_date>=today);
  if(!active.length){target.innerHTML='<p>No active schedules for today. Add a confirmed prescription schedule above.</p>';return}
  const logged=new Set(d.logs.filter(l=>l.scheduled_date===today).map(l=>l.schedule_id+':'+l.scheduled_time));
  const next=active.filter(s=>!logged.has(s.id+':'+s.dose_time)).sort((a,b)=>a.dose_time.localeCompare(b.dose_time)).find(s=>s.dose_time>=new Date().toTimeString().slice(0,5)) || active.filter(s=>!logged.has(s.id+':'+s.dose_time)).sort((a,b)=>a.dose_time.localeCompare(b.dose_time))[0];
  target.innerHTML=(next?`<p class="next-reminder"><b>Next medicine reminder:</b> ${esc(next.medicine_name)} at ${esc(next.dose_time)}</p>`:'<p class="next-reminder">All scheduled doses for today have been logged.</p>')+active.map(s=>{const done=logged.has(s.id+':'+s.dose_time);return `<article class="schedule-row"><div><b>${esc(s.dose_time)} · ${esc(s.medicine_name)}</b><p>${esc(s.strength)} · ${esc(s.tablets)} ${esc(s.dose_unit)} · ${esc(s.instructions||'Follow prescription instructions')}</p><small>${done?'Dose already logged today':'Reminder time: '+esc(s.dose_time)}</small></div><div class="schedule-actions"><button class="outline-btn" ${done?'disabled':''} onclick="logDose('${esc(s.id)}','taken')">Taken</button><button class="outline-btn" ${done?'disabled':''} onclick="logDose('${esc(s.id)}','skipped')">Skipped</button></div></article>`}).join('');
 }catch(e){target.textContent='Could not load medicine schedules.'}
}
window.logDose=async(id,status)=>{
 try{const r=await fetch('/api/schedules/'+encodeURIComponent(id)+'/log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,scheduled_date:localDateString(),scheduled_time:(new Date()).toTimeString().slice(0,5)})});const d=await r.json();if(!r.ok)throw new Error(d.error);toast(status==='taken'?'Dose marked as taken.':'Dose marked as skipped.');loadSchedules()}
 catch(e){toast(e.message)}
};
document.getElementById('scheduleForm')?.addEventListener('submit',async e=>{
 e.preventDefault();if(!document.getElementById('schConfirm').checked)return;
 const payload={medicine_name:document.getElementById('schName').value,strength:document.getElementById('schStrength').value,tablets:document.getElementById('schQty').value,dose_time:document.getElementById('schTime').value,start_date:document.getElementById('schStart').value,end_date:document.getElementById('schEnd').value,instructions:[document.getElementById('schFood').value,document.getElementById('schInstructions').value].filter(Boolean).join(' · ')};
 try{const r=await fetch('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.error);toast('Confirmed schedule saved.');e.target.reset();loadSchedules();refreshReminderSchedules()}
 catch(err){toast(err.message)}
});
document.getElementById('refreshSchedules')?.addEventListener('click',()=>{loadSchedules();refreshReminderSchedules()});

// Alarm audio is generated with Web Audio so no external sound file is required.
let alarmAudioContext=null,alarmOscillators=[],alarmGain=null,alarmVolume=0.75,activeAlarm=null,reminderTimer=null;
let reminderSchedules=[],snoozedReminders={},pendingAlarmQueue=[];
let lastReminderCheck=Date.now()-10000;
const firedReminders=new Set();
function ensureAudio(){
 const AudioContextClass=window.AudioContext||window.webkitAudioContext;
 if(!AudioContextClass)throw new Error('Web Audio is not supported in this browser.');
 if(!alarmAudioContext)alarmAudioContext=new AudioContextClass();
 if(alarmAudioContext.state==='suspended')alarmAudioContext.resume();
 if(!alarmGain){alarmGain=alarmAudioContext.createGain();alarmGain.gain.value=alarmVolume;alarmGain.connect(alarmAudioContext.destination)}
 return alarmAudioContext;
}
function startBuzzer(){
 const ctx=ensureAudio();stopBuzzer();
 const osc1=ctx.createOscillator(),osc2=ctx.createOscillator(),mod=ctx.createOscillator(),modGain=ctx.createGain();
 osc1.type='square';osc1.frequency.value=880;osc2.type='sawtooth';osc2.frequency.value=660;
 mod.type='square';mod.frequency.value=2.5;modGain.gain.value=0.42;
 const toneGain=ctx.createGain();toneGain.gain.value=0.65;
 mod.connect(modGain);modGain.connect(toneGain.gain);osc1.connect(toneGain);osc2.connect(toneGain);toneGain.connect(alarmGain);
 osc1.start();osc2.start();mod.start();alarmOscillators=[osc1,osc2,mod];
}
function stopBuzzer(){alarmOscillators.forEach(o=>{try{o.stop()}catch(e){}});alarmOscillators=[]}
function setAlarmVolume(value){alarmVolume=Math.max(0,Math.min(1,Number(value)/100));if(alarmGain)alarmGain.gain.setTargetAtTime(alarmVolume,alarmAudioContext.currentTime,0.03);const label=document.getElementById('alarmVolumeValue');if(label)label.textContent=Math.round(alarmVolume*100)+'%'}
function showAlarm(item,isTest=false){
 activeAlarm={...item,isTest};
 document.getElementById('alarmMedicineName').textContent=item.medicine_name||'Alarm test';
 document.getElementById('alarmMedicineDose').textContent=item.medicine_name?`${item.strength||''} · ${item.tablets||''} ${item.dose_unit||'dose'}`:'This is a test of your medicine reminder sound.';
 document.getElementById('alarmMedicineInstructions').textContent=item.instructions||'';
 document.getElementById('alarmScheduledTime').textContent=isTest?'Sound test':`Scheduled time: ${item.dose_time}`;
 document.getElementById('medicineAlarm').hidden=false;
 try{startBuzzer()}catch(e){toast('Tap Enable alarm sound to allow audio playback.')}
}
function dismissAlarm(){stopBuzzer();document.getElementById('medicineAlarm').hidden=true;activeAlarm=null}
function showNextPending(){if(!activeAlarm&&pendingAlarmQueue.length)showAlarm(pendingAlarmQueue.shift())}
function stopAlarm(){if(activeAlarm&&!activeAlarm.isTest){firedReminders.add(activeAlarm.key);localStorage.setItem('medex_fired_'+activeAlarm.key,'stopped')}dismissAlarm();showNextPending()}
function snoozeAlarm(){if(!activeAlarm)return;const item=activeAlarm;if(!item.isTest){snoozedReminders[item.key]=Date.now()+5*60*1000;localStorage.setItem('medex_snoozes',JSON.stringify(snoozedReminders))}dismissAlarm();toast('Reminder snoozed for 5 minutes.');showNextPending()}
document.getElementById('stopAlarm')?.addEventListener('click',stopAlarm);
document.getElementById('snoozeAlarm')?.addEventListener('click',snoozeAlarm);
document.getElementById('enableAlarm')?.addEventListener('click',()=>{try{ensureAudio();startBuzzer();setTimeout(stopBuzzer,700);toast('Alarm sound enabled.')}catch(e){toast(e.message)}});
document.getElementById('testAlarm')?.addEventListener('click',()=>{try{showAlarm({medicine_name:'Alarm sound test'},true);setTimeout(()=>{if(activeAlarm?.isTest)dismissAlarm()},4000)}catch(e){toast(e.message)}});
document.getElementById('alarmVolume')?.addEventListener('input',e=>setAlarmVolume(e.target.value));
try{snoozedReminders=JSON.parse(localStorage.getItem('medex_snoozes')||'{}')}catch(e){snoozedReminders={}}
async function refreshReminderSchedules(){
 try{const r=await fetch('/api/schedules');if(!r.ok)return;const d=await r.json();reminderSchedules=d.schedules||[];reminderLogs=d.logs||[]}catch(e){/* retry on next poll */}
}
let reminderLogs=[];
function checkMedicineReminders(){
 if(!reminderSchedules.length)return;
 const now=new Date(),today=localDateString(now),nowMs=now.getTime();
 // Snoozed reminders take priority when their five-minute delay expires.
 for(const [key,when] of Object.entries(snoozedReminders)){
  if(Number(when)<=nowMs){const s=reminderSchedules.find(x=>key.startsWith(x.id+':'));if(s){pendingAlarmQueue.push({...s,key});delete snoozedReminders[key]}}
 }
 localStorage.setItem('medex_snoozes',JSON.stringify(snoozedReminders));
 for(const s of reminderSchedules){
  const key=s.id+':'+today+':'+s.dose_time;
  const dueAt=new Date(`${today}T${s.dose_time}:00`).getTime();
  // Detect a reminder crossed between polls, even if a background tab timer was throttled.
  if(s.start_date>today||s.end_date<today||dueAt<=lastReminderCheck||dueAt>nowMs||firedReminders.has(key)||localStorage.getItem('medex_fired_'+key))continue;
  if(reminderLogs.some(l=>l.schedule_id===s.id&&l.scheduled_date===today&&l.scheduled_time===s.dose_time))continue;
  firedReminders.add(key);localStorage.setItem('medex_fired_'+key,'ringing');pendingAlarmQueue.push({...s,key});
  if('Notification'in window&&Notification.permission==='granted')try{new Notification(window.MedExplainI18n?.t('Time to Take Your Medicine!')||'Time to Take Your Medicine!',{body:`${s.medicine_name} · ${s.strength||''} · ${s.tablets} ${s.dose_unit}`})}catch(e){}
 }
 lastReminderCheck=nowMs;
 showNextPending();
}
function startReminderMonitoring(){
 refreshReminderSchedules();if(reminderTimer)clearInterval(reminderTimer);
 reminderTimer=setInterval(()=>{checkMedicineReminders();if(new Date().getSeconds()<5)refreshReminderSchedules()},5000);
}
if('Notification'in window&&Notification.permission==='default')document.querySelector('[data-view="medschedule"]')?.addEventListener('click',()=>Notification.requestPermission(),{once:true});
startReminderMonitoring();

document.getElementById('xrayForm')?.addEventListener('submit',async e=>{
 e.preventDefault();const f=document.getElementById('xrayFile').files[0],out=document.getElementById('xrayOutput');if(!f)return;
 const fd=new FormData();fd.append('xray',f);fd.append('image_type',document.getElementById('xrayType').value);out.textContent='Saving image record…';
 try{const r=await fetch('/api/xray',{method:'POST',body:fd}),d=await r.json();if(!r.ok)throw new Error(d.error);out.innerHTML=`<p><b>${esc(d.filename)}</b> saved. ${esc(d.status)}</p><p class="notice">${esc(d.notice)}</p>`;e.target.reset();loadXrays()}
 catch(err){out.textContent=err.message}
});
async function loadXrays(){
 const target=document.getElementById('xrayList');if(!target)return;target.textContent='Loading records…';
 try{const r=await fetch('/api/xrays'),d=await r.json();target.innerHTML=d.items.length?d.items.map(x=>`<article class="history-row"><div><b>${esc(x.filename)}</b><small>${esc(x.image_type)} · ${esc(new Date(x.created_at).toLocaleString())}</small></div><span class="status review">${esc(x.review_status)}</span></article>`).join(''):'<p>No X-ray images uploaded yet.</p>'}
 catch(e){target.textContent='Could not load X-ray records.'}
}
