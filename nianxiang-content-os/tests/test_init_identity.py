import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from init_local_config import InitError, verify_user_identity


class InitIdentity(unittest.TestCase):
    def test_cloud_cli_verified_self_contact(self):
        def run(command, **kwargs):
            if command[1:3] == ['auth', 'status']:
                return SimpleNamespace(returncode=1, stdout='', stderr='unknown command "auth" for "lark-cli"')
            self.assertEqual(command[1:3], ['contact', '+get-user'])
            return SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'identity': 'user', 'data': {'user': {'open_id': 'cloud-user'}}}), stderr='')
        with patch('init_local_config.subprocess.run', side_effect=run):
            verify_user_identity()

    def test_cloud_cli_rejects_failed_or_bot_identity(self):
        for payload in ({'ok': False, 'identity': 'user', 'data': {'user': {'open_id': 'cloud-user'}}},
                        {'ok': True, 'identity': 'bot', 'data': {'user': {'open_id': 'cloud-user'}}},
                        {'ok': True, 'identity': 'user', 'data': {'user': {}}}):
            def run(command, **kwargs):
                if command[1:3] == ['auth', 'status']:
                    return SimpleNamespace(returncode=1, stdout='', stderr='unknown command "auth" for "lark-cli"')
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
            with self.subTest(payload=payload), patch('init_local_config.subprocess.run', side_effect=run):
                with self.assertRaises(InitError):
                    verify_user_identity()

    def test_legacy_denial_does_not_fallback(self):
        with patch('init_local_config.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='permission denied')) as run:
            with self.assertRaises(InitError):
                verify_user_identity()
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
