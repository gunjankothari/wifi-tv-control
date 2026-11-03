"""Reads what is playing on a TV over network debugging (ADB). Read-only: it only runs `dumpsys` queries.

Usage: .venv/bin/python adb_probe.py oneplus 192.168.29.77
The first time, the TV shows an "Allow debugging from this computer?" prompt; tick Always allow and press OK.
"""
import asyncio, os, sys
from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adbkey")


def signer():
    if not os.path.exists(KEY):
        keygen(KEY)
        os.chmod(KEY, 0o600)
    return PythonRSASigner(open(KEY + ".pub").read(), open(KEY).read())


async def main(name, ip):
    dev = AdbDeviceTcpAsync(ip, 5555, default_transport_timeout_s=10.0)
    print(f"connecting to {name} ({ip}); if the TV asks, choose Always allow and OK ...", flush=True)
    await dev.connect(rsa_keys=[signer()], auth_timeout_s=60)
    for title, cmd in (
        ("foreground window", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -4"),
        ("resumed activity", "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | head -3"),
        ("media sessions", "dumpsys media_session | grep -E 'package=|state=PlaybackState|metadata:|description=|active=' | head -30"),
    ):
        print(f"\n== {title}\n{(await dev.shell(cmd)).strip()}")
    await dev.close()


asyncio.run(main(*sys.argv[1:3]))
