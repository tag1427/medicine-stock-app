from flask import Flask, render_template, request, redirect, url_for, session, flash
import os, json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
app.secret_key = '515253'

# Google Sheets Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_credentials = json.loads(os.environ['GOOGLE_CREDENTIALS'])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_credentials, scope)
client = gspread.authorize(creds)

# Helpers
def get_stock_sheet(clinic):
    return client.open("Medicine Stock").worksheet(f"{clinic}Stock")

def get_dispatch_sheet(clinic):
    return client.open("Medicine Stock").worksheet(f"{clinic}DispatchLog")

def get_stock(clinic):
    return get_stock_sheet(clinic).get_all_records()

def get_dispatch_log(clinic):
    return get_dispatch_sheet(clinic).get_all_records()

def add_to_sheet(clinic, name, qty):
    get_stock_sheet(clinic).append_row([name, qty])

def update_sheet(clinic, name, qty):
    sheet = get_stock_sheet(clinic)
    try:
        cell = sheet.find(name)
        sheet.update_cell(cell.row, 2, qty)
    except CellNotFound:
        add_to_sheet(clinic, name, qty)

def delete_from_sheet(clinic, name):
    sheet = get_stock_sheet(clinic)
    try:
        cell = sheet.find(name)
        if cell:
            sheet.delete_rows(cell.row)
    except Exception as e:
        print(f"Error deleting '{name}' from {clinic}Stock:", e)
        
def log_dispatch(clinic, tr_no, med_name, count):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    get_dispatch_sheet(clinic).append_row([tr_no, med_name, count, timestamp])

def subtract_stock(clinic, med_name, count):
    sheet = get_stock_sheet(clinic)
    try:
        cell = sheet.find(med_name)
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = max(current_qty - count, 0)
        sheet.update_cell(cell.row, 2, new_qty)
    except CellNotFound:
        pass

# Routes
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    clinic = request.args.get('clinic', 'Boys')
    stock = get_stock(clinic)
    return render_template('index.html', stock=stock, clinic=clinic)

@app.route('/add', methods=['POST'])
def add():
    clinic = request.form['clinic']
    name = request.form['name']
    qty = int(request.form['quantity'])

    try:
        update_sheet(clinic, name, qty)
    except Exception as e:
        # If the medicine is not found, add a new row
        print("Error during update, trying to add new row:", e)
        try:
            add_to_sheet(clinic, name, qty)
        except Exception as e2:
            print("Error in add_to_sheet:", e2)

    return redirect(url_for('index', clinic=clinic))

@app.route('/update/<clinic>/<name>', methods=['POST'])
def update(clinic, name):
    qty = int(request.form['quantity'])
    update_sheet(clinic, name, qty)
    return redirect(url_for('index', clinic=clinic))

@app.route('/delete/<clinic>/<path:name>')
def delete(clinic, name):
    delete_from_sheet(clinic, name)
    return redirect(url_for('index', clinic=clinic))

@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if 'user' not in session:
        return redirect(url_for('login'))

    clinic = request.args.get('clinic', 'Boys')

    if request.method == 'POST':
        tr_no = request.form['tr_no']
        med_name = request.form['med_name']
        count = int(request.form['count'])

        log_dispatch(clinic, tr_no, med_name, count)
        subtract_stock(clinic, med_name, count)
        return redirect(url_for('dispatch', clinic=clinic))

    dispatch_log = get_dispatch_log(clinic)
    return render_template('dispatch.html', dispatch_log=dispatch_log, clinic=clinic)

@app.route('/delete_dispatch/<clinic>/<int:index>')
def delete_dispatch(clinic, index):
    sheet = get_dispatch_sheet(clinic)
    sheet.delete_rows(index + 2)
    return redirect(url_for('dispatch', clinic=clinic))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'staff' and password == 'med786':
            session['user'] = username
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
