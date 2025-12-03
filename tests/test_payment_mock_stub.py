import pytest
from unittest.mock import Mock

from services.library_service import (
    pay_late_fees,
    refund_late_fee_payment,
)
from services.payment_service import PaymentGateway


# ---------------------------------------------------------------------------
# pay_late_fees tests
# ---------------------------------------------------------------------------

def test_pay_late_fees_successful_payment(mocker):
    """Should call payment gateway and succeed when valid late fee exists."""
    # Stubs
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Late Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.0, "days_overdue": 3, "status": "late"},
    )

    # Mock for external gateway
    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.return_value = (True, "txn_123", "Approved")

    success, txn_id, message = pay_late_fees("123456", 1, gateway)

    assert success is True
    assert txn_id == "txn_123"
    assert "successful" in message.lower()

    gateway.process_payment.assert_called_once_with(
        "123456",
        5.0,
        "Late fee for book 1",
    )


def test_pay_late_fees_payment_declined(mocker):
    """Should return failure when gateway declines the payment."""
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 2, "title": "Declined Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 7.5, "days_overdue": 5, "status": "late"},
    )

    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.return_value = (False, None, "Declined")

    success, txn_id, message = pay_late_fees("123456", 2, gateway)

    assert success is False
    assert txn_id is None
    assert "failed" in message.lower()
    assert "declined" in message.lower()

    gateway.process_payment.assert_called_once()


def test_pay_late_fees_invalid_patron_no_gateway_call(mocker):
    """Invalid patron ID should short-circuit and never call the gateway."""
    # Even if these were defined, they must not be used
    fee_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.0, "days_overdue": 2, "status": "late"},
    )
    book_stub = mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Some Book"},
    )

    gateway = Mock(spec=PaymentGateway)

    success, txn_id, message = pay_late_fees("XX3456", 1, gateway)

    assert success is False
    assert txn_id is None
    assert "invalid patron" in message.lower()

    # No external calls
    gateway.process_payment.assert_not_called()
    # And realistically we also shouldn't hit internal deps
    fee_stub.assert_not_called()
    book_stub.assert_not_called()


def test_pay_late_fees_no_late_fee_no_gateway_call(mocker):
    """When no late fee is due, do not call payment gateway."""
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 3, "title": "On Time Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 0.0, "days_overdue": 0, "status": "on_time"},
    )

    gateway = Mock(spec=PaymentGateway)

    success, txn_id, message = pay_late_fees("123456", 3, gateway)

    assert success is False
    assert txn_id is None
    assert "no late fees" in message.lower()

    gateway.process_payment.assert_not_called()


def test_pay_late_fees_gateway_exception_handled(mocker):
    """Network/API exception from gateway should be caught and reported."""
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 4, "title": "Error Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 10.0, "days_overdue": 10, "status": "late"},
    )

    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.side_effect = Exception("Network down")

    success, txn_id, message = pay_late_fees("123456", 4, gateway)

    assert success is False
    assert txn_id is None
    assert "exception" in message.lower()
    assert "network down" in message.lower()

    gateway.process_payment.assert_called_once()


# ---------------------------------------------------------------------------
# refund_late_fee_payment tests
# ---------------------------------------------------------------------------

def test_refund_late_fee_success(mocker):
    """Valid transaction and amount should call refund_payment and succeed."""
    gateway = Mock(spec=PaymentGateway)
    gateway.refund_payment.return_value = (True, "Refunded")

    success, message = refund_late_fee_payment("txn_abc123", 5.0, gateway)

    assert success is True
    assert "refunded" in message.lower()

    gateway.refund_payment.assert_called_once_with("txn_abc123", 5.0)


@pytest.mark.parametrize("txid", ["", None, "abc123"])
def test_refund_late_fee_invalid_transaction_id_no_call(txid):
    """Invalid transaction IDs should be rejected without calling the gateway."""
    gateway = Mock(spec=PaymentGateway)

    success, message = refund_late_fee_payment(txid, 5.0, gateway)

    assert success is False
    assert "invalid transaction id" in message.lower()
    gateway.refund_payment.assert_not_called()


@pytest.mark.parametrize("amount", [-1, 0])
def test_refund_late_fee_invalid_non_positive_amount_no_call(amount):
    """Zero or negative amounts should be rejected without gateway call."""
    gateway = Mock(spec=PaymentGateway)

    success, message = refund_late_fee_payment("txn_valid", amount, gateway)

    assert success is False
    assert "greater than 0" in message.lower()
    gateway.refund_payment.assert_not_called()


def test_refund_late_fee_amount_exceeds_cap_no_call():
    """Amounts greater than $15 should be rejected."""
    gateway = Mock(spec=PaymentGateway)

    success, message = refund_late_fee_payment("txn_valid", 20.0, gateway)

    assert success is False
    assert "cannot exceed $15.00" in message
    gateway.refund_payment.assert_not_called()


def test_refund_late_fee_gateway_failure():
    """Gateway returning failure should be surfaced correctly."""
    gateway = Mock(spec=PaymentGateway)
    gateway.refund_payment.return_value = (False, "Card expired")

    success, message = refund_late_fee_payment("txn_abc", 5.0, gateway)

    assert success is False
    assert "failed" in message.lower()
    gateway.refund_payment.assert_called_once_with("txn_abc", 5.0)


def test_refund_late_fee_gateway_exception():
    """Exceptions from refund_payment should be caught and reported."""
    gateway = Mock(spec=PaymentGateway)
    gateway.refund_payment.side_effect = Exception("Timeout")

    success, message = refund_late_fee_payment("txn_abc", 5.0, gateway)

    assert success is False
    assert "exception" in message.lower()
    assert "timeout" in message.lower()
    gateway.refund_payment.assert_called_once_with("txn_abc", 5.0)
