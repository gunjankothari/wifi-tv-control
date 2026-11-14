"""Windows app: runs the helper in the background and shows its web page in a native window."""
import asyncio, os, sys, threading, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "helper"))
import webview

import tvd

URL = f"http://127.0.0.1:{tvd.PORT}/"


def helper_running():
    try:
        urllib.request.urlopen(URL + "status", timeout=1)
        return True
    except Exception:
        return False


def serve():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tvd.serve(tvd.build_app()))   # also opens the Wi-Fi port while phone access is on
    loop.run_forever()


def main():
    if not helper_running():                       # a second launch just opens another window on the same helper
        threading.Thread(target=serve, daemon=True).start()
        for _ in range(50):
            if helper_running():
                break
            time.sleep(0.2)
    webview.create_window("TV Remote", URL, width=480, height=820, min_size=(380, 560))
    webview.start()


if __name__ == "__main__":
    main()
