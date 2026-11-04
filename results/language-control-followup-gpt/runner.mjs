// Explicit exploratory gateway adaptation of the frozen language-control plan.
// Import and inject credentials in memory; never stores credentials.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const sha = x => createHash('sha256').update(x).digest('hex');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
export async function createLanguageControl(root, keys, config={}) {
  const dir = path.join(root, config.relativeDir??'outputs/language-control-followup');
  const dump = async (name, data) => fs.writeFile(path.join(dir, name), JSON.stringify(data, null, 2)+'\n');
  const read = async name => JSON.parse(await fs.readFile(path.join(dir, name), 'utf8'));
  const frozen = await read('sha256.json');
  for (const [name, digest] of Object.entries(frozen)) {
    if (sha(await fs.readFile(path.join(dir,name))) !== digest) throw Error('Frozen input changed: '+name);
  }
  try { await fs.access(path.join(dir,'execution.json')); throw Error('Existing execution: resume must be explicit'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const cases = await read('cases.json'), schedule = await read('requests-one-model.json');
  const profiles = config.profiles??[{connection:2,label:'gpt-6.1-sol'}, {connection:3,label:'gemini-4-argon'}];
  const quota = async p => {
    const r = await fetch('https://gpt-api.cc/api/usage/token/',{headers:{Authorization:'Bearer '+keys[p.connection-1]},signal:AbortSignal.timeout(15000)});
    const j = await r.json();
    if (!r.ok || typeof j.data?.total_used !== 'number') throw Error('Quota unavailable; stop inference');
    return j.data.total_used;
  };
  const initial = await Promise.all(profiles.map(quota));
  const amendment = {
    prepared_at_utc:new Date().toISOString(), original_files:frozen,
    status:'exploratory_gateway_adaptation_frozen_before_inference',
    authority:'User supplied and authorized third-party gateway connections after direct credentials were unavailable.',
    models:profiles, prior_setup:config.priorSetup??null, identity:'Unverified third-party gateway labels, not independently authenticated provider models. Model-list owned_by metadata says openai even for Grok/Gemini.',
    changes:['Direct provider verification unavailable: exploratory gateway study only.',
      'Model-native tokenizers unavailable: retain all cases as primary and the frozen local o200k_base <=10% subset as secondary, not as model-native length matching.',
      'Independent human bilingual review unavailable: obtain one automated review per available gateway label before target inference, disclose reviewer/target model reuse. No claim of independent semantic certification.'],
    generation:{max_tokens:4096,stream:true,temperature:'gateway default',reasoning:'gateway default',concurrency_per_connection:1,timeout_ms:60000,max_attempts:2},
    stopping:{soft_total_quota:150000,soft_per_connection_quota:75000,check_every_trials_per_connection:5,policy:'Stop on metadata failure, cap, nontransient error, or repeated transient error. Soft caps can overshoot by the in-flight batch. No answer-dependent stopping.'},
    arms:['english','chinese','mixed'], cases:cases.length, repeats:3,target_calls:schedule.length*profiles.length,review_calls:profiles.length,
    full_study_models_required:2,model_coverage_complete:profiles.length===2,
    implementation_sha256:sha(await fs.readFile(new URL(import.meta.url))),
    notes:['Same common system instruction is prepended to all user prompts. Local counts omit this shared prefix and transport framing.',
      'No cache reset, no answer repairs, no retries for wrong/invalid JSON answers, all attempts retained.',
      'Stock and overlap vary numeric values and order; latest-state cases reuse timestamps and vary identifiers/tie state/group order. Narrow template-level generalization only.'],
  };
  await dump('execution-amendment.json', amendment);
  const state = {started_at_utc:new Date().toISOString(), complete:false,full_study_model_coverage_complete:profiles.length===2,phase:'review',amendment_sha256:sha(await fs.readFile(path.join(dir,'execution-amendment.json'))),reviews:[],trials:[],attempts:[],billing_records:[],checkpoints:[],stopped:false};
  const privatePath = path.join(root,'work/language-control-'+path.basename(dir)+'-quota-private.json');
  await fs.writeFile(privatePath,JSON.stringify({initial},null,2)+'\n');
  let writeChain=Promise.resolve();
  const save = () => { const content=JSON.stringify(state,null,2)+'\n'; writeChain=writeChain.then(()=>fs.writeFile(path.join(dir,'execution.json'),content)); return writeChain; };
  const checkpoint = async () => {
    try {
      const current=await Promise.all(profiles.map(quota));
      const deltas=current.map((v,i)=>v-initial[i]);
      if (deltas.some(v=>v<0)) throw Error('Quota counter moved backwards');
      state.checkpoints.push({at_utc:new Date().toISOString(),trials:state.trials.length,attempts:state.attempts.length,per_connection:profiles.map((p,i)=>({connection:p.connection,delta_quota:deltas[i]})),total_delta_quota:deltas.reduce((a,b)=>a+b,0)});
      if(deltas.some(v=>v>=75000)||deltas.reduce((a,b)=>a+b,0)>=150000) {state.stopped=true;state.stop_reason='Soft quota cap reached';}
      for(const p of profiles){
        const r=await fetch('https://gpt-api.cc/api/log/token/',{headers:{Authorization:'Bearer '+keys[p.connection-1]},signal:AbortSignal.timeout(15000)});
        const j=await r.json();
        if(!r.ok||!Array.isArray(j.data))throw Error('Request-level quota logs unavailable');
        const ids=new Set(state.attempts.filter(a=>a.connection===p.connection).map(a=>a.request_id).filter(Boolean));
        for(const record of j.data){
          if(ids.has(record.request_id)&&!state.billing_records.some(x=>x.request_id===record.request_id)){
            const clean={connection:p.connection};
            for(const k of ['request_id','type','quota','prompt_tokens','completion_tokens','created_at','model_name'])clean[k]=record[k];
            state.billing_records.push(clean);
          }
        }
      }
    } catch(e) {state.stopped=true;state.stop_reason='Quota checkpoint failed: '+e.message;}
    await save();
  };
  async function send(profile, job, phase) {
    const key=keys[profile.connection-1];
    for(let retry=0;retry<2;retry++) {
      if(retry) await pause(2000+Math.floor(Math.random()*1000));
      const a={phase,connection:profile.connection,model_requested:profile.label,job_id:job.id,started_at_utc:new Date().toISOString(),prompt_sha256:sha(job.prompt),http_status:null,complete:false};
      state.attempts.push(a);await save();const start=performance.now();
      try {
        const r=await fetch('https://gpt-api.cc/v1/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},redirect:'error',signal:AbortSignal.timeout(60000),body:JSON.stringify({model:profile.label,messages:[{role:'user',content:job.prompt}],max_tokens:4096,stream:true,stream_options:{include_usage:true}})});
        a.http_status=r.status;a.headers_ms=performance.now()-start;a.request_id=r.headers.get('x-request-id')??r.headers.get('x-oneapi-request-id');
        const reader=r.body.getReader(), decoder=new TextDecoder();let raw='';
        for(;;){const chunk=await reader.read();if(chunk.done)break;if(a.first_chunk_ms===undefined)a.first_chunk_ms=performance.now()-start;raw+=decoder.decode(chunk.value,{stream:true});if(raw.length>1000000){await reader.cancel();throw Error('Response too large');}}
        raw+=decoder.decode();a.raw_body=raw.replaceAll(key,'[redacted]');
        if(r.ok){
          const events=[];
          for(const block of raw.replace(/\r\n/g,'\n').split('\n\n')){const s=block.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(!s||s==='[DONE]')continue;try{events.push(JSON.parse(s));}catch{a.stream_parse_error=true;}}
          if(!events.length){const j=JSON.parse(raw);a.text=j.choices?.[0]?.message?.content??'';a.finish_reason=j.choices?.[0]?.finish_reason;a.usage=j.usage;a.model_returned=j.model;}
          else {a.text=events.map(e=>e.choices?.[0]?.delta?.content??'').join('');a.finish_reason=events.map(e=>e.choices?.[0]?.finish_reason).filter(Boolean).at(-1);a.usage=events.map(e=>e.usage).filter(Boolean).at(-1);a.model_returned=events.map(e=>e.model).filter(Boolean).at(-1);}
          a.complete=a.finish_reason==='stop'&&!a.stream_parse_error;
          if(a.complete){try{a.answer=JSON.parse(a.text);}catch{a.answer_parse_error=true;}}
        }
      }catch(e){a.error_type=e.name;a.error_message=String(e.message).replaceAll(key,'[redacted]');}
      a.elapsed_ms=performance.now()-start;await save();
      if(a.complete)return a;
      const transient=[408,429,500,502,503,504].includes(a.http_status)||['TimeoutError','TypeError'].includes(a.error_type);
      if(!transient||retry===1){state.stopped=true;state.stop_reason='Unsuccessful request after bounded attempts; no answer-based retries';await save();return a;}
    }
  }
  const byFamily={};
  for(const kind of ['stock','overlap','latest']){
    const sample=['english','chinese','mixed'].map(arm=>schedule.find(r=>r.family===kind&&r.rep===1&&r.arm===arm));
    byFamily[kind]=Object.fromEntries(sample.map(r=>[r.arm,r.prompt.split('\nReturn JSON only:')[0]]));
  }
  const reviewJob={id:'all-templates-semantic-review',prompt:'Review these English, Chinese-only and mixed task instructions for semantic equivalence, including field names, comparisons, tie rules, output order and no missing conditions. Do not solve any data. Return ONLY JSON {"families":[{"family":"stock","equivalent":true,"reason":"..."},{"family":"overlap","equivalent":true,"reason":"..."},{"family":"latest","equivalent":true,"reason":"..."}]}. Mark false for a real ambiguity or meaning change.\n'+JSON.stringify(byFamily)};
  await dump('review-request.json',reviewJob);
  await save();
  async function review() {
    if(state.phase!=='review')throw Error('Wrong phase');
    for(const p of profiles){if(state.stopped)break;const a=await send(p,reviewJob,'review');state.reviews.push({connection:p.connection,attempt_index:state.attempts.indexOf(a)});await save();}
    await checkpoint();
    const approved=state.reviews.length===profiles.length&&state.reviews.every(r=>{const a=state.attempts[r.attempt_index];return a.complete&&Array.isArray(a.answer?.families)&&a.answer.families.length===3&&['stock','overlap','latest'].every(f=>a.answer.families.some(x=>x.family===f&&x.equivalent===true));});
    if(!approved){state.stopped=true;state.stop_reason='Semantic review did not approve all templates; preserve evidence, do not run targets';}
    if(!state.stopped)state.phase='target';await save();return {approved,stopped:state.stopped,reviews:state.reviews.map(r=>({connection:r.connection,answer:state.attempts[r.attempt_index].answer})),checkpoint:state.checkpoints.at(-1)};
  }
  const queues=new Map();
  for(const p of profiles){let seed=60409+p.connection;const q=[...schedule];for(let i=q.length-1;i>0;i--){seed=(Math.imul(seed,1664525)+1013904223)>>>0;const j=Math.floor(seed/2**32*(i+1));[q[i],q[j]]=[q[j],q[i]];}queues.set(p.connection,q);}
  const jobs=profiles.flatMap(p=>queues.get(p.connection).map(r=>({...r,connection:p.connection,model_requested:p.label,id:r.case+'|'+r.arm+'|'+r.rep,prompt:r.system+'\n\n'+r.prompt})));
  await dump('target-schedule.json',jobs);
  await dump('preflight-freeze.json',{at_utc:new Date().toISOString(),files:Object.fromEntries(await Promise.all(['execution-amendment.json','review-request.json','target-schedule.json'].map(async n=>[n,sha(await fs.readFile(path.join(dir,n)))])))});
  async function batch(count=5){
    if(state.phase!=='target'||state.stopped)return status();
    await Promise.all(profiles.map(async p=>{
      const queue=queues.get(p.connection);
      for(let i=0;i<count&&queue.length&&!state.stopped;i++){
        const r=queue.shift();const job=jobs.find(j=>j.connection===p.connection&&j.id===r.case+'|'+r.arm+'|'+r.rep);
        const a=await send(p,job,'target');state.trials.push({connection:p.connection,case:r.case,family:r.family,arm:r.arm,rep:r.rep,job_id:job.id,attempt_index:state.attempts.indexOf(a)});await save();
      }
    }));
    await checkpoint();
    state.complete=state.trials.length===schedule.length*profiles.length&&state.trials.every(t=>state.attempts[t.attempt_index].complete);
    if(state.complete){state.phase='complete';state.ended_at_utc=new Date().toISOString();await save();}
    return status();
  }
  function status(){return {phase:state.phase,complete:state.complete,stopped:state.stopped,stop_reason:state.stop_reason,trials:state.trials.length,attempts:state.attempts.length,by_connection:profiles.map(p=>({connection:p.connection,trials:state.trials.filter(t=>t.connection===p.connection).length})),checkpoint:state.checkpoints.at(-1)};}
  return {review,batch,status,state,checkpoint};
}
