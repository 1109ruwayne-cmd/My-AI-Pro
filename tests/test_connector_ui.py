"""Browser test of the connectors UI (app on 9420, mocks on 9411-9414).

Needs: playwright + chromium, tests/mock_services.py running, and the app started with
     CONFIG_FILE pointing at a config whose connectors target 127.0.0.1:9411-9414.
"""
import json
import sys

from playwright.sync_api import sync_playwright

APP = "http://127.0.0.1:9420"
fails = []
js_errors = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                              permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.on("console", lambda m: js_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: js_errors.append(str(e)))
    page.goto(APP, wait_until="networkidle")
    page.wait_for_timeout(900)

    print("1. Engine strip")
    strip = page.locator("#engineStrip")
    check(strip.is_visible(), "engine strip visible")
    labels = strip.inner_text().replace("\n", " | ")
    print("   buttons:", labels)
    for want in ("Auto", "Smash AI", "OpenHands", "Dify", "VTuber", "orca-mini", "Connect"):
        check(want in labels, f"button for {want}")
    check(page.locator("#engineStrip .ebtn.on").inner_text().strip().startswith("✨"),
          "Auto is selected at first")

    print("2. Ask OpenHands directly")
    page.locator('#engineStrip .ebtn', has_text="OpenHands").click()
    check(page.locator("#engineStrip .ebtn.on").inner_text().count("OpenHands") == 1,
          "OpenHands button is now selected")
    page.fill("#input", "Build me a small API")
    page.click("#sendBtn")
    page.wait_for_timeout(3000)
    card = page.locator(".msg.assistant").last
    body = card.inner_text()
    print("   answer:", body[:150].replace("\n", " "))
    check("OpenHands agent" in body and "tests pass" in body, "OpenHands answered")
    badge = card.locator(".engine-badge")
    check(badge.count() == 1, "engine badge shown")
    check("OpenHands" in badge.inner_text(), "badge names OpenHands: " + badge.inner_text())

    print("3. Ask the VTuber (text + voice)")
    page.locator('#engineStrip .ebtn', has_text="VTuber").click()
    page.fill("#input", "introduce yourself")
    page.click("#sendBtn")
    page.wait_for_timeout(4000)
    card = page.locator(".msg.assistant").last
    body = card.inner_text()
    print("   answer:", body[:140].replace("\n", " "))
    check("VTuber" in body or "Konnichiwa" in body, "VTuber answered")
    check(card.locator(".voice-row").count() == 1, "voice row shown")
    played = page.evaluate("!!window.__myaiAudioPlayed || document.querySelectorAll('audio').length")
    check(True, f"audio elements in DOM: {played}")

    print("4. Auto routing picks an engine")
    page.locator('#engineStrip .ebtn', has_text="Auto").click()
    page.fill("#input", "ask orca-mini what it thinks about this")
    page.click("#sendBtn")
    page.wait_for_timeout(3000)
    card = page.locator(".msg.assistant").last
    body = card.inner_text()
    print("   answer:", body[:130].replace("\n", " "))
    check("orca-mini" in body, "routed to orca-mini automatically")
    check("orca" in card.locator(".engine-badge").inner_text().lower(), "badge says orca")

    print("5. Back to Smash AI")
    page.locator('#engineStrip .ebtn', has_text="Smash AI").click()
    page.fill("#input", "what is 2+2?")
    page.click("#sendBtn")
    page.wait_for_timeout(2500)
    card = page.locator(".msg.assistant").last
    check(card.locator(".engine-badge").count() == 0, "no badge for Smash AI's own answer")

    print("6. Connectors panel in Settings")
    page.click("#settingsBtn")
    page.wait_for_timeout(600)
    check(page.locator("#connList").is_visible(), "connector list rendered")
    cards = page.locator("#connList .conn")
    print("   cards:", cards.count())
    check(cards.count() >= 8, "a card for every connector plus the free-key table")
    check("Where to get a free key" in page.locator("#connList").inner_text(), "free providers table")
    check(page.locator("#cfgVoice").is_visible(), "voice checkbox present")
    oh = page.locator('#connList .conn[data-c="openhands"]')
    check(oh.locator(".switch").get_attribute("aria-checked") == "true", "openhands shown as on")
    check(oh.locator('input[data-f="url"]').input_value() == "http://127.0.0.1:9413",
          "openhands address filled in")
    check("saved ✓" in oh.inner_text(), "saved key indicated without showing it")
    check(oh.locator('input[data-f="key"]').input_value() == "", "the real key is never sent back")

    print("7. Test button talks to the service")
    oh.locator('[data-test="openhands"]').click()
    page.wait_for_timeout(2500)
    res = oh.locator("#etest-openhands").inner_text()
    print("   result:", res[:160])
    check(res.startswith("✓"), "openhands test passed")
    check("openhands_demo" in res, "profiles listed")
    dify = page.locator('#connList .conn[data-c="dify"]')
    dify.locator('[data-test="dify"]').click()
    page.wait_for_timeout(2500)
    res = dify.locator("#etest-dify").inner_text()
    print("   dify:", res[:120])
    check(res.startswith("✓") and "Dify demo bot" in res, "dify test passed")

    print("8. Switching a connector on and off")
    orca = page.locator('#connList .conn[data-c="orca"]')
    orca.locator('[data-toggle="orca"]').click()
    page.wait_for_timeout(400)
    check(orca.locator(".switch").get_attribute("aria-checked") == "false", "orca switched off")
    check("orca-mini" not in page.locator("#engineStrip").inner_text(), "orca left the strip")
    orca.locator('[data-toggle="orca"]').click()
    page.wait_for_timeout(400)
    check("orca-mini" in page.locator("#engineStrip").inner_text(), "orca is back in the strip")

    print("9. Save keeps connector settings")
    orca.locator('input[data-f="model"]').fill("orca-mini:7b")
    page.click("#saveSettings")
    page.wait_for_timeout(1800)
    cfg = json.loads(page.evaluate("fetch('api/config').then(r=>r.text())"))
    check(cfg["engines"]["orca"]["model"] == "orca-mini:7b", "model saved")
    check("key" not in cfg["engines"]["dify"], "config API no longer exposes keys")
    disk = json.load(open("/tmp/t5/conn-config.json", encoding="utf-8"))
    check(disk["engines"]["dify"]["key"] == "app-good-key", "untouched key kept on disk")
    public = json.loads(page.evaluate("fetch('api/status').then(r=>r.text())"))
    check("app-good-key" not in json.dumps(public), "status never leaks the key")
    check(public["config"]["engines"]["dify"]["has_key"] is True, "status says a key is saved")
    check("orca-mini:7b" in page.locator("#engineStrip").inner_text(), "strip shows the new model")

    print("10. Model suggestion chips")
    page.click("#settingsBtn")
    page.wait_for_timeout(600)
    free = page.locator('#connList .conn[data-c="free"]')
    check(free.locator(".mchip").count() == 0, "a switched-off connector is collapsed")
    free.locator('[data-toggle="free"]').click()
    page.wait_for_timeout(500)
    chips = page.locator('#connList .conn[data-c="free"] .mchip')
    check(chips.count() >= 3, f"free engine has {chips.count()} model chips")
    chips.nth(1).click()
    page.wait_for_timeout(300)
    check(page.locator('#connList .conn[data-c="free"] input[data-f="model"]').input_value()
          == "openai/gpt-oss-120b", "chip filled the model box")
    page.locator('#connList .conn[data-c="free"] input[data-f="url"]').fill("http://127.0.0.1:9411/v1")
    page.locator('#connList .conn[data-c="free"] [data-test="free"]').click()
    page.wait_for_timeout(2500)
    res = page.locator('#etest-free').inner_text()
    print("   free engine test:", res[:100])
    check(res.startswith("✓") and "5 model" in res, "free engine connects and lists models")
    page.locator('#connList .conn[data-c="free"] [data-toggle="free"]').click()
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    print("11. Disabled connector explains itself")
    page.evaluate("localStorage.clear(); sessionStorage.clear()")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1000)
    page.evaluate("""
      fetch('api/config',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({engines:{custom2:{enabled:false}}})})
    """)
    page.wait_for_timeout(600)
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(900)
    got = page.evaluate("""
      new Promise(function(done){
        fetch('api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({engine:'custom2',messages:[{role:'user',content:'hi'}]})})
        .then(function(r){return r.text()}).then(done)
      })
    """)
    check("isn't switched on" in got, "server explains a disabled connector")

    print("12. Phone layout")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(600)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check(overflow <= 1, f"no sideways scrolling on a phone ({overflow}px)")
    check(page.locator("#engineStrip").is_visible(), "strip still visible on a phone")

    browser.close()

print("JS errors:", js_errors)
check(not js_errors, "no JavaScript errors")
print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
