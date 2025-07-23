import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, send_file
import os, json, io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from urllib.parse import unquote
import pandas as pd

app = Flask(__name__)
app.secret_key = '515253'  # Any random string

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
    except Exception as e:
        print("Item not found during update. Adding new instead:", e)
        add_to_sheet(clinic, name, qty)

def delete_from_sheet(clinic, name):
    sheet = get_stock_sheet(clinic)
    try:
        decoded_name = unquote(name)
        cell = sheet.find(decoded_name)
        if cell:
            sheet.delete_rows(cell.row)
        else:
            print(f"[INFO] Item not found for deletion: {decoded_name}")
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
    except Exception as e:
        print("Error during stock subtraction:", e)

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
        print("Error in update. Trying add_to_sheet:", e)
        try:
            add_to_sheet(clinic, name, qty)
        except Exception as e2:
            print("Error in add_to_sheet:", e2)

    return redirect(url_for('index', clinic=clinic))

@app.route('/update/<clinic>/<name>', methods=['POST'])
def update(clinic, name):
    if session.get('user') != 'admin':
        flash("You are not authorized to update stock.")
        return redirect(url_for('index', clinic=clinic))

    qty = int(request.form['quantity'])
    update_sheet(clinic, name, qty)
    return redirect(url_for('index', clinic=clinic))

@app.route('/delete/<clinic>/<path:name>')
def delete(clinic, name):
    if session.get('user') != 'admin':
        flash("You are not authorized to delete stock.")
        return redirect(url_for('index', clinic=clinic))

    delete_from_sheet(clinic, name)
    return redirect(url_for('index', clinic=clinic))

@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if 'user' not in session:
        return redirect(url_for('login'))

    clinic = request.args.get('clinic', 'Boys')
    month = request.args.get('month')
    year = request.args.get('year')

    stock = get_stock(clinic)
    dispatch_log = get_dispatch_log(clinic)

    if month and year:
        dispatch_log = [
            row for row in dispatch_log
            if row['Timestamp'].startswith(f"{year}-{month.zfill(2)}")
        ]

    if request.method == 'POST':
        tr_no = request.form['tr_no']
        med_name = request.form['med_name']
        count = int(request.form['count'])

        stock = get_stock(clinic)  # Refresh stock
        item = next((i for i in stock if i['Name'].strip().lower() == med_name.strip().lower()), None)

        if item is None:
            flash(f"Medicine '{med_name}' not found in stock.")
            return redirect(url_for('dispatch', clinic=clinic))

        if int(item['Quantity']) <= 0:
            flash(f"Cannot dispatch '{med_name}'. Stock is zero.")
            return redirect(url_for('dispatch', clinic=clinic))

        if int(item['Quantity']) < count:
            flash(f"Cannot dispatch {count} units of '{med_name}'. Only {item['Quantity']} in stock.")
            return redirect(url_for('dispatch', clinic=clinic))

        log_dispatch(clinic, tr_no, med_name, count)
        subtract_stock(clinic, med_name, count)
        flash(f"{count} units of '{med_name}' dispatched successfully.")
        return redirect(url_for('dispatch', clinic=clinic))

    return render_template('dispatch.html', dispatch_log=dispatch_log, clinic=clinic, stock=stock)

@app.route('/delete_dispatch/<clinic>/<int:index>')
def delete_dispatch(clinic, index):
    sheet = get_dispatch_sheet(clinic)
    data = sheet.get_all_values()
    row = data[index + 1]
    tr_no = row[0]
    med_name = row[1]
    count = int(row[2])

    try:
        stock_sheet = get_stock_sheet(clinic)
        cell = stock_sheet.find(med_name)
        current_qty = int(stock_sheet.cell(cell.row, 2).value)
        stock_sheet.update_cell(cell.row, 2, current_qty + count)
    except Exception as e:
        print(f"Error restoring stock during dispatch deletion: {e}")

    sheet.delete_rows(index + 2)
    return redirect(url_for('dispatch', clinic=clinic))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == 'mahlushifa515253':
            session['user'] = 'admin'
            return redirect(url_for('index'))
        elif username == 'staff' and password == 'med786':
            session['user'] = 'staff'
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/download_stock/<clinic>/<filetype>')
def download_stock(clinic, filetype):
    data = get_stock(clinic)
    df = pd.DataFrame(data)

    if filetype == 'csv':
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{clinic}_stock.csv'
        )
    elif filetype == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=f"{clinic} Stock")
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{clinic}_stock.xlsx'
        )

@app.route('/download_dispatch/<clinic>/<filetype>')
def download_dispatch(clinic, filetype):
    data = get_dispatch_log(clinic)
    df = pd.DataFrame(data)

    if filetype == 'csv':
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{clinic}_dispatch.csv'
        )
    elif filetype == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=f"{clinic} Dispatch")
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{clinic}_dispatch.xlsx'
        )

@app.route('/monthly_report/<clinic>/<filetype>')
def monthly_report(clinic, filetype):
    dispatch_log = get_dispatch_log(clinic)
    df = pd.DataFrame(dispatch_log)

    if not {'Medicine Name', 'Count', 'Timestamp'}.issubset(df.columns):
        return "Dispatch log is missing required columns", 500

    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Timestamp'])
    df['Month'] = df['Timestamp'].dt.strftime('%B %Y')
    report_df = df.groupby(['Medicine Name', 'Month'])['Count'].sum().reset_index()

    if filetype == 'csv':
        output = report_df.to_csv(index=False)
        response = make_response(output)
        response.headers["Content-Disposition"] = f"attachment; filename={clinic}_monthly_report.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    elif filetype == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False, sheet_name='Monthly Report')
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={clinic}_monthly_report.xlsx"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response

    else:
        return "Invalid file type", 400

@app.route('/upload_stock', methods=['GET', 'POST'])
def upload_stock():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        clinic = request.form['clinic']
        file = request.files['file']

        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.')
            return redirect(request.url)

        content = file.stream.read().decode('utf-8')
        csv_data = csv.DictReader(StringIO(content))

        sheet = get_stock_sheet(clinic)
        sheet.clear()
        sheet.append_row(['Name', 'Quantity'])

        for row in csv_data:
            name = row.get('Name')
            qty = row.get('Quantity')
            if name and qty:
                sheet.append_row([name, qty])

        flash('Stock uploaded successfully.')
        return redirect(url_for('index', clinic=clinic))

    return render_template('upload_stock.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
