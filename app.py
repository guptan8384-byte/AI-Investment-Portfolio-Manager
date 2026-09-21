from flask import Flask, render_template, request, redirect, url_for, session
from backend import authenticate, generate_unique_portfolios
import os, json

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Must be set for sessions

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


# Load users from file (or create if not present)
def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_user(username, password):
    users = load_users()
    users[username] = password
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()
        if username in users:
            return render_template('register.html', error="Username already exists.")
        save_user(username, password)
        session['user'] = username
        return redirect('/')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    users = load_users()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username] == password:
            session['user'] = username
            return redirect('/')
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


@app.route('/')
def index():
    if 'user' not in session:
        return redirect('/login')
    return render_template('index.html', username=session['user'])


@app.route('/results', methods=['POST'])
def results():
    if 'user' not in session:
        return redirect('/login')
    investment = float(request.form['investment'])
    risk_level = request.form['risk']
    time_goal = request.form['goal']
    risk_label = {'low': 'Low Risk', 'moderate': 'Moderate Risk', 'high': 'High Risk'}.get(risk_level, risk_level.title())
    goal_label = {'short': 'Short Term', 'long': 'Long Term'}.get(time_goal, time_goal.title())
    token = authenticate()
    portfolios = generate_unique_portfolios(token, investment, risk_level, time_goal)
    return render_template(
        'results.html',
        portfolios=portfolios,
        username=session['user'],
        selected_investment=investment,
        selected_risk=risk_label,
        selected_goal=goal_label
    )


if __name__ == '__main__':
    app.run(debug=True)
