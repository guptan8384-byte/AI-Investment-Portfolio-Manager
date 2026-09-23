import os
import json

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session
)

from backend import generate_unique_portfolios


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key"
)

USERS_FILE = "users.json"


# =========================================================
# CURRENCY FORMATTING
# =========================================================

def format_indian_number(value):

    try:
        number = int(float(value))

    except (TypeError, ValueError):
        return "0"

    s = str(abs(number))

    if len(s) <= 3:
        return s

    last = s[-3:]

    rest = s[:-3]

    chunks = []

    while len(rest) > 2:

        chunks.append(
            rest[-2:]
        )

        rest = rest[:-2]

    if rest:
        chunks.append(rest)

    chunks.reverse()

    return (
        ",".join(chunks)
        + ","
        + last
    )


def format_currency(value):

    try:
        numeric = float(value)

    except (TypeError, ValueError):
        return "₹0"

    sign = (
        "-"
        if numeric < 0
        else ""
    )

    numeric = abs(numeric)

    integer_part = int(
        numeric
    )

    fractional_part = round(
        (
            numeric
            - integer_part
        ) * 100
    )

    if fractional_part == 100:

        integer_part += 1

        fractional_part = 0

    whole = format_indian_number(
        integer_part
    )

    if fractional_part:

        return (
            f"{sign}₹"
            f"{whole}."
            f"{fractional_part:02d}"
        )

    return (
        f"{sign}₹{whole}"
    )


app.jinja_env.filters[
    "inr"
] = format_currency


# =========================================================
# USER AUTHENTICATION
# =========================================================

def load_users():

    """
    Vercel:
        Reads users from USERS_JSON.

    Local:
        Reads users.json.
    """

    users_json = os.environ.get(
        "USERS_JSON"
    )

    if users_json:

        try:

            return json.loads(
                users_json
            )

        except json.JSONDecodeError:

            return {}

    # Local development

    if not os.path.exists(
        USERS_FILE
    ):

        with open(
            USERS_FILE,
            "w"
        ) as f:

            json.dump(
                {},
                f
            )

    with open(
        USERS_FILE,
        "r"
    ) as f:

        return json.load(f)


def save_user(
    username,
    password
):

    # Registration is disabled
    # on deployed Vercel version.

    if os.environ.get(
        "USERS_JSON"
    ):

        return False

    users = load_users()

    users[username] = password

    with open(
        USERS_FILE,
        "w"
    ) as f:

        json.dump(
            users,
            f
        )

    return True


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        username = (
            request.form[
                "username"
            ].strip()
        )

        password = request.form[
            "password"
        ]

        users = load_users()

        if username in users:

            return render_template(
                "register.html",
                error=(
                    "Username already exists."
                )
            )

        if os.environ.get(
            "USERS_JSON"
        ):

            return render_template(
                "register.html",
                error=(
                    "Registration is currently "
                    "unavailable on the deployed "
                    "version. Please use the demo account."
                )
            )

        if not save_user(
            username,
            password
        ):

            return render_template(
                "register.html",
                error=(
                    "Registration is unavailable."
                )
            )

        session[
            "user"
        ] = username

        return redirect("/")

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    users = load_users()

    if request.method == "POST":

        username = (
            request.form[
                "username"
            ].strip()
        )

        password = request.form[
            "password"
        ]

        if (
            username in users
            and
            users[username]
            == password
        ):

            session[
                "user"
            ] = username

            return redirect("/")

        return render_template(
            "login.html",
            error=(
                "Invalid username "
                "or password."
            )
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.pop(
        "user",
        None
    )

    return redirect(
        "/login"
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    if "user" not in session:

        return redirect(
            "/login"
        )

    return render_template(
        "index.html",
        username=session[
            "user"
        ]
    )


# =========================================================
# PORTFOLIO RESULTS
# =========================================================

@app.route(
    "/results",
    methods=["POST"]
)
def results():

    if "user" not in session:

        return redirect(
            "/login"
        )

    try:

        investment = float(
            request.form[
                "investment"
            ]
        )

    except (
        TypeError,
        ValueError
    ):

        return redirect("/")


    risk_level = request.form[
        "risk"
    ]

    time_goal = request.form[
        "goal"
    ]


    risk_label = {

        "low":
            "Low Risk",

        "moderate":
            "Moderate Risk",

        "high":
            "High Risk"

    }.get(
        risk_level,
        risk_level.title()
    )


    goal_label = {

        "short":
            "Short Term",

        "long":
            "Long Term"

    }.get(
        time_goal,
        time_goal.title()
    )


    try:

        # No Upstox token required.
        # Backend now uses server-side
        # market data.

        portfolios = (
            generate_unique_portfolios(
                None,
                investment,
                risk_level,
                time_goal
            )
        )

    except Exception as e:

        print(
            "Portfolio generation error:",
            e
        )

        return render_template(
            "index.html",
            username=session[
                "user"
            ],
            error=(
                "Unable to generate portfolio "
                "right now. Please try again."
            )
        )


    return render_template(
        "results.html",

        portfolios=portfolios,

        username=session[
            "user"
        ],

        selected_investment=
            investment,

        selected_risk=
            risk_label,

        selected_goal=
            goal_label
    )


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )