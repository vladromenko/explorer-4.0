import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from explorer4.control import Control
from explorer4.session import Session
from explorer4 import resources,handoff

class StageB(unittest.TestCase):
    def test_requested_success_survives_stop_at_command_boundary(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(resources,'DATA',Path(directory)),patch('explorer4.control.catalog.event'),patch('explorer4.session.catalog.event'):
            control=Control()
            control.stop_event.clear()
            control.expires=float('inf')
            session=Session(control)
            def sample(*args,**kwargs):
                session.finish('success')
                raise InterruptedError('Stopped before command')
            source=SimpleNamespace(start=lambda **kw:{},begin_episode=lambda:None,sample=sample,close=lambda:[])
            with patch('explorer4.session.HardwareSource',return_value=source):
                session._run('so101_pick_place','test','test')
            self.assertEqual(session.outcome,'success')
            self.assertIsNone(session.error)
