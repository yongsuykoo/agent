import unittest
from app_agent.discovery import merge_inventory


class DiscoveryTests(unittest.TestCase):
    def test_store_startmenu_and_registry_are_enriched_and_merged(self):
        registry = [{"name": "Calculator", "version": "old", "publisher": "Microsoft", "location": "C:/old", "help_url": "https://example.com"}]
        starts = [{"Name": "Calculator", "AppID": "Microsoft.WindowsCalculator_family!App"}]
        packages = [{"name": "Microsoft.WindowsCalculator", "family": "Microsoft.WindowsCalculator_family", "version": "11", "publisher": "Microsoft", "location": "C:/new"}]
        apps = merge_inventory(registry, starts, packages)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["version"], "11")
        self.assertEqual(apps[0]["location"], "C:/new")
        self.assertIn("Microsoft.WindowsCalculator", apps[0]["aliases"])

    def test_registry_duplicates_keep_stable_identity(self):
        first = merge_inventory([{"name": "Editor", "version": "1"}], [], [])
        second = merge_inventory([{"name": "Editor", "version": "2"}, {"name": "Editor", "version": "2"}], [], [])
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0]["id"], second[0]["id"])

    def test_nonlaunchable_packages_are_still_discovered(self):
        apps = merge_inventory([], [], [{"name": "Store App", "family": "family", "version": "1"}])
        self.assertEqual(apps[0]["app_id"], "")
        self.assertEqual(apps[0]["source"], "store")


    def test_start_shortcut_and_registry_icon_executables_are_linked_without_arguments(self):
        registry = [{'name': 'Editor', 'version': '1', 'executables': ['C:/Apps/Editor.exe']}]
        starts = [{'Name': 'Editor', 'AppID': 'Editor', 'executables': ['C:/Apps/Editor.exe']}]
        result = merge_inventory(registry, starts, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['executables'], ['C:/Apps/Editor.exe'])
