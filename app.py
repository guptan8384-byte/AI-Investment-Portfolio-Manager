import os
import json
import requests
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, session
from backend import authenticate, generate_unique_portfolios

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

USERS_FILE = "users.json"


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
        chunks.append(rest[-2:])
        rest = rest[:-2]

    if rest:
        chunks.append(rest)

    chunks.reverse()

    return ",".join(chunks) + "," + last


def format_currency(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "₹0"

    sign = "-" if numeric < 0 else ""
    numeric = abs(numeric)

    integer_part = int(numeric)
    fractional_part = round((numeric - integer_part) * 100)

    if fractional_part == 100:
        integer_part += 1
        fractional_part = 0

    whole = format_indian_number(integer_part)

    if fractional_part:
        return f"{sign}₹{whole}.{fractional_part:02d}"

    return f"{sign}₹{whole}"


app.jinja_env.filters['inr'] = format_currency


# ---------------------------------------------------------
# USER AUTHENTICATION
# ---------------------------------------------------------

def load_users():
    """
    Local:
        Uses users.json.

    Vercel:
        Uses USERS_JSON environment variable because
        Vercel's filesystem is not persistent/writeable.
    """

    users_json = os.environ.get("USERS_JSON")

    if users_json:
        try:
            return json.loads(users_json)
        except json.JSONDecodeError:
            return {}

    # Local development
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)

    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_user(username, password):
    """
    Saves users locally.

    On Vercel, registration is disabled because environment
    variables cannot be modified by the running application.
    """

    if os.environ.get("USERS_JSON"):
        return False

    users = load_users()
    users[username] = password

    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

    return True


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        users = load_users()

        if username in users:
            return render_template(
                'register.html',
                error="Username already exists."
            )

        # On Vercel, users cannot be permanently registered.
        if os.environ.get("USERS_JSON"):
            return render_template(
                'register.html',
                error="Registration is currently unavailable on the deployed version. Please use the demo account."
            )

        if not save_user(username, password):
            return render_template(
                'register.html',
                error="Registration is unavailable."
            )

        session['user'] = username

        return redirect('/')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    users = load_users()

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        if username in users and users[username] == password:
            session['user'] = username
            return redirect('/')

        return render_template(
            'login.html',
            error="Invalid username or password."
        )

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('upstox_access_token', None)

    return redirect('/login')


# ---------------------------------------------------------
# UPSTOX AUTHENTICATION
# ---------------------------------------------------------

@app.route('/connect-upstox')
def connect_upstox():
    if 'user' not in session:
        return redirect('/login')

    params = {
        'response_type': 'code',
        'client_id': os.environ.get('UPSTOX_CLIENT_ID'),
        'redirect_uri': os.environ.get('UPSTOX_REDIRECT_URI')
    }

    auth_url = (
        "https://api.upstox.com/v2/login/authorization/dialog?"
        + urllib.parse.urlencode(params)
    )

    return redirect(auth_url)


@app.route('/upstox/callback')
def upstox_callback():
    if 'user' not in session:
        return redirect('/login')

    code = request.args.get('code')

    if not code:
        return "Upstox authorization failed: authorization code missing.", 400

    token_response = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        },
        data={
            'code': code,
            'client_id': os.environ.get('UPSTOX_CLIENT_ID'),
            'client_secret': os.environ.get('UPSTOX_CLIENT_SECRET'),
            'redirect_uri': os.environ.get('UPSTOX_REDIRECT_URI'),
            'grant_type': 'authorization_code'
        },
        timeout=20
    )

    if token_response.status_code != 200:
        return "Unable to authenticate with Upstox.", 400

    token_data = token_response.json()

    access_token = token_data.get('access_token')

    if not access_token:
        return "Upstox did not return an access token.", 400

    session['upstox_access_token'] = access_token

    return redirect('/')


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.route('/')
def index():
    if 'user' not in session:
        return redirect('/login')

    return render_template(
        'index.html',
        username=session['user']
    )


# ---------------------------------------------------------
# PORTFOLIO RESULTS
# ---------------------------------------------------------

@app.route('/results', methods=['POST'])
def results():
    if 'user' not in session:
        return redirect('/login')

    investment = float(request.form['investment'])
    risk_level = request.form['risk']
    time_goal = request.form['goal']

    risk_label = {
        'low': 'Low Risk',
        'moderate': 'Moderate Risk',
        'high': 'High Risk'
    }.get(
        risk_level,
        risk_level.title()
    )

    goal_label = {
        'short': 'Short Term',
        'long': 'Long Term'
    }.get(
        time_goal,
        time_goal.title()
    )

    token = session.get('upstox_access_token')

    if not token:
        return redirect('/connect-upstox')

    portfolios = generate_unique_portfolios(
        token,
        investment,
        risk_level,
        time_goal
    )

    return render_template(
        'results.html',
        portfolios=portfolios,
        username=session['user'],
        selected_investment=investment,
        selected_risk=risk_label,
        selected_goal=goal_label
    )


# ---------------------------------------------------------
# LOCAL DEVELOPMENT
# ---------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True)