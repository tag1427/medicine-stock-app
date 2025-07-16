from flask import Flask, render_template, request, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Setup Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import os
import json

google_credentials = json.loads(os.environ['GOOGLE_CREDENTIALS'])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_credentials, scope)
client = gspread.authorize(creds)

sheet = client.open("Medicine Stock").sheet1

def get_stock():
    records = sheet.get_all_records()
    return records
def get_dispatch_log():
    records = dispatch_sheet.get_all_records()
    return records
    
def add_to_sheet(name, qty):
    sheet.append_row([name, qty])

def update_sheet(name, qty):
    cell = sheet.find(name)
    sheet.update_cell(cell.row, 2, qty)

def delete_from_sheet(name):
    cell = sheet.find(name)
    sheet.delete_rows(cell.row)

@app.route('/')
def index():
    stock = get_stock()
    return render_template('index.html', stock=stock)

@app.route('/add', methods=['POST'])
def add():
    name = request.form['name']
    qty = int(request.form['quantity'])

    try:
        update_sheet(name, qty)
    except:
        add_to_sheet(name, qty)

    return redirect(url_for('index'))

@app.route('/update/<name>', methods=['POST'])
def update(name):
    qty = int(request.form['quantity'])
    update_sheet(name, qty)
    return redirect(url_for('index'))

@app.route('/delete/<name>')
def delete(name):
    delete_from_sheet(name)
    return redirect(url_for('index'))
from datetime import datetime

# Reference Sheet2: DispatchLog
dispatch_sheet = client.open("Medicine Stock").worksheet("DispatchLog")

def log_dispatch(tr_no, med_name, count):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dispatch_sheet.append_row([tr_no, med_name, count, timestamp])

def subtract_stock(med_name, count):
    try:
        cell = sheet.find(med_name)
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = current_qty - count
        if new_qty < 0:
            new_qty = 0
        sheet.update_cell(cell.row, 2, new_qty)
    except:
        pass  # If medicine not found, do nothing (you can improve this)
@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if request.method == 'POST':
        tr_no = request.form['tr_no']
        med_name = request.form['med_name']
        count = int(request.form['count'])

        log_dispatch(tr_no, med_name, count)
        subtract_stock(med_name, count)
        return redirect(url_for('dispatch'))

    dispatch_log = get_dispatch_log()
    return render_template('dispatch.html', dispatch_log=dispatch_log)
@app.route('/delete_dispatch/<int:index>')
def delete_dispatch(index):
    dispatch_sheet.delete_rows(index + 2)
    return redirect(url_for('dispatch'))
if __name__ == '__main__':
    app.run(debug=True)
