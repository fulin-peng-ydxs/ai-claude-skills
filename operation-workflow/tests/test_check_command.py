"""Exercise scenario defaults, exceptions and legacy policies without execution."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('command_gate', ROOT / 'scripts/check_command.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
DOCKER = 'docker --host unix:///var/run/docker.sock '


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / 'assets/command-policy.json').read_text())
        self.policy['targets'] = [{'server_id': 'test-01', 'user': 'ops'}]
        self.policy['approval_ref'] = 'fixture:adopted'

    def decision(self, command, **kwargs):
        return GATE.classify(self.policy, kwargs.get('server_id', 'test-01'), kwargs.get('user', 'ops'), command)

    def legacy(self, **rules):
        self.policy = {
            'version': 1, 'targets': [{'server_id': 'test-01', 'user': 'ops'}],
            'approval_ref': 'fixture:legacy-approved', 'default': 'ask',
            'deny': ['rm -rf /'], 'ask': ['systemctl restart **'], 'allow': ['id'],
        }
        self.policy.update(rules)

    def test_default_allow_and_default_ask_have_only_the_opposite_exception_table(self):
        for scenario in self.policy['scenarios']:
            exception = 'ask' if scenario['default'] == 'allow' else 'allow'
            self.assertEqual({'name', 'prefix', 'default', exception}, set(scenario))
        docker = self.policy['scenarios'][0]
        self.assertEqual('allow', docker['default'])
        self.assertNotIn('allow', docker)
        result = self.decision(DOCKER+'new-subcommand query')
        self.assertEqual('allow', result['decision'])
        self.assertEqual('scenario-default', result['reason'])
        self.assertEqual('docker', result['scenario'])
        result = self.decision('unknown-program query')
        self.assertEqual('ask', result['decision'])
        self.assertEqual('general', result['scenario'])
        self.assertEqual('scenario-default', result['reason'])

    def test_default_ask_whitelist_and_default_allow_risk_exception(self):
        result = self.decision('id')
        self.assertEqual('allow', result['decision'])
        self.assertEqual('scenario-exception', result['reason'])
        self.assertEqual('ask', result['mode'])
        result = self.decision(DOCKER+'service update --force portal')
        self.assertEqual('ask', result['decision'])
        self.assertEqual('scenario-exception', result['reason'])
        self.assertEqual('allow', result['mode'])

    def test_queries_use_defaults_instead_of_a_docker_whitelist(self):
        for suffix in [
            'ps', 'ps -a --filter name=portal --no-trunc',
            "ps --format '{{.ID}} {{.Names}}' --filter status=running",
            'container list --all --quiet', 'service ls --format json',
            'container inspect rm', 'service inspect exec',
            "inspect --format '{{json .State}}' restart",
            'logs --tail 20 --since 5m portal', 'service logs --tail=30 --timestamps portal',
            "container stats portal --format '{{json .}}' --no-stream",
            'events --since 30m --until 2026-11-04T00:00:00Z',
            'future-read-command --filter name=rm',
        ]:
            with self.subTest(suffix=suffix):
                result = self.decision(DOCKER+suffix)
                self.assertEqual('allow', result['decision'])
                self.assertEqual('scenario-default', result['reason'])

    def test_state_changes_and_compound_execution_entries_ask(self):
        for suffix in [
            'run alpine', 'exec portal id', 'container exec portal id',
            'container restart portal', 'service create --name app alpine',
            'service update --force portal', 'service scale portal=2',
            'stack deploy -c stack.yml app', 'image pull alpine',
            'volume rm app-data', 'network connect app-net portal',
            'node demote node-1', 'swarm leave', 'context use production',
            'plugin install external/plugin', 'config inspect app-config',
            'compose -p app -f compose.yml down', 'compose -f compose.yml ps',
            'buildx build .',
        ]:
            with self.subTest(suffix=suffix):
                self.assertEqual('ask', self.decision(DOCKER+suffix)['decision'])
        for command in ['systemctl restart nginx.service', 'mkfs.ext4 /dev/example',
                        'dd if=/dev/example of=/dev/other', 'redis-cli INFO',
                        'mysql --execute=SELECT', 'apt-get update', 'git -C /opt/app push']:
            self.assertEqual('ask', self.decision(command)['decision'])

    def test_risk_options_cover_short_long_and_equals_forms(self):
        for suffix in [
            'ps --context production', 'ps --context=production', 'ps -cproduction',
            'ps --host tcp://other.invalid:2375', 'ps -Htcp://other.invalid:2375',
            'ps --config=/tmp/other', 'logs --follow --tail 20 portal',
            'container logs -ft portal', 'service logs --follow=true portal',
            'logs --details --tail 10 portal',
            "inspect --format '{{json .Config.Env}}' portal",
            "container inspect -f '{{json .Config.Env}}' portal",
            "service inspect --format='{{json .Spec.TaskTemplate.ContainerSpec.Env}}' portal",
            "image inspect '-f{{json .Config.Env}}' portal", "ps --format '{{.Command}}'",
            'inspect --type config app-config', 'inspect --type=config app-config',
            'stats portal --no-stream --no-stream=false',
        ]:
            with self.subTest(suffix=suffix):
                self.assertEqual('ask', self.decision(DOCKER+suffix)['decision'])

    def test_docker_global_options_cannot_shift_mutation_verbs(self):
        flags = ['--debug', '-D', '--debug=false', '-D=false',
                 '--log-level error', '--log-level=error', '-l error', '-lerror',
                 '-l=error', '-Dlerror', '--help=false', '-h=false',
                 '--version=false', '-v=false', '-Dv=false']
        for flag in flags:
            for group, action in [('service', 'update --force portal'),
                                  ('container', 'exec portal id'),
                                  ('volume', 'remove data')]:
                for command in [DOCKER+flag+' '+group+' '+action,
                                'docker '+flag+' --host unix:///var/run/docker.sock '+group+' '+action,
                                DOCKER+group+' '+flag+' '+action]:
                    with self.subTest(command=command):
                        self.assertEqual('ask', self.decision(command)['decision'])
            for command in [DOCKER+flag+' service inspect rm',
                            'docker '+flag+' --host unix:///var/run/docker.sock container inspect remove',
                            DOCKER+'service '+flag+' inspect exec']:
                with self.subTest(query=command):
                    self.assertEqual('allow', self.decision(command)['decision'])
        for command in ['docker -DHunix:///var/run/docker.sock service update --force portal',
                        'docker --host=unix:///var/run/docker.sock -D container exec portal id']:
            self.assertEqual('ask', self.decision(command)['decision'])

    def test_docker_mutation_aliases_have_identical_decisions(self):
        for area in ['container', 'image', 'volume', 'network', 'service', 'stack',
                     'node', 'config', 'secret', 'context', 'plugin']:
            for verb in ['rm', 'remove']:
                for flag in ['', '--debug ']:
                    command = DOCKER+flag+area+' '+verb+' target'
                    with self.subTest(command=command):
                        self.assertEqual('ask', self.decision(command)['decision'])
        for suffix in ['stack down app', 'stack deploy -c stack.yml app', 'stack up -c stack.yml app',
                       'debug portal', 'init', 'rm portal', 'rmi image', 'rename old new']:
            self.assertEqual('ask', self.decision(DOCKER+suffix)['decision'])
        for suffix in ['--debug inspect debug', 'service inspect remove', 'container inspect rm']:
            self.assertEqual('allow', self.decision(DOCKER+suffix)['decision'])

    def test_unknown_or_malformed_docker_global_options_do_not_default_allow(self):
        for suffix in ['--unknown service update --force portal',
                       'service --unknown update --force portal',
                       '--log-level', '--log-level --debug service update',
                       '--log-level=invalid service update', '--debug=invalid service update',
                       '-DZ service update', '-- service update',
                       '--tlsverify=false service ls', 'service --tls ls']:
            with self.subTest(suffix=suffix):
                self.assertEqual('ask', self.decision(DOCKER+suffix)['decision'])
        argv = GATE.tokens(DOCKER+'container exec portal echo --debug --log-level=error')
        self.assertEqual(argv, GATE.docker_arguments(argv))
        argv = GATE.tokens(DOCKER+"service inspect --format '{{.Spec.Name}}' remove")
        self.assertEqual(argv, GATE.docker_arguments(argv))

    def test_normalized_matching_preserves_deny_priority_and_prefix_identity(self):
        self.policy['deny'].append(DOCKER+'service update **')
        self.assertEqual('deny', self.decision(DOCKER+'--debug service update --force portal')['decision'])
        alternate = deepcopy(self.policy['scenarios'][0])
        alternate['name'] = 'same-endpoint'
        alternate['prefix'] = 'docker -Hunix:///var/run/docker.sock'
        self.policy['scenarios'].append(alternate)
        self.assertEqual('invalid-policy', self.decision(DOCKER+'ps')['reason'])

    def test_deny_host_option_spellings_cross_match_with_display_flags(self):
        prefixes = [
            'docker -Hunix:///var/run/docker.sock',
            'docker -H unix:///var/run/docker.sock',
            'docker -H=unix:///var/run/docker.sock',
            'docker --host unix:///var/run/docker.sock',
            'docker --host=unix:///var/run/docker.sock',
        ]
        original = list(self.policy['deny'])
        for rule_prefix in prefixes:
            rule = rule_prefix+' service inspect **'
            self.policy['deny'] = original+[rule]
            for command_prefix in prefixes:
                for flags in ['', '--debug ', '-D ', '--log-level=error ', '-Dlerror ']:
                    for suffix in [flags+'service inspect portal', 'service '+flags+'inspect portal']:
                        command = command_prefix+' '+suffix
                        with self.subTest(rule=rule, command=command):
                            result = self.decision(command)
                            self.assertEqual('deny', result['decision'])
                            self.assertEqual(rule, result['pattern'])
            self.assertEqual('allow', self.decision(DOCKER+'service ls')['decision'])
            self.assertEqual('allow', self.decision(DOCKER+'container inspect portal')['decision'])

    def test_deny_patterns_normalize_groups_glob_values_and_keep_operands_literal(self):
        for rule in [
            'docker {-Hunix:///var/run/docker.sock,--host=unix:///var/run/docker.sock} service inspect **',
            '{docker,podman} -Hunix:///var/run/docker.sock service inspect **',
            'docker -H* service inspect **',
            'docker --log-level=* -Hunix:///var/run/docker.sock service inspect **',
            'docker -Hunix:///var/run/docker.sock {container,service} inspect **',
        ]:
            with self.subTest(rule=rule):
                self.policy['deny'] = [rule]
                self.assertEqual('deny', self.decision(DOCKER+'--debug service inspect portal')['decision'])
        self.policy['deny'] = ['docker -Hunix:///var/run/docker.sock container exec portal echo -Hliteral']
        result = self.decision(DOCKER+'--debug container exec portal echo -Hliteral')
        self.assertEqual('deny', result['decision'])
        # An exec operand is not a Docker global host option.
        result = self.decision(DOCKER+'--debug container exec portal echo --host literal')
        self.assertEqual('ask', result['decision'])
        self.policy['deny'] = ['docker -Hunix:///var/run/docker.sock **']
        self.assertEqual('deny', self.decision(DOCKER+'ps')['decision'])

    def test_deny_boolean_spellings_are_equivalent_without_merging_true_and_false(self):
        enabled = ['--tlsverify', '--tlsverify=true', '--tlsverify=1', '--tlsverify=T']
        disabled = ['--tlsverify=false', '--tlsverify=0', '--tlsverify=F']
        for variants, opposite in [(enabled, disabled), (disabled, enabled)]:
            for spelling in variants:
                self.policy['deny'] = [DOCKER+spelling+' service inspect **']
                for actual in variants:
                    with self.subTest(rule=spelling, actual=actual):
                        self.assertEqual('deny', self.decision(DOCKER+actual+' --debug service inspect portal')['decision'])
                for actual in opposite:
                    self.assertEqual('ask', self.decision(DOCKER+actual+' service inspect portal')['decision'])

    def test_unresolvable_docker_deny_does_not_silently_disappear(self):
        for rule in [
            'docker --unknown service inspect **',
            'docker ** -Hunix:///var/run/docker.sock service inspect **',
            'dock* -Hunix:///var/run/docker.sock service inspect **',
            'docker --host unix:///var/run/docker.sock service * --host other',
            'docker --host {a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q} service inspect {a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q}',
        ]:
            with self.subTest(rule=rule):
                self.policy['deny'] = [rule]
                self.assertEqual('invalid-policy', self.decision(DOCKER+'ps')['reason'])

    def test_broken_policy_stays_distinct_from_an_ordinary_approved_ask(self):
        ordinary = self.decision(DOCKER+'service update --force portal')
        self.assertEqual('scenario-exception', ordinary['reason'])
        self.policy['scenarios'][0]['ask'] = None
        broken = self.decision(DOCKER+'service update --force portal')
        self.assertEqual('ask', broken['decision'])
        self.assertEqual('invalid-policy', broken['reason'])
        self.assertIsNone(broken['pattern'])
        self.assertNotIn('scenario', broken)

    def test_general_whitelist_stays_narrow_without_an_ask_table(self):
        for command in [
            'cat /etc/os-release', 'free -h', 'df -hPT /opt', 'stat -- /opt/app/config',
            'ps -eo pid,ppid,user,comm,%cpu,%mem', 'ip route show', 'ss -lntp',
            'systemctl is-active nginx.service', 'journalctl -u nginx.service -n 20 --no-pager',
            'git -C /opt/app rev-parse HEAD', 'du -sh -- /opt/app',
        ]:
            self.assertEqual('allow', self.decision(command)['decision'])
        for command in ['cat /etc/shadow', 'cat /opt/app/config.yml', 'ps aux',
                        'systemctl show nginx.service --property=Environment',
                        'systemctl status nginx.service -Hother.invalid',
                        'date --set=2026-11-04', 'hostname replacement',
                        'docker inspect portal', 'curl https://example.invalid/health']:
            self.assertEqual('ask', self.decision(command)['decision'])

    def test_common_deny_cannot_be_overridden_by_a_scenario(self):
        general = self.policy['scenarios'][1]
        general['default'] = 'allow'
        general['ask'] = []
        del general['allow']
        for command in [
            'rm -rf /', 'rm -rf -- /', 'rm -rf /etc', 'rm -rf /etc/', 'rm -rf / # comment',
            'ssh -o StrictHostKeyChecking=no ops@example.invalid',
            'ssh -oStrictHostKeyChecking=off ops@example.invalid',
            "ssh -o 'StrictHostKeyChecking false' ops@example.invalid",
        ]:
            with self.subTest(command=command):
                self.assertEqual('deny', self.decision(command)['decision'])

    def test_each_declared_exception_can_match_without_duplicate_patterns(self):
        for scenario in self.policy['scenarios']:
            key = 'ask' if scenario['default'] == 'allow' else 'allow'
            self.assertEqual(len(scenario[key]), len(set(scenario[key])))
            for pattern in scenario[key]:
                parts = [GATE.choices(part)[0].replace('*', 'example') for part in GATE.tokens(pattern)]
                command = scenario['prefix']+' '+shlex.join(parts)
                with self.subTest(scenario=scenario['name'], pattern=pattern):
                    self.assertEqual(key, self.decision(command)['decision'])

    def test_longest_prefix_selects_one_mode_without_merging_tables(self):
        nested = {'name': 'service', 'prefix': DOCKER+'service', 'default': 'ask', 'allow': ['ls **']}
        self.policy['scenarios'].append(nested)
        for order in [self.policy['scenarios'], list(reversed(self.policy['scenarios']))]:
            self.policy['scenarios'] = order
            result = self.decision(DOCKER+'service inspect portal')
            self.assertEqual('ask', result['decision'])
            self.assertEqual('service', result['scenario'])
            self.assertEqual('allow', self.decision(DOCKER+'service ls')['decision'])
            self.assertEqual('allow', self.decision(DOCKER+'container inspect portal')['decision'])

    def test_modes_empty_exceptions_and_no_matching_scenario(self):
        self.policy['scenarios'] = [{'name': 'one', 'prefix': 'probe', 'default': 'allow', 'ask': []}]
        self.assertEqual('allow', self.decision('probe value')['decision'])
        self.assertEqual('scenario-not-covered', self.decision('id')['reason'])
        self.policy['scenarios'] = [{'name': 'one', 'prefix': 'probe', 'default': 'ask', 'allow': []}]
        self.assertEqual('ask', self.decision('probe value')['decision'])

    def test_invalid_scenarios_and_three_tables_fail_closed(self):
        base = deepcopy(self.policy)
        mutations = [
            lambda p: p['scenarios'][0].update(allow=[]),
            lambda p: p['scenarios'][1].update(ask=[]),
            lambda p: p['scenarios'][0].pop('ask'),
            lambda p: p['scenarios'][0].update(default='deny'),
            lambda p: p['scenarios'][0].update(default='ask'),
            lambda p: p['scenarios'][0].update(prefix='docker **'),
            lambda p: p['scenarios'].append(deepcopy(p['scenarios'][0])),
            lambda p: p['scenarios'][0].update(ask=['{run,} **']),
            lambda p: p['scenarios'][0].update(ask=['{run,{exec,rm}} **']),
            lambda p: p['scenarios'][0].update(ask=['{run,**} **']),
            lambda p: p['scenarios'][0].update(ask='run **'),
            lambda p: p.update(default='allow'),
            lambda p: p.update(scenarios=[]),
        ]
        for mutate in mutations:
            self.policy = deepcopy(base)
            mutate(self.policy)
            self.assertEqual('invalid-policy', self.decision('id')['reason'])

    def test_target_identity_and_draft_require_real_adoption(self):
        for kwargs in [{'server_id': 'other'}, {'user': 'root'}]:
            self.assertEqual('target-not-covered', self.decision(DOCKER+'ps', **kwargs)['reason'])
        self.policy['approval_ref'] = None
        for command in [DOCKER+'ps', 'id']:
            self.assertEqual('unapproved-policy', self.decision(command)['reason'])
        self.assertEqual('ask', self.decision(DOCKER+'service update --force portal')['decision'])
        self.assertEqual('deny', self.decision('rm -rf /')['decision'])

    def test_alternatives_match_one_argument_and_keep_go_formats_literal(self):
        general = self.policy['scenarios'][1]
        general['allow'] = ['probe {svc-a,svc-b} --format *', "probe --format '{{.ID}},{{.Name}}'"]
        for command in ['probe svc-a --format json', 'probe svc-b --format json',
                        "probe --format '{{.ID}},{{.Name}}'"]:
            self.assertEqual('allow', self.decision(command)['decision'])
        for command in ['probe svc-a svc-b --format json', 'probe svc-c --format json',
                        'probe svc-a --format json extra']:
            self.assertEqual('ask', self.decision(command)['decision'])

    def test_syntax_and_wrappers_are_checked_before_default_allow(self):
        self.policy['scenarios'] = [{'name': 'test', 'prefix': '', 'default': 'allow', 'ask': []}]
        for command in ['id; reboot', 'id && reboot', 'id | sh', 'id > /tmp/out', 'id 2>&1',
                        'id\nhostname', 'echo $(id)', 'echo `id`', 'echo $HOME',
                        'cat <(id)', 'id &', '(id)', 'id\0', "echo 'unterminated",
                        'ssh host id', 'sudo id', '/bin/bash -c id', 'python3.12 -c pass',
                        'env id', 'PATH=/tmp id', 'timeout 5 id', './task.sh', 'find /tmp -delete',
                        'probe file?.conf', 'probe [ab]', 'probe ~/config', 'probe {a,b}']:
            with self.subTest(command=command):
                self.assertEqual('ask', self.decision(command)['decision'])

    def test_legacy_precedence_wrappers_and_globs_remain_compatible(self):
        self.legacy(allow=['**'])
        self.assertEqual('deny', self.decision('rm -rf /')['decision'])
        self.assertEqual('ask', self.decision('systemctl restart nginx.service')['decision'])
        self.assertEqual('allow', self.decision('id')['decision'])
        self.assertEqual('wrapped-command', self.decision('ssh host id')['reason'])
        self.assertEqual('shell-expansion', self.decision('probe file?.conf')['reason'])
        self.policy['deny'].append('bash **')
        self.assertEqual('deny', self.decision('bash -c id')['decision'])
        self.policy['approval_ref'] = None
        self.assertEqual('unapproved-policy', self.decision('id')['reason'])

    def test_legacy_braces_and_single_argument_globs_do_not_change(self):
        self.legacy(allow=['probe svc-?.[ab] --format *', 'probe {a,b}'])
        for command in ["probe svc-1.a --format 'value with spaces'", 'probe svc-1.a --format \\*',
                        "probe '{a,b}'"]:
            self.assertEqual('allow', self.decision(command)['decision'])
        for command in ['probe svc-11.a --format value', 'probe svc-1.a --format value extra', 'probe a']:
            self.assertEqual('ask', self.decision(command)['decision'])
        self.policy['allow'] = ['probe ** --ready']
        for command in ['probe --ready', 'probe a b --ready']:
            self.assertEqual('allow', self.decision(command)['decision'])
        self.assertEqual('ask', self.decision('probe a --ready extra')['decision'])

    def test_executable_paths_cannot_bypass_restrictions_in_either_format(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                if legacy:
                    self.legacy(deny=['dd **', 'rm -rf /'], ask=['systemctl restart **'], allow=['**'])
                else:
                    self.policy['deny'].append('dd **')
                    self.policy['scenarios'] = [{'name': 'all', 'prefix': '', 'default': 'allow',
                                                 'ask': ['systemctl restart **']}]
                for program in ['dd', '/bin/dd', '/usr/bin/dd', './dd', '/tmp/dd']:
                    self.assertEqual('deny', self.decision(program+' if=/dev/zero of=/dev/null')['decision'])
                for program in ['rm', '/bin/rm', '/usr/bin/rm', './rm']:
                    self.assertEqual('deny', self.decision(program+' -rf /')['decision'])
                for program in ['systemctl', '/bin/systemctl', './systemctl']:
                    self.assertEqual('ask', self.decision(program+' restart nginx.service')['decision'])

    def test_path_rules_do_not_trust_basename_or_rewrite_operands(self):
        self.legacy(deny=['/bin/dd **', 'probe /bin/dd'], ask=[], allow=['id', '/usr/bin/id'])
        self.assertEqual('deny', self.decision('/bin/dd operand')['decision'])
        self.assertEqual('ask', self.decision('/other/dd operand')['decision'])
        self.assertEqual('deny', self.decision('probe /bin/dd')['decision'])
        self.assertEqual('ask', self.decision('probe dd')['decision'])
        for command, expected in [('id', 'allow'), ('/usr/bin/id', 'allow'), ('/tmp/id', 'ask')]:
            self.assertEqual(expected, self.decision(command)['decision'])

    def test_docker_normalized_denies_also_cover_pathless_program_rules(self):
        self.policy['deny'] = ['docker -Hunix:///var/run/docker.sock service inspect **']
        for command in ['docker', '/usr/bin/docker', './docker']:
            result = self.decision(command+' --debug --host=unix:///var/run/docker.sock service inspect portal')
            self.assertEqual('deny', result['decision'])

    def test_command_wrappers_cannot_be_allowed_by_broad_policies(self):
        base = deepcopy(self.policy)
        for legacy in (False, True):
            self.policy = deepcopy(base)
            if legacy:
                self.legacy(allow=['**'])
            else:
                self.policy['scenarios'] = [{'name': 'all', 'prefix': '', 'default': 'allow', 'ask': []}]
            for command in ['builtin eval id', 'builtin exec /bin/rm -rf /',
                            DOCKER+'exec example sh -c id', DOCKER+'container exec example sh -c id',
                            'docker --debug -Hunix:///var/run/docker.sock container --log-level=error exec example id',
                            '/usr/bin/docker --host=unix:///var/run/docker.sock exec example /bin/rm -rf /',
                            DOCKER+'run example sh -c id', DOCKER+'container run example id']:
                with self.subTest(legacy=legacy, command=command):
                    result = self.decision(command)
                    self.assertEqual(('ask', 'wrapped-command'), (result['decision'], result['reason']))
            for command in [DOCKER+'inspect exec', DOCKER+'container inspect run', 'probe builtin eval']:
                self.assertEqual('allow', self.decision(command)['decision'])
            self.policy['deny'] = [DOCKER+'exec **', 'builtin **']
            self.assertEqual('deny', self.decision(DOCKER+'exec example sh -c id')['decision'])
            self.assertEqual('deny', self.decision('builtin eval id')['decision'])

    def test_path_globs_do_not_claim_filesystem_confinement(self):
        self.legacy(allow=['probe /opt/app/*'])
        for command in ['probe /opt/app/nested/file', 'probe /opt/app/../secret']:
            self.assertEqual('allow', self.decision(command)['decision'])

    def test_invalid_common_and_legacy_fields_fail_closed(self):
        base = deepcopy(self.policy)
        for field, value in [('version', True), ('version', 0), ('targets', ['test-01']),
                             ('deny', [None]), ('approval_ref', ''), ('scenarios', None)]:
            self.policy = deepcopy(base)
            self.policy[field] = value
            self.assertEqual('invalid-policy', self.decision('id')['reason'])
        self.legacy()
        base = deepcopy(self.policy)
        for field, value in [('default', 'allow'), ('allow', 'id'), ('ask', ['id; reboot'])]:
            self.policy = dict(base, **{field: value})
            self.assertEqual('invalid-policy', self.decision('id')['reason'])
        self.policy = dict(base, alow=['**'])
        self.assertEqual('invalid-policy', self.decision('id')['reason'])

    def test_cli_decisions_never_execute_even_when_default_allows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            marker = Path(directory) / 'must-not-exist'
            path.write_text(json.dumps(self.policy))
            for command, expected in [('id', 0), ('unknown', 2), ('rm -rf /', 3),
                                      (DOCKER+f'touch {marker}', 0), (f'touch {marker}', 2)]:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_command.py'),
                                         '--policy', str(path), '--server-id', 'test-01',
                                         '--user', 'ops', '--command', command], capture_output=True, text=True)
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertIn('decision', json.loads(result.stdout))
            self.assertFalse(marker.exists())
            path.write_text('not JSON')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_command.py'),
                                     '--policy', str(path), '--server-id', 'test-01',
                                     '--user', 'ops', '--command', 'id'], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertEqual('invalid-policy', json.loads(result.stdout)['reason'])


if __name__ == '__main__':
    unittest.main()
