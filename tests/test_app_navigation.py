from streamlit.testing.v1 import AppTest


def test_account_icon_opens_sign_in_and_links_to_account_creation():
    app = AppTest.from_file("app.py").run(timeout=45)

    app.button(key="header_account_button").click().run(timeout=45)

    assert not app.exception
    assert any(field.label == "Email" for field in app.text_input)
    assert any(button.key == "open_create_account" for button in app.button)

    app.button(key="open_create_account").click().run(timeout=45)

    assert not app.exception
    assert any("Create your account" in str(item.value) for item in app.markdown)
    assert any(button.key == "open_sign_in" for button in app.button)

    app.button(key="open_sign_in").click().run(timeout=45)

    assert not app.exception
    assert any(button.key == "open_create_account" for button in app.button)
