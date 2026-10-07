"""Read installed application metadata without launching applications."""
import sys


def installed_apps():
    if sys.platform != "win32":
        raise RuntimeError("Installed app discovery requires Windows.")
    import winreg

    apps = {}
    path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            with root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    with winreg.OpenKey(root, winreg.EnumKey(root, index)) as key:
                        def value(name):
                            try:
                                return str(winreg.QueryValueEx(key, name)[0])
                            except FileNotFoundError:
                                return ""
                        name = value("DisplayName")
                        if name:
                            app = {"name": name, "version": value("DisplayVersion"),
                                   "publisher": value("Publisher"),
                                   "location": value("InstallLocation"),
                                   "help_url": value("HelpLink")}
                            apps[(name.casefold(), app["version"])] = app
    return sorted(apps.values(), key=lambda app: app["name"].casefold())
