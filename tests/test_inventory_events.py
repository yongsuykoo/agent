import tempfile
import unittest
from unittest.mock import Mock,patch
from app_agent.inventory_events import InventoryEvents
from app_agent.maintenance import Maintenance
from test_maintenance import Session


class InventoryEventTests(unittest.TestCase):
    def test_registry_signal_remains_pending_until_scan_and_rearms_native_watch(self):
        events=InventoryEvents();events.kernel=Mock();events.advapi=Mock()
        key=Mock();key.__int__=Mock(return_value=4)
        events.watches=[(key,9)]
        events.kernel.WaitForSingleObject.side_effect=[0,258,258]
        events.advapi.RegNotifyChangeKeyValue.return_value=0
        self.assertTrue(events.poll());self.assertTrue(events.poll())
        events.advapi.RegNotifyChangeKeyValue.assert_called_once_with(4,True,0x10000005,9,True)
        events.scanned();self.assertFalse(events.poll());events.close()
        events.kernel.CloseHandle.assert_called_once_with(9);key.Close.assert_called_once()

    def test_install_signal_waits_for_current_job_then_triggers_inventory_before_periodic_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            signals=Mock();signals.poll.return_value=False
            with patch('app_agent.inventory_events.InventoryEvents',return_value=signals), \
                 patch('app_agent.maintenance.time.monotonic',return_value=100):
                session=Session();maintenance=Maintenance(directory,emit=lambda text:None)
                maintenance.tick(session,'0.7.2',0)
                signals.poll.return_value=True
                maintenance.tick(session,'0.7.2',0)
                self.assertEqual(len(session.requests),1)
                session.finish();maintenance.tick(session,'0.7.2',0)
                self.assertEqual([r['operation'] for r in session.requests],['inventory','inventory'])
                maintenance.close();signals.close.assert_called_once()
