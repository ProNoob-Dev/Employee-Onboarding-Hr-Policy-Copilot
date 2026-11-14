from app.pii import contains_unmasked_pii, mask_pii


def test_masks_email():
    assert mask_pii("mail me at jane.doe@example.com please") == "mail me at [EMAIL] please"


def test_masks_phone_indian():
    assert "[PHONE]" in mask_pii("call me on 9876543210")
    assert "[PHONE]" in mask_pii("call me on +91 98765 43210")


def test_masks_aadhaar():
    assert mask_pii("aadhaar 1234 5678 9012") == "aadhaar [AADHAAR]"
    assert mask_pii("aadhaar 123456789012") == "aadhaar [AADHAAR]"


def test_masks_pan():
    assert mask_pii("PAN ABCDE1234F") == "PAN [PAN]"
    assert mask_pii("pan abcde1234f") == "pan [PAN]"


def test_masks_phone_with_parentheses():
    assert mask_pii("call me on (9876543210)") == "call me on [PHONE]"
    assert mask_pii("call me on +91 (98765 43210)") == "call me on [PHONE]"
    assert mask_pii("call (98765) 43210") == "call [PHONE]"


def test_masks_compensation():
    assert mask_pii("my CTC is Rs 12,00,000") == "my CTC is [COMPENSATION]"
    assert mask_pii("salary is ₹18 lakh") == "salary is [COMPENSATION]"
    assert mask_pii("offer is Rs 12 lakh per annum") == "offer is [COMPENSATION] per annum"
    assert mask_pii("package is ₹18 LPA") == "package is [COMPENSATION]"
    assert mask_pii("deal costs INR 2 crore") == "deal costs [COMPENSATION]"


def test_compensation_needs_a_digit_after_the_marker():
    # Regression: the "Rs" tail of "hours"/"years" followed by a comma was
    # masked as compensation, corrupting REMOTE-02 and IT-02 clause text.
    assert mask_pii("reachable during working hours, and attend meetings") == (
        "reachable during working hours, and attend meetings")
    assert mask_pii("laptops are replaced every 3 years, or earlier") == (
        "laptops are replaced every 3 years, or earlier")


def test_keeps_employee_id():
    assert mask_pii("employee EMP-001 asked") == "employee EMP-001 asked"


def test_mask_is_idempotent():
    masked = mask_pii("jane@example.com, 9876543210, Rs 500000")
    assert mask_pii(masked) == masked


def test_contains_unmasked_pii_detects_leaks():
    assert contains_unmasked_pii("reach me at jane@example.com")
    assert not contains_unmasked_pii("reach me at [EMAIL]")


def test_uuid_tail_is_not_a_phone():
    # Regression: a UUID hex tail is mostly digits but is not PII.
    assert not contains_unmasked_pii("4cd4636b-8345-40a5-9cda-d87016788068")
    assert mask_pii("event 4cd4636b-8345-40a5-9cda-d87016788068") == (
        "event 4cd4636b-8345-40a5-9cda-d87016788068")
