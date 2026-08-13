import hashlib,json,shutil,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE))
import c05_aggregate as a
import c05_runner as r
class Tests(unittest.TestCase):
 def setUp(self): self.root=Path(tempfile.mkdtemp(dir=HERE.parent.parent/'.parcour-runs'));self.raw=self.root/'raw';self.ledger=self.root/'ledger.json';self.make()
 def tearDown(self): shutil.rmtree(self.root)
 def make(self, *,off=8,on=11):
  if self.raw.exists(): shutil.rmtree(self.raw)
  records=[]; positive_seen={'on':0,'off':0}
  for spec in r.ALL_SPECS:
   rid=spec['run_id']; d=self.raw/rid;(d/'sessions').mkdir(parents=True);(d/'consortium').mkdir();(d/'sessions'/'x.jsonl').write_text('{}');(d/'consortium'/'x.jsonl').write_text('{}')
   kind=r.FIXTURES[spec['fixture_id']]['kind']; positive=kind=='positive'; arm=spec['arm']; smoke=spec['smoke']
   continuity=True
   if not smoke and positive:
    continuity=positive_seen[arm] < (on if arm=='on' else off); positive_seen[arm]+=1
   result={'run_id':rid,'arm':arm,'repetition':spec.get('repetition'),'fixture_id':spec['fixture_id'],'fixture_kind':kind,'identity_valid':True,'process_valid':True,'raw_valid':True,'prompts_delivered':3,'failed_assertions':[],'continuity':continuity,'guard_fired':positive and arm=='on','control_regression':False,'wall_clock_ms':1,'tool_calls':2};(d/'result.json').write_text(json.dumps(result)); files=[{'path':str(x.relative_to(d)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'size':x.stat().st_size} for x in d.rglob('*') if x.is_file()];(d/'evidence-manifest.json').write_text(json.dumps({'files':files}));records.append({'run_id':rid,'status':'consumed','result_sha256':hashlib.sha256((d/'result.json').read_bytes()).hexdigest()})
  self.ledger.write_text(json.dumps({'schema_version':'c05-raw-publication-ledger-v1','runs':records}))
 def refresh(self, index):
  d=self.raw/r.ALL_SPECS[index]['run_id']; files=[{'path':str(x.relative_to(d)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'size':x.stat().st_size} for x in d.rglob('*') if x.is_file() and x.name!='evidence-manifest.json'];(d/'evidence-manifest.json').write_text(json.dumps({'files':files}));ledger=json.loads(self.ledger.read_text());ledger['runs'][index]['result_sha256']=hashlib.sha256((d/'result.json').read_bytes()).hexdigest();self.ledger.write_text(json.dumps(ledger))
 def test_positive_and_negative_gates(self):
  out=a.aggregate(self.ledger,self.raw);self.assertEqual(len(out['smoke_records']),8);self.assertEqual(len(out['cell_records']),48);self.assertEqual(len(out['paired_records']),24);self.assertEqual(out['denominators'],{'smoke':8,'matrix':48,'on_positive':12,'off_positive':12,'controls':24,'on_controls':12});self.assertEqual(out['mechanism'],{'on_positive_fires':12,'off_positive_fires':0,'control_fires':0,'on_control_fires':0,'pass':True});self.assertTrue(out['smoke_transition']);self.assertTrue(out['bounded_uplift']);self.make(on=10);self.assertFalse(a.aggregate(self.ledger,self.raw)['bounded_uplift'])
 def test_smoke_transition_and_mechanism_are_uplift_gates(self):
  d=self.raw/r.ALL_SPECS[0]['run_id'];result=json.loads((d/'result.json').read_text());result['guard_fired']=False;(d/'result.json').write_text(json.dumps(result));self.refresh(0);out=a.aggregate(self.ledger,self.raw);self.assertFalse(out['smoke_transition']);self.assertFalse(out['bounded_uplift'])
 def test_control_failure_and_byte_mismatch_fail(self):
  index=next(i for i,spec in enumerate(r.ALL_SPECS) if not spec['smoke'] and r.FIXTURES[spec['fixture_id']]['kind']=='control');d=self.raw/r.ALL_SPECS[index]['run_id'];result=json.loads((d/'result.json').read_text());result['control_regression']=True;(d/'result.json').write_text(json.dumps(result));self.refresh(index);out=a.aggregate(self.ledger,self.raw);self.assertEqual(out['controls']['regressions'],1);self.assertFalse(out['bounded_uplift']);self.make();(self.raw/r.ALL_SPECS[0]['run_id']/'sessions'/'x.jsonl').write_text('changed');
  with self.assertRaises(RuntimeError):a.aggregate(self.ledger,self.raw)
if __name__=='__main__':unittest.main()
