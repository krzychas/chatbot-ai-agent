import json
import bcrypt

USERS_FILE = "users.json"

with open(
    USERS_FILE,
    "r",
    encoding="utf-8"
) as f:

    users = json.load(f)

username = input("Login: ")
password = input("Hasło: ")

users[username] = bcrypt.hashpw(
    password.encode("utf-8"),
    bcrypt.gensalt()
).decode("utf-8")

with open(
    USERS_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        users,
        f,
        ensure_ascii=False,
        indent=2
    )

print("Dodano użytkownika.")
