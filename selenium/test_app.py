"""
Selenium end-to-end test for Notes Manager.

Covers: login protection, register, create, search, category filter, pin,
edit, delete, Redis visit counter, logout, and the wrong-password message.

Usage:
    pip install selenium
    python test_app.py http://<ALB-DNS-name>
    python test_app.py http://localhost --headless

Selenium 4.6+ downloads the matching ChromeDriver automatically (Selenium Manager).
"""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

args = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = args[0].rstrip("/") if args else "http://localhost"
HEADLESS = "--headless" in sys.argv

STAMP = int(time.time())
USERNAME = f"tester_{STAMP}"
PASSWORD = "Secret123"
NOTE_A = f"Deploy checklist {STAMP}"     # Work / High
NOTE_B = f"Exam revision {STAMP}"        # Study / Low


def note_row(title):
    """Locator for the note card whose title is exactly `title`."""
    return (By.XPATH, f"//li[contains(@class,'note-item')][.//span[@class='note-title' and text()='{title}']]")


def main():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1000")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)
    passed = 0

    def ok(msg):
        nonlocal passed
        passed += 1
        print(f"[PASS] Test {passed:2d}: {msg}")

    def flash_text():
        return driver.find_element(By.ID, "flashes").text

    def add_note(title, content, category, priority):
        driver.find_element(By.ID, "note-title-input").send_keys(title)
        driver.find_element(By.ID, "note-content-input").send_keys(content)
        Select(driver.find_element(By.ID, "note-category")).select_by_visible_text(category)
        Select(driver.find_element(By.ID, "note-priority")).select_by_visible_text(priority)
        driver.find_element(By.ID, "add-btn").click()
        wait.until(EC.presence_of_element_located(note_row(title)))

    try:
        # 1. Notes page is protected: visitors are sent to the login page
        driver.get(URL + "/")
        wait.until(EC.url_contains("/login"))
        assert "Notes Manager" in driver.title
        ok(f"protected page redirected to login, title = {driver.title}")

        # 2. Register a new account (auto-logs in)
        driver.find_element(By.ID, "register-link").click()
        driver.find_element(By.ID, "username").send_keys(USERNAME)
        driver.find_element(By.ID, "password").send_keys(PASSWORD)
        driver.find_element(By.ID, "confirm").send_keys(PASSWORD)
        driver.find_element(By.ID, "register-btn").click()
        nav = wait.until(EC.visibility_of_element_located((By.ID, "nav-user")))
        assert USERNAME in nav.text
        ok(f"registered and logged in -> '{nav.text}'")

        # 3. Verify a web element: the page heading
        heading = driver.find_element(By.ID, "app-title")
        assert heading.text == "My Notes"
        ok(f"heading element found -> {heading.text}")

        # 4. Create two notes in different categories
        add_note(NOTE_A, "Check ALB targets are healthy", "Work", "High")
        add_note(NOTE_B, "Docker volumes and Compose", "Study", "Low")
        assert driver.find_element(By.ID, "stat-total").text == "2"
        ok("created 2 notes, total stat = 2")

        # 5. Search finds only the matching note
        box = driver.find_element(By.ID, "search-input")
        box.clear()
        box.send_keys("checklist")
        driver.find_element(By.ID, "filter-btn").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "result-count"), '1 note(s) found for "checklist"'))
        assert not driver.find_elements(*note_row(NOTE_B))
        ok("search 'checklist' shows only the Work note")

        # 6. Category filter
        driver.find_element(By.ID, "clear-filters").click()
        Select(driver.find_element(By.ID, "filter-category")).select_by_visible_text("Study")
        driver.find_element(By.ID, "filter-btn").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "result-count"), "in Study"))
        assert driver.find_elements(*note_row(NOTE_B)) and not driver.find_elements(*note_row(NOTE_A))
        ok("category filter 'Study' shows only the Study note")

        # 7. Pin a note -> it moves to the top with a Pinned badge
        driver.find_element(By.ID, "clear-filters").click()
        driver.find_element(*note_row(NOTE_B)).find_element(By.CLASS_NAME, "pin-btn").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "flashes"), "Note pinned."))
        first = driver.find_elements(By.CSS_SELECTOR, "#notes-list .note-item")[0]
        assert NOTE_B in first.text and "Pinned" in first.text
        assert driver.find_element(By.ID, "stat-pinned").text == "1"
        ok("pinned note moved to the top, pinned stat = 1")

        # 8. Edit a note (title + priority)
        driver.find_element(*note_row(NOTE_A)).find_element(By.CLASS_NAME, "edit-link").click()
        title_box = wait.until(EC.visibility_of_element_located((By.ID, "edit-title-input")))
        edited = NOTE_A + " (done)"
        title_box.clear()
        title_box.send_keys(edited)
        Select(driver.find_element(By.ID, "edit-priority")).select_by_visible_text("Medium")
        driver.find_element(By.ID, "save-btn").click()
        row = wait.until(EC.presence_of_element_located(note_row(edited)))
        assert "Medium" in row.text and "edited" in row.text
        ok(f"note edited -> '{edited}', priority Medium")

        # 9. Delete a note (accept the confirm() popup)
        driver.find_element(*note_row(edited)).find_element(By.CLASS_NAME, "delete-btn").click()
        wait.until(EC.alert_is_present()).accept()
        wait.until(EC.text_to_be_present_in_element((By.ID, "flashes"), "Note deleted."))
        assert not driver.find_elements(*note_row(edited))
        assert driver.find_element(By.ID, "stat-total").text == "1"
        ok("note deleted, total stat = 1")

        # 10. Redis visit counter increases on reload
        before = driver.find_element(By.ID, "visit-count").text
        driver.refresh()
        after = wait.until(EC.presence_of_element_located((By.ID, "visit-count"))).text
        assert before != after
        ok(f"visit counter changed: '{before}' -> '{after}'")

        # 11. JSON API returns this user's notes
        driver.get(URL + "/api/notes")
        body = driver.find_element(By.TAG_NAME, "body").text
        assert f'"user":"{USERNAME}"' in body.replace(" ", "") and '"count":1' in body.replace(" ", "")
        ok("JSON API /api/notes returns 1 note for this user")
        driver.get(URL + "/")

        # 12. Logout, then the notes page is protected again
        driver.find_element(By.ID, "logout-btn").click()
        wait.until(EC.url_contains("/login"))
        assert "logged out" in flash_text()
        driver.get(URL + "/")
        wait.until(EC.url_contains("/login"))
        ok("logged out; notes page redirects to login again")

        # 13. Wrong password shows an error (and counts the attempt)
        driver.find_element(By.ID, "username").send_keys(USERNAME)
        driver.find_element(By.ID, "password").send_keys("wrong-password")
        driver.find_element(By.ID, "login-btn").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "flashes"), "Invalid username or password"))
        ok(f"wrong password rejected -> '{flash_text()}'")

        # 14. Correct password logs back in, pinned note still there (data persisted)
        driver.find_element(By.ID, "password").send_keys(PASSWORD)
        driver.find_element(By.ID, "login-btn").click()
        wait.until(EC.visibility_of_element_located((By.ID, "nav-user")))
        assert driver.find_elements(*note_row(NOTE_B))
        ok("logged back in, saved note still there")

        print("Info:", driver.find_element(By.ID, "served-by").text)
        driver.save_screenshot("selenium_result.png")
        print(f"\nAll {passed} tests passed. Screenshot saved: selenium_result.png")
    except Exception as exc:  # noqa: BLE001
        driver.save_screenshot("selenium_failure.png")
        print(f"[FAIL] after {passed} passed tests: {exc!r}")
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
