import io
import pandas as pd
from flask import send_file
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import os, json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from urllib.parse import unquote  # ✅ To decode %20 in names

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
    qty = int(request.form['quantity'])
    update_sheet(clinic, name, qty)
    return redirect(url_for('index', clinic=clinic))

@app.route('/delete/<clinic>/<path:name>')  # ✅ Handles spaces in medicine names
def delete(clinic, name):
    delete_from_sheet(clinic, name)
    return redirect(url_for('index', clinic=clinic))

@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if 'user' not in session:
        return redirect(url_for('login'))

    clinic = request.args.get('clinic', 'Boys')

    stock = get_stock(clinic)  # Get stock list to populate dropdown

    if request.method == 'POST':
        tr_no = request.form['tr_no']
        med_name = request.form['med_name']
        count = int(request.form['count'])

        log_dispatch(clinic, tr_no, med_name, count)
        subtract_stock(clinic, med_name, count)
        return redirect(url_for('dispatch', clinic=clinic))

    dispatch_log = get_dispatch_log(clinic)
    return render_template('dispatch.html', dispatch_log=dispatch_log, clinic=clinic, stock=stock)

@app.route('/delete_dispatch/<clinic>/<int:index>')
def delete_dispatch(clinic, index):
    sheet = get_dispatch_sheet(clinic)
    data = sheet.get_all_values()

    # Get row details (index + 1 for header, +1 for 1-based index)
    row = data[index + 1]  # index 0 = header, index+1 = actual row
    tr_no = row[0]
    med_name = row[1]
    count = int(row[2])

    # Add back to stock
    try:
        stock_sheet = get_stock_sheet(clinic)
        cell = stock_sheet.find(med_name)
        current_qty = int(stock_sheet.cell(cell.row, 2).value)
        stock_sheet.update_cell(cell.row, 2, current_qty + count)
    except Exception as e:
        print(f"Error restoring stock during dispatch deletion: {e}")

    # Delete the dispatch log entry
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

    # Check if required columns exist
    if not {'Medicine Name', 'Count', 'Timestamp'}.issubset(df.columns):
        return "Dispatch log is missing required columns", 500

    # Convert 'Timestamp' to datetime and extract month-year
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Timestamp'])  # remove bad dates
    df['Month'] = df['Timestamp'].dt.strftime('%B %Y')  # e.g., July 2025

    # Group by Medicine and Month
    report_df = df.groupby(['Medicine Name', 'Month'])['Count'].sum().reset_index()

    if filetype == 'csv':
        output = report_df.to_csv(index=False)
        response = make_response(output)
        response.headers["Content-Disposition"] = f"attachment; filename={clinic}_monthly_report.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    elif filetype == 'excel':
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False, sheet_name='Monthly Report')
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={clinic}_monthly_report.xlsx"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response

    else:
        return "Invalid file type", 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
    
