import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

directory = Path('outputs/genuine-mix-v060')


def oracle(kind, p):
    if kind == 'stock':
        return {'ids': [r['id'] for r in p if r['active'] is True and r['on_hand']-r['reserved'] < r['reorder_limit']]}
    if kind == 'overlap':
        return {'ids': [r['id'] for r in p['events'] if r['start'] < p['query']['end'] and r['end'] > p['query']['start']]}
    if kind == 'latest':
        latest = {}
        for r in p:
            if r['device'] not in latest or r['ts'] >= latest[r['device']]['ts']:
                latest[r['device']] = r
        return {'devices': sorted(k for k, r in latest.items() if r['state'] == 'online')}
    if kind == 'refund':
        return {'total_cents': sum(r['paid_cents']-r['refunded_cents'] for r in p if r['currency'] == 'USD' and r['status'] == 'settled')}
    if kind == 'unique':
        seen, result = set(), []
        for label in p:
            text = label.strip()
            if text and text.casefold() not in seen:
                result.append(text)
                seen.add(text.casefold())
        return {'labels': result}
    if kind == 'dependencies':
        return {'ids': [r['id'] for r in p['tasks'] if r['done'] is False and set(r['dependencies']) <= set(p['completed'])]}
    if kind == 'phone':
        return {'phones': [(r.get('contact') or {}).get('phone') for r in p]}
    if kind == 'literal':
        return {'value': p['text'].split('<value>')[1].split('</value>')[0]}
    if kind == 'utc':
        times = [datetime.fromisoformat(r['local'])-timedelta(minutes=r['offset_minutes']) for r in p]
        i = min(range(len(p)), key=lambda i: times[i])
        return {'id': p[i]['id'], 'utc': times[i].strftime('%Y-%m-%dT%H:%MZ')}
    if kind == 'ranking':
        return {'ids': [r['id'] for r in sorted((r for r in p if r['eligible']), key=lambda r: (-r['score'], r['penalty'], r['id']))[:3]]}
    raise ValueError(kind)


data = json.loads((directory / 'dataset.json').read_text(encoding='utf-8'))
for case in data['cases']:
    assert {'answer': oracle(case['template'], case['payload'])} == case['expected'], case['id']
(directory / 'oracle-check.py').write_bytes(Path(__file__).read_bytes())
(directory / 'preflight.json').write_text(json.dumps({
    'cases_checked': 20, 'expected_answer_checks': 'all passed',
    'oracle_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'independence': 'Separate arithmetic/rule derivation, same assistant author; not external review.'
}, indent=2)+'\n', encoding='utf-8')
print('All 20 hand-authored expected answers match separate rule derivations.')
