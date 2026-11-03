// Explicit opt-in network runner for a NEW execution of the frozen study.
// Keys are read from environment variables, never written to artifacts.
import fs from 'node:fs/promises';
import path from 'node:path';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [inputArg, outputArg] = process.argv.slice(2);
if (!inputArg || !outputArg) {
  throw Error('Usage: node research/run_heldout_v060.mjs INPUT_DIR NEW_OUTPUT_DIR');
}
const input = path.resolve(inputArg), output = path.resolve(outputArg);
if (input === output) throw Error('Use a separate output directory; preserve the published study.');
const keys = ['', process.env.GATEWAY_GPT_KEY, process.env.GATEWAY_GEMINI_KEY];
if (!keys[1] || !keys[2]) throw Error('Set GATEWAY_GPT_KEY and GATEWAY_GEMINI_KEY for https://gpt-api.cc.');
try {
  await fs.access(path.join(output, 'results.json'));
  throw Error('Output already contains a run; refusing to overwrite or resend it.');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
const hash = b => createHash('sha256').update(b).digest('hex');
async function source(name) {
  try { return await fs.readFile(path.join(input, name)); }
  catch (e) { if (e.code !== 'ENOENT') throw e; return gunzipSync(await fs.readFile(path.join(input, name + '.gz'))); }
}
const protocol = JSON.parse(await source('protocol.json'));
for (const [name, expected] of Object.entries(protocol.files)) {
  if (hash(await source(name)) !== expected) throw Error('Frozen file changed: ' + name);
}
if (hash(await source('grader-source.py')) !== protocol.grader_source_sha256) throw Error('Frozen grader changed.');
const execution = JSON.parse(await source('execution.json'));
if (hash(await source('runner.mjs')) !== execution.runner_sha256) throw Error('Frozen runner changed.');
await fs.mkdir(output, {recursive:true});
for (const name of ['dataset.json','preparation.json','requests.json','protocol.json','grader-source.py','runner.mjs']) {
  await fs.writeFile(path.join(output,name), await source(name));
}
await fs.writeFile(path.join(output,'execution.json'), JSON.stringify({
  ...execution,
  note:'New independent execution of the frozen inputs; do not pool with the published run.',
  recorded_at_utc:new Date().toISOString()
},null,2)+'\n');
const profiles = protocol.model_labels.map((label,i) => ({connection:i+2,label,trials:[],request_attempts:[],stopped:false,complete:false}));
const report = {
  complete:false,provider:'https://gpt-api.cc',
  identity_verification:'Unverified third-party gateway model labels; not direct provider access.',
  dataset_sha256:protocol.files['dataset.json'],prepared_source_sha256:protocol.files['preparation.json'],grader_sha256:protocol.grader_source_sha256,
  protocol:{...protocol,concurrency_per_model:2,max_output_tokens:4096,timeout_ms:60000,max_attempts:2,stream:true,temperature:'provider default'},
  limitations:protocol.limitations,profiles,started_at_utc:new Date().toISOString()
};
const {createGatewayStudy} = await import(pathToFileURL(path.join(input,'runner.mjs')).href);
const root = process.cwd(), relativeDir = path.relative(root,output);
const study = await createGatewayStudy(root,keys,report,{
  relativeDir,datasetPath:path.join(relativeDir,'dataset.json'),preparedPath:path.join(relativeDir,'preparation.json'),
  requests:JSON.parse(await source('requests.json')),requestsPerModel:150,keepFailedTrials:true,continueTransientFailures:true
});
console.log(JSON.stringify(await study.batch(150)));
