"""Browser test of the paywall, meter and owner dashboard.

Needs: tests/mock_services.py running, and the app started with
    CONFIG_FILE=tests/billing-config.json PORT=9421 HOST=127.0.0.1
    USAGE_DB=<fresh file> ADMIN_PASSWORD=admin-pw AI_API_KEY=test-key python3 app.py

Two browsers play two roles: a visitor (no admin password) and the owner.
"""
import sys
import uuid

from playwright.sync_api import sync_playwright

APP = "http://127.0.0.1:9421"
fails = []
js_errors = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def owner_page(browser):
    """A tab signed in as the owner."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("console", lambda m: js_errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: js_errors.append(str(e)))
    pg.on("dialog", lambda d: d.accept("admin-pw"))
    pg.goto(APP, wait_until="networkidle")
    pg.evaluate("sessionStorage.setItem('myai.admin', 'admin-pw')")
    pg.wait_for_timeout(500)
    return ctx, pg


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: js_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: js_errors.append(str(e)))
    page.goto(APP, wait_until="networkidle")
    page.wait_for_timeout(1200)

    print("1. The free meter (visitor)")
    pill = page.locator("#usagePill")
    check(pill.is_visible(), "meter pill visible")
    txt = pill.inner_text()
    print("   pill:", txt)
    check("2 questions left" in txt, "fresh visitor sees the allowance")

    print("2. Spend the allowance")
    for i in range(2):
        page.fill("#input", f"free question {i + 1}")
        page.click("#sendBtn")
        page.wait_for_timeout(2200)
    txt = pill.inner_text()
    print("   pill:", txt)
    check("0 questions left" in txt, "meter counts down")

    print("3. The paywall appears")
    page.fill("#input", "one question too many")
    page.click("#sendBtn")
    page.wait_for_timeout(2500)
    card = page.locator(".msg.assistant").last
    pw_card = card.locator(".paywall")
    check(pw_card.count() == 1, "paywall card shown")
    body = pw_card.inner_text() if pw_card.count() else ""
    print("   paywall:", body[:160].replace("\n", " | "))
    check("free allowance is used up" in body.lower(), "headline")
    check("Test Plus" in body and "R49" in body, "plan and price shown")
    check("Pay by bank transfer (EFT)" in body, "EFT button (manual provider on)")
    check("Pay by card" in body, "card button (stripe on)")
    check("Redeem" in body, "coupon box")

    print("4. EFT flow shows bank details and a reference")
    pw_card.locator('[data-pw="manual"]').click()
    page.wait_for_timeout(1500)
    bank = pw_card.locator('[data-pw="bankbox"]').inner_text()
    print("   bank:", bank[:140].replace("\n", " | "))
    check("FNB" in bank and "62812345678" in bank, "bank details shown")
    check("MA-" in bank, "payment reference shown")
    ref = bank.split("MA-")[1].split()[0]
    check(len(ref) >= 8, f"reference looks complete: MA-{ref}")

    print("5. Owner dashboard approves it")
    octx, opage = owner_page(browser)
    opage.click("#settingsBtn")
    opage.wait_for_timeout(800)
    check(opage.locator("#billEnabled").is_checked(), "paywall switch shown as on")
    check(opage.locator("#billPrice").input_value() == "49", "price loaded")
    check(opage.locator("#billStripeKey").input_value() == "", "stripe secret never sent to browser")
    opage.click("#billDashBtn")
    opage.wait_for_timeout(2000)
    dtxt = opage.locator("#billDash").inner_text()
    print("   dash:", dtxt[:200].replace("\n", " | "))
    check("visitors" in dtxt and "active subscriptions" in dtxt, "stats shown")
    check(ref in dtxt, "the pending EFT is listed")
    check("R49" in dtxt or "earned" in dtxt, "revenue line")
    opage.locator('[data-appr]').first.click()
    opage.wait_for_timeout(1500)
    check("Nothing waiting." in opage.locator("#billDash").inner_text(), "approved and cleared")

    print("6. The visitor checks again and gets in")
    page.locator(".paywall").last.locator('[data-pw="refresh"]').click()
    page.wait_for_timeout(2500)
    txt = page.locator("#usagePill").inner_text()
    print("   pill:", txt)
    check("Test Plus" in txt, "meter shows the subscription")
    check(page.locator(".paywall").count() == 0, "the paywall card is gone")
    page.fill("#input", "first question as a subscriber")
    page.click("#sendBtn")
    page.wait_for_timeout(2200)
    last = page.locator(".msg.assistant").last
    check(last.locator(".paywall").count() == 0, "subscriber is not paywalled")
    check("answered" in last.inner_text(), "subscriber got a real answer")

    print("7. Coupons from the dashboard")
    opage.locator("#billDashBtn").click()
    opage.wait_for_timeout(1500)
    code = "WE" + uuid.uuid4().hex[:6].upper()   # unique per run so the DB can be reused
    opage.fill("#cpCode", code)
    opage.fill("#cpDays", "14")
    opage.click("#cpMake")
    opage.wait_for_timeout(1500)
    check(code in opage.locator("#billDash").inner_text(), "coupon listed")
    octx.close()
    # a brand-new visitor redeems it straight from the paywall
    ctx2 = browser.new_context(viewport={"width": 1280, "height": 900})
    p2 = ctx2.new_page()
    p2.on("console", lambda m: js_errors.append(m.text) if m.type == "error" else None)
    p2.on("pageerror", lambda e: js_errors.append(str(e)))
    p2.goto(APP, wait_until="networkidle")
    p2.wait_for_timeout(900)
    p2.evaluate("""async function(){
        for (var i=0;i<3;i++){
          await fetch('api/chat',{method:'POST',headers:{'Content-Type':'application/json',
            'X-Visitor': localStorage.getItem('myai.visitor').replace(/"/g,'')},
            body:JSON.stringify({messages:[{role:'user',content:'q'+i}]})});
        }
      }""")
    p2.wait_for_timeout(1500)
    p2.reload(wait_until="networkidle")
    p2.wait_for_timeout(900)
    p2.fill("#input", "after the wall")
    p2.click("#sendBtn")
    p2.wait_for_timeout(2200)
    wall = p2.locator(".paywall").last
    check(wall.count() == 1, "second visitor sees the paywall")
    wall.locator('[data-pw="coupon"]').fill(code.lower())  # case-insensitive redeem
    wall.locator('[data-pw="coupon-go"]').click()
    p2.wait_for_timeout(2500)
    t2 = p2.locator("#usagePill").inner_text()
    print("   pill2:", t2)
    check("Test Plus" in t2, "coupon unlocked the second visitor")
    ctx2.close()

    print("8. Settings save keeps billing (owner)")
    octx, opage = owner_page(browser)
    opage.click("#settingsBtn")
    opage.wait_for_timeout(800)
    opage.fill("#billPrice", "59")
    opage.click("#saveSettings")
    opage.wait_for_timeout(1500)
    opage.click("#settingsBtn")
    opage.wait_for_timeout(800)
    check(opage.locator("#billPrice").input_value() == "59", "price saved and reloaded")
    check(opage.locator("#billEnabled").is_checked(), "paywall still enabled after save")
    opage.fill("#billPrice", "49")
    opage.click("#saveSettings")
    opage.wait_for_timeout(1200)
    octx.close()

    print("9. Phone layout with the paywall (visitor)")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(700)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check(overflow <= 1, f"no sideways scrolling ({overflow}px)")
    browser.close()

print("JS errors:", js_errors)
check(not js_errors, "no JavaScript errors")
print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
