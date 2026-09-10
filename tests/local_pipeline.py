"""Optional local integration inputs regenerated together, never stale reports."""
import atexit
import json
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

from tools.localization.analysis import load_datasets
from tools.localization.human_reviews import implementation_ledger, load_ledger
from tools.localization import scope, context_overrides, patch_plan, layout_plan, mod_build
from tools.localization.blocked_audit import serialize_json


@lru_cache(None)
def inputs(historical=False):
    if not Path('source/de/jp/key-value/key-value-strings-utf8.txt').exists():
        raise unittest.SkipTest('Optional local official data unavailable')
    data=load_datasets(Path('source'))
    formal_ledger=load_ledger()
    phase2a_deferred=any(r.get('implementation_status')=='adjudicated_not_patch_enabled'
                         for r in formal_ledger['records'])
    ledger=implementation_ledger(formal_ledger)
    if historical:
        ids=set(ledger['baseline_ids'])|{'5115','5118','5130','5186','5205'}
        ledger['records']=[r for r in ledger['records'] if r['string_id'] in ids]
        # Historical approved terminology, reconstructed only in memory.
        # Source evidence signatures are unchanged; no backup ledger required.
        rocketry=next(r for r in ledger['records'] if r['string_id']=='7432')
        rocketry.update(decision='restore',proposed_jp='砲弾術')
    Path('reports').mkdir(exist_ok=True)
    temp=tempfile.TemporaryDirectory(dir='reports');atexit.register(temp.cleanup)
    root=Path(temp.name);sd=root/'scope';sd.mkdir()
    lp=root/'names.json';lp.write_text(serialize_json(ledger),encoding='utf8')
    audit=scope.build_scope(data,ledger,context_path=None if historical else context_overrides.DEFAULT_PATH)
    (sd/'scope-audit.tsv').write_text(scope.render_audit(audit),encoding='utf8')
    (sd/'scope-metadata.json').write_text(serialize_json({k:v for k,v in audit.items() if k!='rows'}),encoding='utf8')
    rows,meta,hashes=patch_plan.read_audit(sd)
    hp=Path('reviews/phase1d-layout-decisions.json');human=json.loads(hp.read_text(encoding='utf8'))
    plan=layout_plan.integrate(data,ledger,rows,meta,hashes,human)
    pp=root/'patch-plan.json';pp.write_text(serialize_json({k:v for k,v in plan.items() if k!='blocked'}),encoding='utf8')
    return dict(data=data,ledger=ledger,formal_ledger=formal_ledger,phase2a_deferred=phase2a_deferred,
                rows=rows,meta=meta,hashes=hashes,human=human,plan=plan,
                args=(Path('source'),pp,lp,hp,sd),audit=audit)


@lru_cache(None)
def payload():
    item=inputs()
    if item['phase2a_deferred']:
        raise unittest.SkipTest('Phase 2A adjudications are recorded but patch/Mod implementation is not authorized')
    bundle=mod_build.prepare(*item['args'])
    Path('dist').mkdir(exist_ok=True)
    temp=tempfile.TemporaryDirectory(dir='dist');atexit.register(temp.cleanup)
    path=Path(temp.name)/'payload';mod_build.generate(bundle,path)
    return bundle,path
