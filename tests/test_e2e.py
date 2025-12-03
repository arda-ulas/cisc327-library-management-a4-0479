"""
End-to-end tests for the Library Management System.

These tests use Playwright (via pytest-playwright) to interact with the running
Flask application through a real browser.

How to run:
    1. Start the Flask app:
         (venv) $ flask run --host=0.0.0.0 --port=5000
       or:
         (venv) $ python app.py

    2. Execute the E2E tests:
         (venv) $ pytest tests/test_e2e.py

The tests default to http://localhost:5000, but this can be overridden using
the environment variable E2E_BASE_URL.
"""

import os
import time
from typing import Tuple
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:5000")


def _make_unique_isbn() -> str:
    """
    Generate a pseudo-unique 13-digit ISBN using the current timestamp.
    """
    millis = int(time.time() * 1000)
    digits = str(millis)
    return digits[:13] if len(digits) >= 13 else digits.ljust(13, "0")


def _add_book_via_ui(page: Page) -> Tuple[str, str]:
    """
    Add a new book through the UI and verify the success flash message.
    Returns (title, isbn) for further actions.
    """
    page.goto(f"{BASE_URL}/")
    expect(page).to_have_url(f"{BASE_URL}/catalog")

    page.get_by_role("link", name="➕ Add Book").click()
    expect(page.locator("h2")).to_have_text("➕ Add New Book")

    title = f"Test Book {int(time.time())}"
    author = "Test Author"
    isbn = _make_unique_isbn()
    total_copies = "2"

    page.fill("#title", title)
    page.fill("#author", author)
    page.fill("#isbn", isbn)
    page.fill("#total_copies", total_copies)

    page.get_by_role("button", name="Add Book to Catalog").click()
    expect(page).to_have_url(f"{BASE_URL}/catalog")

    flash = page.locator(".flash-success")
    expect(flash).to_contain_text("has been successfully added to the catalog")

    row = page.locator("table tbody tr", has_text=isbn)
    expect(row).to_contain_text(title)
    expect(row).to_contain_text(isbn)

    return title, isbn


def test_add_book_appears_in_catalog(page: Page) -> None:
    """
    Flow 1:
    Add a new book and verify it appears in the catalog with a success message.
    """
    _add_book_via_ui(page)


def test_borrow_book_reduces_availability_and_shows_message(page: Page) -> None:
    """
    Flow 2:
    Borrow a newly added book and verify:
      - success flash message appears
      - available copy count decreases by 1
    """
    title, isbn = _add_book_via_ui(page)

    row = page.locator("table tbody tr", has_text=isbn)
    availability_cell = row.locator("td").nth(4)
    initial_text = availability_cell.inner_text().strip()

    # Parse "X/Y Available"
    try:
        available_str, total_str = initial_text.split()[0].split("/")
        initial_available = int(available_str)
        total_copies = int(total_str)
    except Exception:
        initial_available = None
        total_copies = None

    patron_input = row.get_by_placeholder("Patron ID (6 digits)")
    patron_input.fill("123456")
    row.get_by_role("button", name="Borrow").click()

    flash = page.locator(".flash-success")
    expect(flash).to_contain_text("Successfully borrowed")
    expect(flash).to_contain_text(title)

    row = page.locator("table tbody tr", has_text=isbn)
    new_text = row.locator("td").nth(4).inner_text().strip()

    assert new_text != initial_text

    if initial_available is not None and total_copies is not None:
        new_available_str, new_total_str = new_text.split()[0].split("/")
        new_available = int(new_available_str)
        new_total = int(new_total_str)

        assert new_total == total_copies
        assert new_available == initial_available - 1
