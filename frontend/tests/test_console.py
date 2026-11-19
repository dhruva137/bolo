"""Run with Python, Playwright and Chrome installed. One browser, one temporary shop."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def navigate(page, view):
    menu = page.locator("#menuToggle")
    if menu.is_visible():
        menu.click()
    page.locator(f'#nav a[data-view="{view}"]').click()
    expect(page.locator(f"#v-{view}")).to_be_visible()
    expect(page.locator("#pageState")).to_be_empty()


def run(base):
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel=os.environ.get("BOLO_TEST_BROWSER", "chrome"))
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme="light")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            page.get_by_role("button", name="Kirana demo").click()
            expect(page.locator("#kpis .kpi")).to_have_count(6)
            page.request.put(base + "/api/settings", data={"voice_replies": "0"})
            navigate(page, "phone")
            expect(page.locator("#chat .chat-empty")).to_be_visible()
            page.locator(".examples summary").click()
            prompts = page.locator("#hints button").all_text_contents()
            assert prompts and len(prompts) == len(set(prompts))
            page.locator("#hints button").first.press("Enter")
            expect(page.locator("#msgInput")).to_have_value(prompts[0])
            page.locator(".examples summary").click()
            page.route("**/api/simulate", lambda route: route.fulfill(
                status=503, content_type="application/json", body=json.dumps({"detail": "Please retry"})))
            page.locator("#sendBtn").click()
            expect(page.locator("#sendState")).to_have_text("Please retry")
            expect(page.locator("#msgInput")).to_have_value(prompts[0])
            page.unroute("**/api/simulate")
            page.locator("#msgInput").fill("urgent stock count")
            page.locator("#sendBtn").click()
            expect(page.locator("#msgInput")).to_be_empty()
            expect(page.locator("#chat .chat-empty")).to_have_count(0)
            for width in [1280, 390]:
                page.set_viewport_size({"width": width, "height": 800})
                for view in ["dashboard", "phone", "live", "ledger", "people", "settings"]:
                    navigate(page, view)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, view)
                    if width == 390:
                        assert page.locator(".side").bounding_box()["height"] < 100
                navigate(page, "live")
                thread = page.locator("#threadList button").first
                expect(thread).to_contain_text("Urgent wording")
                expect(thread).to_contain_text("urgent stock count")
                thread.click()
                expect(page.locator("#liveChat .msg.in").first).to_contain_text("urgent stock count")
            navigate(page, "phone")
            fixture = sorted((ROOT / "backend" / "eval" / "audio").glob("*.wav"))[0]
            page.locator("#fileInput").set_input_files(str(fixture))
            form = page.locator("#chat .voice-review")
            expect(form).to_be_visible(timeout=30000)
            form.locator("textarea").fill("Lakshmi 70 udhaar")
            form.get_by_role("button", name="Use transcript").click()
            expect(page.locator("#chat .reviewed")).to_contain_text("Lakshmi 70 udhaar", timeout=15000)
            expect(page.locator("#chat audio").first).to_be_visible()
            assert not errors, errors
            print("PASS: desktop/mobile, empty states, keyboard prompts, retry, message send, Live watch")
        finally:
            browser.close()


if __name__ == "__main__":
    # Keep fresh database files and credentials completely separate from a live shop.
    with tempfile.TemporaryDirectory() as data:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {**os.environ, "BOLO_DATA_DIR": data, "PYTHONUTF8": "1", "BOLO_OFFLINE": "1",
               "BOLO_STT_MODEL": str(Path(data) / "absent-model")}
        for key in ["SARVAM_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "WA_TOKEN", "WA_PHONE_NUMBER_ID",
                    "TWILIO_SID", "TWILIO_TOKEN", "BOLNA_API_KEY", "BOLNA_AGENT_ID"]:
            env[key] = ""
        # On Windows the venv python.exe is a launcher. Start the actual
        # interpreter so terminate()/wait() cover the SQLite-owning process.
        executable = getattr(sys, "_base_executable", sys.executable) if os.name == "nt" else sys.executable
        if os.name == "nt":
            import sysconfig
            env["PYTHONPATH"] = os.pathsep.join([sysconfig.get_paths()["purelib"], env.get("PYTHONPATH", "")])
        cmd = [executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
        server = subprocess.Popen(cmd, env=env, cwd=ROOT / "backend")
        try:
            for attempt in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Test server exited during startup")
                try:
                    with urlopen(base + "/api/status", timeout=1):
                        break
                except OSError:
                    time.sleep(0.2)
            run(base)
        finally:
            server.terminate()
            server.wait(timeout=10)
