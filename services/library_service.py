"""
Library Service Module - Business Logic Functions
Contains all the core business logic for the Library Management System
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database import (
    get_db_connection,
    get_book_by_id, get_book_by_isbn, get_patron_borrow_count,
    insert_book, insert_borrow_record, update_book_availability,
    update_borrow_record_return_date, get_all_books,
    get_patron_borrowed_books, get_borrow_history_for_patron
)
from services.payment_service import PaymentGateway

def add_book_to_catalog(title: str, author: str, isbn: str, total_copies: int) -> Tuple[bool, str]:
    """
    Add a new book to the catalog.
    Implements R1: Book Catalog Management
    """
    # Normalize/trim
    title = (title or "").strip()
    author = (author or "").strip()
    isbn = (isbn or "").strip()

    # Title
    if not title:
        return False, "Title is required."
    if len(title) > 200:
        return False, "Title must be less than 200 characters."

    # Author
    if not author:
        return False, "Author is required."
    if len(author) > 100:
        return False, "Author must be less than 100 characters."

    # ISBN: exactly 13 digits (not just length)
    if len(isbn) != 13 or not isbn.isdigit():
        return False, "ISBN must be exactly 13 digits."

    # total_copies: positive integer
    if not isinstance(total_copies, int) or total_copies <= 0:
        return False, "Total copies must be a positive integer."

    # Duplicate ISBN
    existing = get_book_by_isbn(isbn)
    if existing:
        return False, "A book with this ISBN already exists."

    # Insert (available_copies starts equal to total_copies)
    success = insert_book(title, author, isbn, total_copies, total_copies)
    if success:
        return True, f'Book "{title}" has been successfully added to the catalog.'
    else:
        return False, "Database error occurred while adding the book."

def borrow_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Allow a patron to borrow a book.
    Implements R3 as per requirements

    Args:
        patron_id: 6-digit library card ID
        book_id: ID of the book to borrow

    Returns:
        tuple: (success: bool, message: str)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."

    # Check if book exists and is available
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    if book['available_copies'] <= 0:
        return False, "This book is currently not available."

    # Check patron's current borrowed books count
    current_borrowed = get_patron_borrow_count(patron_id)

    if current_borrowed >= 5:
        return False, "You have reached the maximum borrowing limit of 5 books."

    # Create borrow record
    borrow_date = datetime.now()
    due_date = borrow_date + timedelta(days=14)

    # Insert borrow record and update availability
    borrow_success = insert_borrow_record(patron_id, book_id, borrow_date, due_date)
    if not borrow_success:
        return False, "Database error occurred while creating borrow record."

    availability_success = update_book_availability(book_id, -1)
    if not availability_success:
        return False, "Database error occurred while updating book availability."

    return True, f'Successfully borrowed "{book["title"]}". Due date: {due_date.strftime("%Y-%m-%d")}.'

def return_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    R4 — Process book return by a patron.

    Rules:
    - Patron ID must be exactly 6 digits.
    - There must be an active borrow (return_date IS NULL) for (patron_id, book_id).
    - On success: set return_date = now, increment available_copies.
    """
    # Validate patron
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."

    # Validate book and existence
    try:
        book_id = int(book_id)
    except Exception:
        return False, "Invalid book id."
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    # Try to set return_date on an active borrow for this patron/book
    now = datetime.now()
    updated = update_borrow_record_return_date(patron_id, book_id, now)
    if not updated:
        # No active borrow row for this patron & book
        return False, "No active borrow for this patron and book."

    # Increment availability
    if not update_book_availability(book_id, +1):
        return False, "Database error occurred while updating availability."

    return True, f'Returned "{book["title"]}".'

def calculate_late_fee_for_book(patron_id: str, book_id: int) -> Dict:
    """
    R5 — Calculate late fees for a specific active loan of (patron_id, book_id).

    Rules from spec:
    - Loans are due in 14 days (already enforced on borrow).
    - If overdue:
        * Days 1–7 overdue: $0.50/day
        * Day 8+ overdue: $1.00/day
        * Total fee capped at $15.00
    Return:
        {
            'fee_amount': float,   # dollars
            'days_overdue': int,
            'status': 'on_time' | 'late' | 'no_active_loan'
        }
    """
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return {'fee_amount': 0.0, 'days_overdue': 0, 'status': 'no_active_loan'}

    try:
        book_id = int(book_id)
    except Exception:
        return {'fee_amount': 0.0, 'days_overdue': 0, 'status': 'no_active_loan'}

    # Find the active (unreturned) borrow for this patron/book
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT id, due_date
          FROM borrows
         WHERE patron_id = ? AND book_id = ? AND return_date IS NULL
         ORDER BY id DESC
         LIMIT 1
        """,
        (patron_id, book_id),
    ).fetchone()
    conn.close()

    if not row:
        return {'fee_amount': 0.0, 'days_overdue': 0, 'status': 'no_active_loan'}

    # Compute overdue days (based on local date difference)
    try:
        due_dt = datetime.fromisoformat(row["due_date"])
    except Exception:
        # If stored format is unexpected, no fee
        return {'fee_amount': 0.0, 'days_overdue': 0, 'status': 'no_active_loan'}

    today = datetime.now()
    days_overdue = max(0, (today.date() - due_dt.date()).days)

    if days_overdue == 0:
        return {'fee_amount': 0.0, 'days_overdue': 0, 'status': 'on_time'}

    # Tiered fee with cap
    tier1_days = min(days_overdue, 7)
    tier2_days = max(days_overdue - 7, 0)
    fee = tier1_days * 0.50 + tier2_days * 1.00
    fee_capped = min(15.00, fee)

    # Round to 2 decimals for presentation
    fee_capped = round(fee_capped + 1e-9, 2)

    return {'fee_amount': fee_capped, 'days_overdue': days_overdue, 'status': 'late'}

def search_books_in_catalog(search_term: str, search_type: str) -> List[Dict]:
    """
    R6 — Search for books.
    - title/author: partial, case-insensitive
    - isbn: exact match (13-digit)
    Returns list of book dicts in the same shape as get_all_books().
    """
    term = (search_term or "").strip()
    stype = (search_type or "").strip().lower()

    if not term or stype not in {"title", "author", "isbn"}:
        return []

    books = get_all_books()

    if stype == "isbn":
        # exact match
        return [b for b in books if b.get("isbn") == term]

    # partial, case-insensitive for title/author
    term_l = term.lower()
    if stype == "title":
        return [b for b in books if term_l in (b.get("title") or "").lower()]
    else:  # author
        return [b for b in books if term_l in (b.get("author") or "").lower()]

def get_patron_status_report(patron_id: str) -> Dict:
    """
    R7 — Patron Status Report.

    Returns a dict with:
      - patron_id
      - current_loans: list of {book_id, title, author, borrow_date, due_date, days_overdue, late_fee}
      - counts: {"currently_borrowed": int, "history_total": int}
      - total_late_fees: float (sum for active loans)
      - history: list of {book_id, title, author, borrow_date, due_date, return_date}

    Notes:
      * Reuses R5 fee calculation per active loan.
      * Patron ID must be exactly 6 digits.
    """
    pid = (patron_id or "").strip()
    if not pid.isdigit() or len(pid) != 6:
        return {
            "patron_id": patron_id,
            "current_loans": [],
            "counts": {"currently_borrowed": 0, "history_total": 0},
            "total_late_fees": 0.0,
            "history": [],
            "error": "Invalid patron ID. Must be exactly 6 digits.",
        }

    # Active borrows (no return_date)
    active = get_patron_borrowed_books(pid)  # returns borrow_date, due_date, title/author, is_overdue
    current_loans: List[Dict] = []
    total_fees = 0.0

    for rec in active:
        fee_info = calculate_late_fee_for_book(pid, rec["book_id"])
        fee_amt = float(fee_info.get("fee_amount", 0.0))
        total_fees += fee_amt

        days_overdue = max(0, (datetime.now().date() - rec["due_date"].date()).days)

        current_loans.append({
            "book_id": rec["book_id"],
            "title": rec["title"],
            "author": rec["author"],
            "borrow_date": rec["borrow_date"],
            "due_date": rec["due_date"],
            "days_overdue": days_overdue,
            "late_fee": round(fee_amt, 2),
        })

    # Full history (returned + active)
    history = get_borrow_history_for_patron(pid)
    counts = {
        "currently_borrowed": len(current_loans),
        "history_total": len(history),
    }

    return {
        "patron_id": pid,
        "current_loans": current_loans,
        "counts": counts,
        "total_late_fees": round(total_fees, 2),
        "history": history,
    }

# ======================================================================
# A3: Payment-related Business Logic
# ======================================================================

def pay_late_fees(
    patron_id: str,
    book_id: int,
    payment_gateway: PaymentGateway,
) -> Tuple[bool, str | None, str]:
    """
    Process late fee payment for a specific book borrowed by a patron.

    Uses:
      - calculate_late_fee_for_book()         -> determine amount owed
      - get_book_by_id()                      -> validate the book exists
      - payment_gateway.process_payment()     -> external payment API (mocked in tests)

    Returns:
        (success: bool, transaction_id: str | None, message: str)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, None, "Invalid patron ID. Must be exactly 6 digits."

    # Validate and normalize book_id
    try:
        book_id = int(book_id)
    except (TypeError, ValueError):
        return False, None, "Invalid book ID."

    # Ensure book exists
    book = get_book_by_id(book_id)
    if not book:
        return False, None, "Book not found."

    # Calculate late fee
    fee_info = calculate_late_fee_for_book(patron_id, book_id)
    amount = float(fee_info.get("fee_amount", 0.0))
    status = fee_info.get("status", "")

    # No fee due -> do NOT call payment gateway
    if amount <= 0 or status != "late":
        return False, None, "No late fees due for this book."

    if payment_gateway is None:
        return False, None, "Payment gateway is required."

    description = f"Late fee for book {book_id}"

    # Attempt payment via external gateway
    try:
        success, transaction_id, message = payment_gateway.process_payment(
            patron_id, amount, description
        )
    except Exception as exc:
        # Network / API failure
        return False, None, f"Payment failed due to an exception: {exc}"

    if not success:
        # Payment declined or failed
        return False, None, f"Payment failed: {message}"

    # Success
    return True, transaction_id, f"Late fee payment successful: {message}"


def refund_late_fee_payment(
    transaction_id: str,
    amount: float,
    payment_gateway: PaymentGateway,
) -> Tuple[bool, str]:
    """
    Process a refund for a previously charged late fee.

    Uses:
      - payment_gateway.refund_payment()

    Validation rules:
      - transaction_id must be a non-empty string and look like a valid ID
        (for this assignment we require it to start with 'txn_')
      - amount must be > 0
      - amount must NOT exceed $15.00 (max late fee)

    Returns:
        (success: bool, message: str)
    """
    if not transaction_id or not isinstance(transaction_id, str):
        return False, "Invalid transaction ID."

    # Simple shape check to align with the PaymentGateway style
    if not transaction_id.startswith("txn_"):
        return False, "Invalid transaction ID."

    # Validate amount
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False, "Invalid refund amount."

    if amount <= 0:
        return False, "Refund amount must be greater than 0."
    if amount > 15.00:
        return False, "Refund amount cannot exceed $15.00."

    if payment_gateway is None:
        return False, "Payment gateway is required."

    # Call external gateway (mocked in tests)
    try:
        success, message = payment_gateway.refund_payment(transaction_id, amount)
    except Exception as exc:
        return False, f"Refund failed due to an exception: {exc}"

    if not success:
        return False, f"Refund failed: {message}"

    return True, message
