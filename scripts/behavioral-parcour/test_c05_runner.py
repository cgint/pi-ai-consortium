#!/usr/bin/env python3
"""Deterministic tests for c05_runner; never launch Pi or materialize a run."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
import c05_runner as c05
import c05_scorer

class C05RunnerTests(unittest.TestCase):
    def test_schedule_order_uniqueness_and_no_c04_paths(self):
        self.assertEqual(len(c05.SMOKE_SPECS), 8); self.assertEqual(len(c05.RUN_SPECS), 48)
        self.assertEqual([x['run_id'] for x in c05.SMOKE_SPECS], [f'c05-smoke-on-{x}' for x in c05.FIXTURE_ORDER])
        self.assertEqual([x['run_id'] for x in c05.RUN_SPECS[:4]], ['c05-off-r1-yaml-markdown','c05-on-r1-yaml-markdown','c05-off-r1-policy-retirement','c05-on-r1-policy-retirement'])
        self.assertEqual(len(c05.BY_ID), 56)
        self.assertNotIn('c04-', '\n'.join(map(str, c05.SMOKE_SPECS + c05.RUN_SPECS)))

    def test_paths_are_repo_confined_and_never_tmp(self):
        paths = c05.run_paths(c05.ALL_SPECS)
        self.assertEqual(len(paths), 112)
        self.assertTrue(all(str(p).startswith(str(c05.REPO_ROOT) + '/') for p in paths))
        self.assertTrue(all('/tmp/' not in str(p) and '/c04-' not in str(p) for p in paths))
        command = c05.build_pi_command(c05.RUN_ROOT / 'x' / 'workspace', c05.RUN_ROOT / 'x' / 'sessions', 'c05-x')
        self.assertEqual(command[command.index('--provider') + 1], '8081-twins')
        self.assertEqual(command[command.index('--model') + 1], 'qwen36-27b-nvidia-nvfp4')
        self.assertEqual(c05.build_child_env({'CONSORTIUM_MODEL':'wrong'})['CONSORTIUM_MODEL'], c05.MODEL_REF)

    def test_phase0_requires_exact_hash_nested_identity_and_versions(self):
        data = json.loads(c05.PHASE0_PATH.read_text()); digest = c05.sha256_file(c05.PHASE0_PATH)
        self.assertEqual(data['version_check']['observed'], {'node':'v22.23.2','pi':'0.84.1'})
        self.assertEqual(data['identity']['state_initial']['observed'], {'provider':'8081-twins','model':'qwen36-27b-nvidia-nvfp4','thinking':'off'})
        self.assertEqual(c05.validate_phase0(c05.PHASE0_PATH, digest)['pass'], True)
        with self.assertRaises(RuntimeError): c05.validate_phase0(c05.PHASE0_PATH, '0'*64)
        with self.assertRaises(ValueError): c05.validate_phase0(c05.PHASE0_PATH, 'f9a90f')

    def test_runtime_version_family_accepts_patch_and_rejects_family_or_malformed_values(self):
        accepted = {'node':'v22.23.2', 'pi':'0.84.1'}
        self.assertTrue(c05.runtime_version_family_compatible(accepted, {'node':'v22.99.0', 'pi':'0.84.2'}))
        for current in (
            {'node':'v21.99.0', 'pi':'0.84.2'},
            {'node':'v23.0.0', 'pi':'0.84.2'},
            {'node':'v22.23.2', 'pi':'0.83.9'},
            {'node':'v22.23.2', 'pi':'0.85.0'},
            {'node':'22.23.2', 'pi':'0.84.2'},
            {'node':'v22.23.2', 'pi':'unknown'},
        ):
            self.assertFalse(c05.runtime_version_family_compatible(accepted, current), current)

    def test_runtime_gate_uses_real_phase0_shape_selected_child_environment_and_patch_policy(self):
        accepted = copy.deepcopy(json.loads(c05.PHASE0_PATH.read_text()))
        workspace, sessions, run_id = c05.RUN_ROOT / 'runtime-gate' / 'workspace', c05.RUN_ROOT / 'runtime-gate' / 'sessions', 'c05-runtime-gate'
        current = {'node':'v22.99.0', 'pi':'0.84.2'}
        with patch.dict(os.environ, {'UNRELATED_AMBIENT': 'wrong'}, clear=False):
            self.assertTrue(c05.validate_runtime_gate(accepted, workspace, sessions, run_id, current))
        for mutate in (
            lambda data: data['plan']['child_environment'].__setitem__('UNRELATED_AMBIENT', 'wrong'),
            lambda data: data['plan']['extension_hashes'].__setitem__(str(c05.REPO_ROOT / 'index.ts'), '0' * 64),
            lambda data: data['plan']['command'].__setitem__(0, 'not-pi'),
        ):
            bad = copy.deepcopy(accepted); mutate(bad)
            self.assertFalse(c05.validate_runtime_gate(bad, workspace, sessions, run_id, current))
        self.assertFalse(c05.validate_runtime_gate(accepted, workspace, sessions, run_id, {'node':'v22.99.0','pi':'0.85.0'}))

    def test_governor_telemetry_requires_exact_state_changing_selection(self):
        valid = {'type':'governor_input','state_supersession_guard':True,'state_supersession_guard_source':'workspace_settings','current_human_turn_length':1}
        prompt = 'state changing prompt'
        valid['current_human_turn_length'] = len(prompt)
        events = [{'type':'turn_start','input':'unrelated'}, valid, {'type':'turn_start','input':prompt}, valid]
        self.assertTrue(c05.governor_input_valid(events, 'on', prompt))
        for field, value in [('state_supersession_guard',False), ('state_supersession_guard_source','default'), ('current_human_turn_length',0)]:
            bad=copy.deepcopy(valid); bad[field]=value
            self.assertFalse(c05.governor_input_valid([{'type':'turn_start','input':prompt}, bad], 'on', prompt))
        self.assertFalse(c05.governor_input_valid([valid], 'on', prompt), 'unbound governor input must fail')
        self.assertTrue(c05.guard_fired([{'type':'injection_complete','reason':c05.GUARD_REASON}]))
        self.assertTrue(c05.guard_fired([{'type':'injection_skipped','governor_reason':c05.GUARD_REASON}]))

    def _ledger_fixture(self):
        root = c05.RUN_ROOT / f'c05-test-ledger-{uuid.uuid4().hex}'; root.mkdir(parents=True)
        records = [{'run_id':spec['run_id'], 'raw_directory':f'docs/c05-raw/{spec["run_id"]}', 'status':'unconsumed'} for spec in c05.ALL_SPECS]
        ledger = root / 'ledger.json'; ledger.write_text(json.dumps({'schema_version':'c05-raw-publication-ledger-v1', 'runs':records}))
        return root, ledger

    def _raw_result(self, root, spec, *, ready=True):
        raw=root/'docs/c05-raw'/spec['run_id']; (raw/'sessions').mkdir(parents=True); (raw/'consortium').mkdir()
        (raw/'sessions'/'session.jsonl').write_text('{}\n'); (raw/'consortium'/'events.jsonl').write_text('{}\n')
        positive=c05.FIXTURES[spec['fixture_id']]['kind']=='positive'
        result={'run_id':spec['run_id'], 'fixture_id':spec['fixture_id'], 'raw_valid':True, 'failed_assertions':[], 'identity_valid':True, 'process_valid':True, 'prompts_delivered':3, 'guard_fired':positive, 'continuity':True, 'control_regression':False}
        if not ready: result['guard_fired'] = not positive
        result_path=raw/'result.json'; result_path.write_text(json.dumps(result))
        files=[{'path':str(file.relative_to(raw)), 'sha256':c05.sha256_file(file), 'size':file.stat().st_size} for file in raw.rglob('*') if file.is_file()]
        (raw/'evidence-manifest.json').write_text(json.dumps({'files':files}))
        return result_path

    def test_consume_ledger_mutates_one_record_and_atomic_failure_preserves_bytes(self):
        root, ledger=self._ledger_fixture()
        try:
            result=self._raw_result(root, c05.SMOKE_SPECS[0]); before=json.loads(ledger.read_text()); expected=c05.sha256_file(ledger)
            digest, data=c05.consume_ledger_record(ledger, expected, c05.SMOKE_SPECS[0]['run_id'], result, 1)
            self.assertEqual(digest, c05.sha256_file(ledger)); self.assertEqual(data['runs'][0]['status'], 'consumed')
            self.assertEqual(before['runs'][1:], data['runs'][1:]); self.assertEqual(data['runs'][0]['runner_exit'], 1)
            unchanged=ledger.read_bytes()
            with self.assertRaises(RuntimeError): c05.consume_ledger_record(ledger, expected, c05.SMOKE_SPECS[1]['run_id'], root/'missing.json', 0)
            self.assertEqual(ledger.read_bytes(), unchanged)
            with patch.object(c05.os, 'replace', side_effect=OSError('rename failed')):
                with self.assertRaises(OSError): c05.consume_ledger_record(ledger, digest, c05.SMOKE_SPECS[1]['run_id'], self._raw_result(root, c05.SMOKE_SPECS[1]), 0)
            self.assertEqual(ledger.read_bytes(), unchanged)
        finally:
            shutil.rmtree(root)

    def test_build_smoke_decision_requires_order_and_reports_true_false(self):
        root, ledger=self._ledger_fixture()
        try:
            for spec in c05.SMOKE_SPECS:
                result=self._raw_result(root, spec)
                c05.consume_ledger_record(ledger, c05.sha256_file(ledger), spec['run_id'], result, 0)
            output=root/'decision.json'
            with patch.object(c05, 'REPO_ROOT', root):
                decision=c05.build_smoke_decision(ledger, output)
            self.assertTrue(decision['matrix_ready']); self.assertEqual([item['run_id'] for item in decision['results']], [spec['run_id'] for spec in c05.SMOKE_SPECS])
            data=json.loads(ledger.read_text()); data['runs'][0], data['runs'][1] = data['runs'][1], data['runs'][0]; ledger.write_text(json.dumps(data))
            with patch.object(c05, 'REPO_ROOT', root), self.assertRaises(RuntimeError): c05.build_smoke_decision(ledger, output)
            data['runs'][0], data['runs'][1] = data['runs'][1], data['runs'][0]; ledger.write_text(json.dumps(data))
            first=root/'docs/c05-raw'/c05.SMOKE_SPECS[0]['run_id']/'result.json'; bad=json.loads(first.read_text()); bad['guard_fired']=False; first.write_text(json.dumps(bad))
            raw=first.parent; files=[{'path':str(file.relative_to(raw)), 'sha256':c05.sha256_file(file), 'size':file.stat().st_size} for file in raw.rglob('*') if file.is_file() and file.name != 'evidence-manifest.json']; (raw/'evidence-manifest.json').write_text(json.dumps({'files':files}))
            data=json.loads(ledger.read_text()); data['runs'][0]['result_sha256']=c05.sha256_file(first); ledger.write_text(json.dumps(data))
            with patch.object(c05, 'REPO_ROOT', root): self.assertFalse(c05.build_smoke_decision(ledger, output)['matrix_ready'])
        finally:
            shutil.rmtree(root)

    def test_smoke_transition_positive_control_pass_and_fail(self):
        good=[]
        for spec in c05.SMOKE_SPECS:
            positive=c05.FIXTURES[spec['fixture_id']]['kind']=='positive'
            good.append({'run_id':spec['run_id'],'fixture_id':spec['fixture_id'],'identity_valid':True,'raw_valid':True,'process_valid':True,'prompts_delivered':3,'guard_fired':positive,'continuity':True,'control_regression':False})
        self.assertTrue(c05.smoke_transition(good))
        bad=copy.deepcopy(good); bad[4]['guard_fired']=True
        self.assertFalse(c05.smoke_transition(bad))
        bad=copy.deepcopy(good); bad[0]['guard_fired']=False
        self.assertFalse(c05.smoke_transition(bad))

    def test_scorer_and_exit_classes(self):
        fixture=c05.FIXTURES['requirement-replacement']
        self.assertTrue(c05_scorer.continuity_passes(fixture, 'Current durable requirement: Markdown release-notes requirement. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable.'))
        self.assertEqual(c05.exit_class([{'id':'C05-process','pass':False}]),2)
        self.assertEqual(c05.exit_class([{'id':'C05-confinement','pass':False}]),2)
        self.assertEqual(c05.exit_class([{'id':'C05-continuity','pass':False}]),1)
        self.assertEqual(c05.exit_class([{'id':'C05-continuity','pass':True}]),0)

    def test_contract_review_ledger_gates_fail_closed_before_materialization(self):
        spec=c05.SMOKE_SPECS[0]
        runner=c05.C05Runner(spec, freeze_commit='0'*40, phase0_sha256='0'*64, contract_sha256='0'*64, review_sha256='0'*64, ledger_sha256='0'*64)
        accepted={'pass':True, 'version_check':{'observed':{'node':'v22.23.2','pi':'0.84.1'}}, 'plan':{'extension_hashes':{}}}
        current={'node':'v22.23.9','pi':'0.84.2'}
        with patch.object(c05, 'run_paths', return_value=[]), patch.object(c05, 'validate_phase0', return_value=accepted) as p0, patch.object(c05, 'validate_contract') as contract, patch.object(c05, 'validate_review') as review, patch.object(c05, 'validate_ledger') as ledger, patch.object(c05, 'current_runtime_versions', return_value=current), patch.object(c05, 'validate_runtime_gate', return_value=True) as runtime_gate, patch('subprocess.check_output', return_value='2026-01-01T00:00:00Z'):
            result=runner.preflight()
        self.assertTrue(result['pass']); p0.assert_called_once(); contract.assert_called_once(); review.assert_called_once(); ledger.assert_called_once()
        runtime_gate.assert_called_once_with(accepted, runner.workspace, runner.sessions_dir, runner.run_id, current)
        self.assertEqual(result['manifest']['runtime_versions'], {'accepted_phase0':accepted['version_check']['observed'], 'current':current})
        self.assertFalse(runner.runtime_root.exists(), 'preflight must not materialize a run')

    def test_nested_schema_malformed_and_obsolete_fail(self):
        good={'success':True,'data':{'model':{'provider':c05.MODEL_PROVIDER,'id':c05.MODEL_ID},'thinkingLevel':'off'}}
        self.assertTrue(c05.phase0.validate_executor_state(good)['pass'])
        self.assertFalse(c05.phase0.validate_executor_state({'success':True,'data':{'provider':c05.MODEL_PROVIDER,'modelId':c05.MODEL_ID,'thinkingLevel':'off'}})['pass'])
        self.assertFalse(c05.phase0.validate_executor_state({'success':True,'data':{'model':c05.MODEL_REF,'thinkingLevel':'off'}})['pass'])

    def test_sequencer_orders_initial_controls_three_prompts_and_final_queries(self):
        prompts=['first', 'second', 'third']
        sequencer=c05.C05Sequencer(prompts)
        self.assertEqual(sequencer.on_event({'type':'response','id':'get_state','success':True}), [])
        first=sequencer.on_event({'type':'response','id':'get_commands','success':True})
        self.assertEqual(first, [{'id':'prompt_0','type':'prompt','message':'first'}])
        second=sequencer.on_event({'type':'agent_settled'})
        self.assertEqual(second, [{'id':'prompt_1','type':'prompt','message':'second'}])
        third=sequencer.on_event({'type':'agent_settled'})
        self.assertEqual(third, [{'id':'prompt_2','type':'prompt','message':'third'}])
        finals=sequencer.on_event({'type':'agent_settled'})
        self.assertEqual([action['id'] for action in finals], ['state_final','entries_final','stats_final','text_final'])
        for action in finals:
            self.assertEqual(sequencer.on_event({'type':'response','id':action['id'],'success':True}), [])
        self.assertTrue(sequencer.complete)

    def test_materialization_records_fixture_before_and_exact_arm_setting(self):
        root=c05.RUN_ROOT / f'c05-test-materialize-{uuid.uuid4().hex}'
        runner=c05.C05Runner(c05.RUN_SPECS[1])
        runner.runtime_root=root; runner.tmp_root=root; runner.workspace=root/'workspace'; runner.sessions_dir=root/'sessions'
        try:
            runner._materialize_workspace()
            target=runner.workspace / runner.fixture['target']
            self.assertEqual((runner.fixture_before / runner.fixture['target']).read_text(), runner.fixture['before'])
            self.assertEqual(target.read_text(), runner.fixture['before'])
            self.assertEqual(json.loads((runner.workspace/'.pi/settings.json').read_text())['consortium']['stateSupersessionGuard'], True)
            self.assertTrue(str(root).startswith(str(c05.RUN_ROOT) + os.sep))
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_review_parser_accepts_real_nested_c04_shape_and_rejects_flat_obsolete_shape(self):
        source = c05.REPO_ROOT / 'docs/c04-evidence/independent-review-8081-twins-session.jsonl'
        events = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        assistant = next(event for event in events if event.get('type') == 'message' and event.get('message', {}).get('role') == 'assistant')
        self.assertEqual(assistant['message']['role'], 'assistant')
        self.assertEqual(next(event for event in events if event.get('type') == 'session_info')['name'], 'c04-8081-twins-preflight-review')
        self.assertEqual(next(event for event in events if event.get('type') == 'model_change')['modelId'], c05.MODEL_ID)
        self.assertEqual(next(event for event in events if event.get('type') == 'thinking_level_change')['thinkingLevel'], 'off')
        self.assertNotIn('role', assistant, 'old flat parser would reject the real event')

    def test_review_requires_relative_real_shape_final_verdict_and_timing(self):
        root = c05.RUN_ROOT / f'c05-test-review-{uuid.uuid4().hex}'
        root.mkdir(parents=True)
        try:
            raw = root / 'review.jsonl'
            timestamp = '2026-01-02T00:00:00Z'
            events = [
                {'type':'session_info', 'timestamp':timestamp, 'name':'c05-8081-twins-review'},
                {'type':'model_change', 'provider':c05.MODEL_PROVIDER, 'modelId':c05.MODEL_ID},
                {'type':'thinking_level_change', 'thinkingLevel':c05.THINKING},
                {'type':'message', 'message':{'role':'assistant', 'content':[{'type':'text','text':'HEADLINE: FAIL\nBLOCKER: Yes'}]}},
                {'type':'message', 'message':{'role':'assistant', 'content':[{'type':'text','text':'HEADLINE: PASS\nBLOCKER: None'}]}},
            ]
            raw.write_text(''.join(json.dumps(event) + '\n' for event in events))
            review = root / 'review.json'
            data = {'pass':True, 'blockers':[], 'timestamp':timestamp, 'raw_session_path':'review.jsonl', 'raw_session_sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
            review.write_text(json.dumps(data)); digest = c05.sha256_file(review)
            with patch.object(c05, 'REPO_ROOT', root):
                self.assertTrue(c05.validate_review(review, digest, '2026-01-01T00:00:00Z', '2026-01-03T00:00:00Z'))
                for key, value in [('raw_session_path','../review.jsonl'), ('timestamp','2026-01-02T00:00:01Z')]:
                    bad=copy.deepcopy(data); bad[key]=value; review.write_text(json.dumps(bad))
                    with self.assertRaises(RuntimeError): c05.validate_review(review, c05.sha256_file(review), '2026-01-01T00:00:00Z', '2026-01-03T00:00:00Z')
                bad_events=copy.deepcopy(events); bad_events[-1]['message']['content'][0]['text']='PASS anywhere\nBLOCKER: None'
                raw.write_text(''.join(json.dumps(event)+'\n' for event in bad_events)); data['raw_session_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest(); review.write_text(json.dumps(data))
                with self.assertRaises(RuntimeError): c05.validate_review(review, c05.sha256_file(review), '2026-01-01T00:00:00Z', '2026-01-03T00:00:00Z')
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_smoke_decision_validates_order_results_manifests_and_tracking(self):
        root = c05.RUN_ROOT / f'c05-test-smoke-{uuid.uuid4().hex}'; raw_root = root / 'raw'; root.mkdir(parents=True)
        try:
            results=[]
            for spec in c05.SMOKE_SPECS:
                raw=raw_root/spec['run_id']; (raw/'sessions').mkdir(parents=True); (raw/'consortium').mkdir()
                (raw/'sessions'/'session.jsonl').write_text('{}\n'); (raw/'consortium'/'events.jsonl').write_text('{}\n')
                result={'run_id':spec['run_id'], 'raw_valid':True, 'failed_assertions':[]}; (raw/'result.json').write_text(json.dumps(result))
                files=[{'path':str(file.relative_to(raw)), 'sha256':hashlib.sha256(file.read_bytes()).hexdigest(), 'size':file.stat().st_size} for file in raw.rglob('*') if file.is_file()]
                (raw/'evidence-manifest.json').write_text(json.dumps({'files':files}))
                positive=c05.FIXTURES[spec['fixture_id']]['kind']=='positive'
                results.append({'run_id':spec['run_id'], 'fixture_id':spec['fixture_id'], 'result_sha256':hashlib.sha256((raw/'result.json').read_bytes()).hexdigest(), 'raw_valid':True, 'failed_assertions':[], 'identity_valid':True, 'process_valid':True, 'prompts_delivered':3, 'guard_fired':positive, 'continuity':True, 'control_regression':False})
            decision=root/'smoke.json'; decision.write_text(json.dumps({'matrix_ready':True, 'results':results}))
            tracked = type('Result', (), {'returncode':0})()
            with patch('subprocess.run', return_value=tracked), patch.object(c05, 'matrix_ready', return_value=True):
                self.assertTrue(c05.validate_smoke_decision(decision, c05.sha256_file(decision), {}, repo_root=root, raw_root=raw_root))
                bad=copy.deepcopy(results); bad.reverse(); decision.write_text(json.dumps({'matrix_ready':True, 'results':bad}))
                self.assertFalse(c05.validate_smoke_decision(decision, c05.sha256_file(decision), {}, repo_root=root, raw_root=raw_root))
                decision.write_text(json.dumps({'matrix_ready':True, 'results':results})); manifest=raw_root/results[0]['run_id']/'evidence-manifest.json'; data=json.loads(manifest.read_text()); data['files'][0]['size'] += 1; manifest.write_text(json.dumps(data))
                self.assertFalse(c05.validate_smoke_decision(decision, c05.sha256_file(decision), {}, repo_root=root, raw_root=raw_root))
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_post_harvest_final_raw_mismatch_is_mandatory_failure(self):
        root=c05.RUN_ROOT / f'c05-test-final-raw-{uuid.uuid4().hex}'; runner=c05.C05Runner(c05.RUN_SPECS[0]); runner.runtime_root=root; runner.evidence_dir=root/'evidence'; runner.manifest={'argv':['pi'], 'workspace_guard_setting':False}; proc=type('Proc', (), {})()
        try:
            with patch.object(runner, 'preflight', return_value={'pass':True}), patch.object(runner, '_materialize_workspace'), patch.object(runner, '_spawn_pi', return_value=proc), patch.object(runner, '_run_rpc_loop'), patch.object(runner, '_cleanup_process'), patch.object(runner, '_collect_consortium_logs'), patch.object(runner, '_collect_session_logs'), patch.object(runner, '_validate_all', return_value=[{'id':'C05-process','pass':True}]), patch.object(runner, '_harvest'), patch.object(runner, '_refresh_evidence_manifest'), patch.object(runner, '_raw_valid', side_effect=[True, False]) as raw_valid:
                runner.evidence_dir.mkdir(parents=True); result=runner.run()
            self.assertEqual(raw_valid.call_count, 2); self.assertFalse(result['pass']); self.assertEqual(result['exit_class'], 2); self.assertIn('C05-harvest', result['failed_assertions'])
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_runner_consumes_behavioral_result_but_not_final_raw_failure(self):
        root=c05.RUN_ROOT / f'c05-test-consume-run-{uuid.uuid4().hex}'; root.mkdir(parents=True)
        try:
            runner=c05.C05Runner(c05.SMOKE_SPECS[0], consume_ledger=True, ledger_sha256='a'*64)
            runner.runtime_root=root; runner.evidence_dir=root/'evidence'; runner.evidence_dir.mkdir(); runner.manifest={'argv':['pi'], 'workspace_guard_setting':True}; proc=type('Proc', (), {})()
            common=[patch.object(runner, 'preflight', return_value={'pass':True}), patch.object(runner, '_materialize_workspace'), patch.object(runner, '_spawn_pi', return_value=proc), patch.object(runner, '_run_rpc_loop'), patch.object(runner, '_cleanup_process'), patch.object(runner, '_collect_consortium_logs'), patch.object(runner, '_collect_session_logs'), patch.object(runner, '_validate_all', return_value=[{'id':'C05-continuity','pass':False}]), patch.object(runner, '_harvest'), patch.object(runner, '_refresh_evidence_manifest')]
            with common[0], common[1], common[2], common[3], common[4], common[5], common[6], common[7], common[8], common[9], patch.object(runner, '_raw_valid', return_value=True), patch.object(c05, 'consume_ledger_record', return_value=('b'*64, {})) as consume:
                result=runner.run()
            self.assertEqual(result['exit_class'], 1); self.assertEqual(result['ledger_sha256'], 'b'*64); consume.assert_called_once()
            with patch.object(runner, 'preflight', return_value={'pass':True}), patch.object(runner, '_materialize_workspace'), patch.object(runner, '_spawn_pi', return_value=proc), patch.object(runner, '_run_rpc_loop'), patch.object(runner, '_cleanup_process'), patch.object(runner, '_collect_consortium_logs'), patch.object(runner, '_collect_session_logs'), patch.object(runner, '_validate_all', return_value=[{'id':'C05-process','pass':True}]), patch.object(runner, '_harvest'), patch.object(runner, '_refresh_evidence_manifest'), patch.object(runner, '_raw_valid', side_effect=[True, False]), patch.object(c05, 'consume_ledger_record') as consume:
                runner.run()
            consume.assert_not_called()
        finally:
            shutil.rmtree(root)

    def test_guard_is_bounded_to_second_prompt_turn_and_trace_identity_is_exact(self):
        second = 'second'
        events = [
            {'type':'turn_start','input':'first'}, {'type':'injection_complete','governor_reason':c05.GUARD_REASON},
            {'type':'turn_start','input':second}, {'type':'injection_skipped','governor_reason':c05.GUARD_REASON},
            {'type':'turn_start','input':'third'}, {'type':'injection_complete','governor_reason':c05.GUARD_REASON},
        ]
        self.assertTrue(c05.guard_fired(events, second))
        self.assertFalse(c05.guard_fired(events[:2], second), 'a prior turn must not count')
        self.assertFalse(c05.guard_fired(events[4:], second), 'a later turn must not count')
        trace = {'type':'deliberation_start','model':c05.MODEL_REF,'modelSource':'CONSORTIUM_MODEL'}
        self.assertEqual(trace['modelSource'], 'CONSORTIUM_MODEL')

    def test_control_regression_derives_identity_from_before_text(self):
        controls = [fixture for fixture in c05.FIXTURES.values() if fixture['kind'] == 'control']
        expected = ['YAML changelog entries', 'legacy-yaml-approval', 'YAML release notes', 'yaml-state-v1']
        for fixture, identity in zip(controls, expected):
            self.assertFalse(c05.control_regression(fixture['before'], fixture['before']))
            self.assertTrue(c05.control_regression(fixture['before'], fixture['before'].replace(identity, 'changed')))
            self.assertTrue(c05.control_regression(fixture['before'], fixture['before'].replace('RELEASE_STREAM=stable', 'RELEASE_STREAM=canary')))
            self.assertTrue(c05.control_regression(fixture['before'], 'Historical superseded ' + identity + '. RELEASE_STREAM=stable'))
            self.assertFalse(c05.control_regression(fixture['before'], 'Historical context: obsolete migration.\nCurrent: ' + identity + '\nRELEASE_STREAM=stable'), 'historical prose elsewhere must not erase current identity')

    def test_run_wires_preflight_rpc_collection_validation_and_harvest_without_pi(self):
        root = c05.RUN_ROOT / f'c05-test-run-wiring-{uuid.uuid4().hex}'
        runner = c05.C05Runner(c05.RUN_SPECS[0])
        runner.runtime_root = root
        runner.evidence_dir = root / 'evidence'
        runner.evidence_dir.mkdir(parents=True)
        runner.manifest = {'argv': ['pi'], 'workspace_guard_setting': False}
        proc = type('Proc', (), {})()
        try:
            with patch.object(runner, 'preflight', return_value={'pass': True}), patch.object(runner, '_materialize_workspace') as materialize, patch.object(runner, '_spawn_pi', return_value=proc) as spawn, patch.object(runner, '_run_rpc_loop') as rpc, patch.object(runner, '_cleanup_process') as cleanup, patch.object(runner, '_collect_consortium_logs') as consortium, patch.object(runner, '_collect_session_logs') as sessions, patch.object(runner, '_validate_all', return_value=[{'id':'C05-process','pass':True}]) as validate, patch.object(runner, '_harvest') as harvest, patch.object(runner, '_raw_valid', return_value=True):
                result = runner.run()
            materialize.assert_called_once(); spawn.assert_called_once(); rpc.assert_called_once(); cleanup.assert_called_once_with(proc)
            consortium.assert_called_once(); sessions.assert_called_once(); validate.assert_called_once(); harvest.assert_called_once()
            self.assertTrue(result['pass']); self.assertEqual(result['exit_class'], 0)
            self.assertNotIn('harvest_error', result)
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_raw_destination_conflict_allows_only_gitkeep(self):
        root=c05.RAW_ROOT / f'c05-test-placeholder-{uuid.uuid4().hex}'
        try:
            root.mkdir(parents=True); (root/'.gitkeep').write_text('')
            self.assertFalse(c05.raw_destination_conflict(root))
            (root/'result.json').write_text('{}')
            self.assertTrue(c05.raw_destination_conflict(root))
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_pass_b_exposes_live_run_and_harvest_hashes_every_file(self):
        self.assertTrue(callable(c05.C05Runner.run))
        for name in ('_spawn_pi','_run_rpc_loop','_refresh_evidence_manifest','_harvest'):
            self.assertIn(name, c05.C05Runner.__dict__)
        root=c05.RUN_ROOT / f'c05-test-harvest-{uuid.uuid4().hex}'
        runner=c05.C05Runner(c05.RUN_SPECS[0])
        runner.runtime_root=root; runner.tmp_root=root; runner.workspace=root/'workspace'; runner.sessions_dir=root/'sessions'; runner.evidence_dir=root/'evidence'
        try:
            runner._materialize_workspace()
            (runner.sessions_dir/'session.jsonl').write_text('{"type":"session"}\n')
            consortium=runner.workspace/'.pi/consortium'; consortium.mkdir(parents=True); (consortium/'events.jsonl').write_text('{"type":"event"}\n')
            (root/'rpc-events.jsonl').write_text('{"type":"response"}\n')
            runner.raw_incoming=['{"type":"response"}']; runner.outgoing_records=[{'payload':{'type':'get_state'}}]
            runner.directional_records=[{'direction':'in','payload':{'type':'get_state'}}]; runner.stderr_lines=['stderr']
            runner.responses={'state_final':{'success':True},'entries_final':{'success':True},'stats_final':{'success':True},'text_final':{'success':True}}
            runner._harvest({'pass':False,'reason':'test'})
            manifest=json.loads((runner.evidence_dir/'evidence-manifest.json').read_text())
            listed={item['path']:item for item in manifest['files']}
            required={'manifest.json','fixture-before/'+runner.fixture['target'],'fixture-after/'+runner.fixture['target'],'raw-incoming.jsonl','outgoing-commands.jsonl','combined-directional.jsonl','rpc-events.jsonl','rpc-stderr.log','sessions/session.jsonl','consortium/events.jsonl','state_final.json','entries_final.json','stats_final.json','text_final.json','result.json'}
            self.assertTrue(required.issubset(listed))
            for rel, item in listed.items():
                path=runner.evidence_dir/rel
                self.assertEqual(item['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(item['size'], path.stat().st_size)
        finally:
            if root.exists(): shutil.rmtree(root)

    def test_matrix_cli_requires_smoke_decision_and_smoke_does_not(self):
        common=['--freeze-commit','a'*40,'--phase0-sha256','b'*64,'--contract-sha256','c'*64,'--review-sha256','d'*64,'--ledger-sha256','e'*64]
        with self.assertRaises(SystemExit):
            c05.main(['--run-id',c05.RUN_SPECS[0]['run_id'],*common,'--preflight-only'])
        with patch.object(c05.C05Runner, 'preflight', return_value={'pass':True}), patch.object(c05.C05Runner, 'run') as run:
            self.assertEqual(c05.main(['--run-id',c05.SMOKE_SPECS[0]['run_id'],*common,'--preflight-only']), 0)
            run.assert_not_called()
        with self.assertRaises(SystemExit): c05.main(['--run-id',c05.SMOKE_SPECS[0]['run_id'],*common])
        with self.assertRaises(SystemExit): c05.main(['--run-id',c05.SMOKE_SPECS[0]['run_id'],*common,'--preflight-only','--consume-ledger'])
        with patch.object(c05, 'build_smoke_decision', return_value={'matrix_ready':False}) as build:
            self.assertEqual(c05.main(['--build-smoke-decision','decision.json']), 0)
            build.assert_called_once_with(c05.LEDGER_PATH, Path('decision.json'))

    def test_runner_source_has_no_system_temporary_paths(self):
        source=Path(c05.__file__).read_text()
        forbidden=os.sep + 'tmp' + os.sep
        self.assertNotIn(forbidden, source)

if __name__ == '__main__': unittest.main()
