"""Quick UI smoke test: the chat, markdown, code buttons, attachments and settings
still work after a change. Needs the app on 9422 with a mock AI on 9411."""
import sys

from playwright.sync_api import sync_playwright

APP = "http://127.0.0.1:9422"
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
    page.wait_for_timeout(1200)

    print("1. Welcome + meter")
    check(page.locator(".welcome h1").is_visible(), "welcome screen")
    check(page.locator("#usagePill").is_visible(), "usage meter pill")
    check(page.locator("#engineStrip").is_visible(), "engine strip")

    print("2. A coding answer renders markdown + code buttons")
    page.fill("#input", "write a python function add(a, b) with a code block")
    page.click("#sendBtn")
    page.wait_for_timeout(3000)
    card = page.locator(".msg.assistant").last
    html = card.inner_html()
    check("<pre" in html or "code" in html, "code block rendered")
    check(card.locator('[data-act="copy"]').count() == 1, "copy button")
    check("mock-openai" in card.inner_text(), "the mock AI answered")

    print("3. Maths renders")
    page.fill("#input", "show the formula $E = mc^2$ and $$\\int_0^1 x dx$$")
    page.click("#sendBtn")
    page.wait_for_timeout(2500)
    check(page.locator(".msg.assistant").last.locator(".katex").count() >= 1, "KaTeX rendered")

    print("4. Attachment chip")
    page.evaluate("""
      var dt = new DataTransfer();
      dt.items.add(new File(['print("hi")\\n'], 'snippet.py', {type: 'text/plain'}));
      document.getElementById('attachInput').files = dt.files;
      document.getElementById('attachInput').dispatchEvent(new Event('change', {bubbles: true}));
    """)
    page.wait_for_timeout(800)
    check(page.locator("#attachRow .att").count() == 1, "file chip shown")
    page.fill("#input", "look at my file")
    page.click("#sendBtn")
    page.wait_for_timeout(2500)
    check("snippet.py" in page.locator(".msg.user").last.inner_text(), "attachment in the bubble")

    print("5. Settings round-trip")
    page.click("#settingsBtn")
    page.wait_for_timeout(700)
    check(page.locator("#cfgProvider").is_visible(), "provider select")
    check(page.locator("#billPrice").is_visible(), "billing section present")
    check(page.locator("#connList .conn").count() >= 8, "connectors present")
    page.fill("#cfgName", "Smoke AI")
    page.click("#saveSettings")
    page.wait_for_timeout(1500)
    check(page.locator("#topTitle").inner_text() == "Smoke AI", "name saved")
    page.click("#settingsBtn")
    page.wait_for_timeout(500)
    page.fill("#cfgName", "Smash AI")
    page.click("#saveSettings")
    page.wait_for_timeout(1200)

    print("5b. I FIX AI module")
    check(page.locator('.ebtn[data-e="ifixai"]').count() == 1, "I FIX AI button in the strip")
    page.click('.ebtn[data-e="ifixai"]')
    page.wait_for_timeout(400)
    page.fill("#input", "my openai chatbot returns empty answers, fix it")
    page.click("#sendBtn")
    page.wait_for_timeout(3500)
    badge = page.locator(".engine-badge").last
    check(badge.count() >= 1 and "I FIX AI" in badge.inner_text(), "I FIX AI badge on the answer")
    page.click('.ebtn[data-e="auto"]')
    page.wait_for_timeout(300)

    print("6. Retry + new chat")
    page.locator('[data-act="retry"]').last.click()
    page.wait_for_timeout(2500)
    check(page.locator(".msg.assistant").count() >= 3, "retry added an answer")
    page.click("#newChatTop")
    page.wait_for_timeout(600)
    check(page.locator(".welcome").is_visible(), "new chat clears the thread")

    print("7. Phone layout")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(700)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check(overflow <= 1, f"no sideways scrolling ({overflow}px)")
    browser.close()

print("JS errors:", js_errors)
check(not js_errors, "no JavaScript errors")
print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
