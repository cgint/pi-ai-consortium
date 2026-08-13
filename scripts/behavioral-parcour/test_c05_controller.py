import hashlib, json, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent; sys.path.insert(0,str(HERE))
import c05_controller as c
import c05_runner as r
class Tests(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(dir=HERE.parent.parent/'.parcour-runs')); self.ledger=self.root/'ledger.json'; self.frozen={x:('a'*40 if x=='freeze_commit' else 'b'*64) for x in ('freeze_commit','phase0_sha256','contract_sha256','review_sha256')}; self.write()
 def tearDown(self): shutil.rmtree(self.root)
 def write(self): self.ledger.write_text(json.dumps({'schema_version':'c05-raw-publication-ledger-v1','runs':[{'run_id':s['run_id'],'raw_directory':f'docs/c05-raw/{s["run_id"]}','status':'unconsumed'} for s in r.ALL_SPECS]}))
 def test_exact_smoke_command_and_default_plan(self):
  with patch.object(c,'REPO_ROOT',self.root):
   p=c.next_plan(self.ledger,self.frozen); self.assertTrue(p['smoke']); self.assertEqual(p['argv'][-1],'--consume-ledger'); self.assertIn(c.sha256(self.ledger),p['argv'])
 def test_stale_order_and_conflict_stop(self):
  data=json.loads(self.ledger.read_text()); data['runs'][1]['status']='consumed'; self.ledger.write_text(json.dumps(data))
  with self.assertRaises(RuntimeError): c.next_plan(self.ledger,self.frozen)
  self.write()
  with patch.object(c,'REPO_ROOT',self.root), patch.object(r,'raw_destination_conflict',return_value=True):
   with self.assertRaises(RuntimeError): c.next_plan(self.ledger,self.frozen)
 def test_smoke_behavioral_exit_continues_smoke_but_categorically_blocks_matrix(self):
  data=json.loads(self.ledger.read_text()); data['runs'][0]['status']='consumed'; self.ledger.write_text(json.dumps(data))
  with patch.object(c,'REPO_ROOT',self.root):
   self.assertEqual(c.next_plan(self.ledger,self.frozen)['run_id'],r.SMOKE_SPECS[1]['run_id'])
  [x.update(status='consumed') for x in data['runs'][:8]]; self.ledger.write_text(json.dumps(data)); decision=self.root/'smoke-decision.json'; decision.write_text('{}')
  with patch.object(c,'REPO_ROOT',self.root), patch.object(r,'validate_smoke_decision',return_value=False):
   with self.assertRaises(RuntimeError): c.next_plan(self.ledger,self.frozen,smoke_decision=decision)
 def test_execute_once_captures_one_console_and_preserves_exit_classes(self):
  plan={'state':'ready','run_id':'x','argv':['fake']}
  with patch('subprocess.run',return_value=type('P',(),{'returncode':1,'stdout':'o','stderr':'e'})()) as run:
   self.assertEqual(c.execute_once(plan,self.root),1); run.assert_called_once()
  self.assertTrue((self.root/'x-console.json').is_file()); self.assertEqual(c.execute_once({'state':'complete'},self.root),2)
if __name__=='__main__': unittest.main()
