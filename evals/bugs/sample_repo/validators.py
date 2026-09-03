def validate_email(email):
    if email is None:
        return False
    email = email.strip()
    return "@" in email and "." in email.split("@")[-1]
