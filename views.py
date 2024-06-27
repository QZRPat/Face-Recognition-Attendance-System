from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app, Response, make_response, \
    flash, session
from flask_login import current_user
from .models import Students
from .models import AttendanceDB
from . import db
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date, timedelta, timezone
from io import BytesIO, StringIO
from flask import Response
from flask_excel import make_response_from_query_sets
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from collections import defaultdict
from .capture import capture_and_save_image
import os
import cv2
import subprocess
import csv
import shutil
import time
import pytz
import datetime
from datetime import datetime
import configparser
import pandas as pd

views = Blueprint('views', __name__)


@views.before_request
def before_request():
    # Check if the user is not logged in and the requested endpoint requires login
    if current_user.is_anonymous and request.endpoint not in ['auth.login']:
        return redirect(url_for('auth.login'))


@views.route('/')
def index():
    return render_template("login.html")


@views.route('/home', methods=['GET', 'POST'])
def home():
    selected_section = "0"  # Initialize selected_section with a default value

    if request.method == 'POST':
        selected_section = request.form.get('section')

        # For POST requests, display attendance for the selected section and current day
        attendance_data = AttendanceDB.query.filter(
            AttendanceDB.date_time_taken >= date.today(),
            AttendanceDB.date_time_taken < date.today() + timedelta(days=1),
            AttendanceDB.section == selected_section
        ).all()

        # Convert the attendance data to a list of dictionaries
        attendance_list = []
        for entry in attendance_data:
            attendance_list.append({
                'fullName': entry.fullName,
                'grade': entry.grade,
                'section': entry.section,
                'date_time_taken': entry.date_time_taken.strftime("%Y-%m-%d %I:%M %p"),  # Modify this line
                'status': entry.status
            })
        attendance_list = sorted(attendance_list, key=lambda x: x['fullName'])
        return render_template("index.html", attendance_list=attendance_list, selected_section=selected_section)

    # For GET requests, display attendance for all sections initially
    attendance_data = AttendanceDB.query.filter(
        AttendanceDB.date_time_taken >= date.today(),
        AttendanceDB.date_time_taken < date.today() + timedelta(days=1)
    ).all()

    # Convert the attendance data to a list of dictionaries
    attendance_list = []
    for entry in attendance_data:
        attendance_list.append({
            'fullName': entry.fullName,
            'grade': entry.grade,
            'section': entry.section,
            'date_time_taken': entry.date_time_taken.strftime("%Y-%m-%d %I:%M %p"),  # Modify this line
            'status': entry.status
        })
    attendance_list = sorted(attendance_list, key=lambda x: x['fullName'])
    return render_template("index.html", attendance_list=attendance_list, selected_section=selected_section)


@views.route('/attendancetbl', methods=['GET', 'POST'])
def attendancetbl():
    if request.method == 'POST':
        action = request.form.get('action')
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')
        section = request.form.get('section')
        export_format = request.form.get('export_format')

        # Base query
        query = AttendanceDB.query.filter(
            AttendanceDB.date_time_taken <= f"{to_date} 23:59:59"
        )

        # Add date filter only if from_date is provided
        if from_date:
            query = query.filter(AttendanceDB.date_time_taken >= from_date)

        # Add section filter only if it's not None
        if section is not None and section != '0':
            query = query.filter(AttendanceDB.section == section)

        if action == 'delete':
            # Perform deletion of filtered records
            query.delete()
            db.session.commit()
            flash('Attendance records deleted successfully!', 'success')
            return redirect(url_for('views.attendancetbl'))

        query = query.order_by(AttendanceDB.fullName, AttendanceDB.date_time_taken)
        # Execute the query
        attendance_data = query.all()

        if export_format == 'pdf':
            return export_to_pdf(attendance_data, from_date, to_date, section)
        elif export_format == 'csv':
            return export_to_csv(attendance_data, from_date, to_date, section)
        elif export_format == 'summary':
            pdf_buffer = generate_summary_pdf(attendance_data, from_date, to_date)
            response = make_response(pdf_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=summary_{from_date}_to_{to_date}.pdf'
            return response

    else:
        # If no form submission, show all attendance data
        attendance_data = AttendanceDB.query.all()

    return render_template('attendancetbl.html', attendance_data=attendance_data)


def generate_summary_pdf(data, from_date, to_date):
    # Creating a PDF buffer
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Title and Headings
    p.setFont("Helvetica-Bold", 12)
    p.drawString(100, 800, "Attendance Summary")
    p.setFont("Helvetica", 10)
    p.drawString(100, 785, f"Date Range: {from_date} to {to_date}")

    # Initialize the dictionary to store summary data
    student_summary = defaultdict(lambda: {'present': 0, 'absent': 0, 'late': 0})

    # Calculate counts for each student
    for record in data:
        student_summary[record.fullName][record.status.lower()] += 1

    # Set initial y_position for the first student entry
    y_position = 760

    # Writing summary data for each student to PDF
    for student, counts in student_summary.items():
        p.drawString(100, y_position, f"Student: {student}")
        y_position -= 15
        for status, count in counts.items():
            p.drawString(120, y_position, f"{status.title()}: {count}")
            y_position -= 15
        y_position -= 10  # Extra space between students

        # Check for page end to possibly add a new page
        if y_position < 50:
            p.showPage()
            y_position = 760  # Reset y position for the new page

    p.showPage()
    p.save()

    # Move the buffer's pointer to the beginning so the PDF can be returned
    buffer.seek(0)
    return buffer


def export_to_pdf(data, from_date, to_date, section):
    # Sort the data alphabetically based on fullName
    sorted_data = sorted(data, key=lambda x: x.fullName)

    # Create a PDF document
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)

    # Customize the filename based on selected parameters
    filename = f"attendance_{from_date}_{to_date}_{section}.pdf"

    # Create a table with the sorted attendance data
    table_data = [['Student Name', 'Grade', 'Section', 'Date', 'Time', 'Status']]

    current_date = None  # To track the current date and add a separator

    for record in sorted_data:
        record_date = record.date_time_taken.strftime('%Y-%m-%d')

        # Check if the date has changed, and add a separator if it has
        if record_date != current_date:
            table_data.append(['', '', '', '', '', ''])  # Add an empty row as a separator
            current_date = record_date

        table_data.append([
            record.fullName,
            record.grade,
            record.section,
            record.date_time_taken.strftime('%m-%d-%Y'),
            record.date_time_taken.strftime('%I:%M %p'),
            record.status
        ])
    col_widths = [3 * inch, 1 * inch, 1 * inch, 1 * inch, 1 * inch, 1 * inch]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    # Build the PDF
    pdf.build([table])

    # Return the PDF as a response with the customized filename
    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


def export_to_csv(data, from_date, to_date, section):
    # Create a CSV file
    csv_buffer = StringIO()

    # Customize the filename based on selected parameters
    filename = f"attendance_{from_date}_{to_date}_{section}.csv"

    # Write the CSV data using the csv module
    csv_writer = csv.writer(csv_buffer)

    # Write header
    csv_writer.writerow(['Student Name', 'Grade', 'Section', 'Date', 'Time', 'Status'])

    # Write data
    for record in data:
        csv_writer.writerow([
            record.fullName,
            record.grade,
            record.section,
            record.date_time_taken.strftime('%Y-%m-%d'),
            record.date_time_taken.strftime('%I:%M %p'),
            record.status
        ])

    # Reset the buffer position to the beginning
    csv_buffer.seek(0)

    # Return the CSV as a response with the customized filename
    response = make_response(csv_buffer.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


def export_masterlist_pdf(data, from_date, to_date, section):
    # Create a dictionary to store attendance status for each student
    student_attendance = {}

    # Write date headers
    date_range = generate_date_range(from_date, to_date)
    header = "Student Name,Grade,Section," + ",".join(date_range)

    for record in data:
        # Fetch attendance records for the current student and date range
        attendance_records = fetch_attendance_records(record.id, from_date, to_date)

        # Update attendance status for each date
        attendance_status = {date: '-' for date in date_range}

        for attendance_record in attendance_records:
            date_key = attendance_record.date_time_taken.strftime('%m-%d-%Y')

            # Convert "Present" to "Check" and "Absent" to "X"
            if attendance_record.status == 'Present':
                attendance_status[date_key] = 'Check'
            else:
                attendance_status[date_key] = 'X'

        # Append attendance status to the dictionary using the student's name as the key
        student_attendance[record.fullName] = {
            "name": record.fullName,
            "grade": record.grade,
            "section": record.section,
            "status": attendance_status
        }

    # Create a StringIO buffer to store CSV content
    csv_buffer = StringIO()

    # Write CSV header
    csv_buffer.write(header + "\n")

    # Write attendance data to the CSV buffer
    for student_data in student_attendance.values():
        row_data = [
                       student_data["name"],
                       student_data["grade"],
                       student_data["section"]
                   ] + list(student_data["status"].values())

        csv_buffer.write(",".join(map(str, row_data)) + "\n")

    # Create response and serve the CSV file
    filename = f"MasterList_{from_date}_{to_date}_{section}.csv"
    response = make_response(csv_buffer.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


def generate_date_range(start_date, end_date):
    if not start_date or not end_date:
        return []

    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    date_range = [start + timedelta(days=x) for x in range((end - start).days + 1)]
    return [date.strftime('%m-%d-%Y') for date in date_range]


def fetch_attendance_records(student_id, from_date, to_date):
    # Implement your logic to fetch attendance records for the given student_id and date range
    # This could be a database query or another method specific to your application
    # Return a list of attendance records for the student within the specified date range
    return AttendanceDB.query.filter(
        AttendanceDB.id == student_id,
        AttendanceDB.date_time_taken >= from_date,
        AttendanceDB.date_time_taken <= to_date
    ).all()


'''
def capture_and_save_image(folder_path, student_id):
    cam = cv2.VideoCapture(0)

    ret, frame= cam.read()
    time.sleep(2)

    cam.release()

    if ret:
        img_name = f'student_{student_id}.jpg'
        img_path = os.path.join(folder_path, img_name)
        cv2.imwrite(img_path, frame)
        print(f"image {img_name} saved!")

    cv2.destroyAllWindows()
'''


def create_student_folder(full_name, grade, section, current_folder_path=None):
    # Define the base path for the dataset
    base_path = r'/home/fras/facial_recog/dataset'

    # Define the folder name based on the student's information
    folder_name = f"{full_name.replace('_', ' ')}_{grade}_{section}"

    # Create the full path for the student's folder
    folder_path = os.path.join(base_path, section, folder_name)

    try:
        if current_folder_path:
            # Rename the folder if it doesn't exist
            os.rename(current_folder_path, folder_path)
            print(f"Folder renamed successfully: {current_folder_path} to {folder_path}")
        else:
            # Create the folder if it doesn't exist
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created successfully: {folder_path}")
    except Exception as e:
        print(f"Error creating/renaming folder: {e}")

    return folder_path


# student backup
# Function to copy the student's folder to the destination location
def copy_student_folder(source_folder, destination_folder):
    try:
        time.sleep(2)
        # Use shutil.copytree to recursively copy the entire folder
        shutil.copytree(source_folder, os.path.join(destination_folder, os.path.basename(source_folder)))
        print(f"Folder copied successfully to: {destination_folder}")
    except Exception as e:
        print(f"Error copying folder: {e}")


def train_model(section):
    if section == 'Section A':
        model_script_path = '/home/fras/facial_recog/train_modelA.py'
    elif section == 'Section B':
        model_script_path = '/home/fras/facial_recog/train_modelB.py'
    else:
        print(f'cannot find train_model')
        return

    try:
        os.system(f"python {model_script_path}")
    except Exception as e:
        print(f"Error running train_model script: {e}")


@views.route('/manage', methods=['GET', 'POST'])
def manage():
    sections = ["Section A", "Section B"]  # Add all available sections to the list

    if request.method == 'POST':
        selected_section = request.form.get("section")

        if selected_section == "0":
            students = Students.query.all()
        else:
            students = Students.query.filter_by(section=selected_section).all()

        return render_template("manage.html", students=students, sections=sections, selected_section=selected_section)

    # For GET requests, display all students initially
    students = Students.query.all()
    return render_template("manage.html", students=students, sections=sections, selected_section="0")


@views.route('/update/<int:updateid>', methods=['GET', 'POST'])
def update(updateid):
    student = Students.query.get_or_404(updateid)
    current_folder_path = create_student_folder(student.fullName, student.grade, student.section)

    if request.method == 'POST':
        new_lrn = request.form['lrn']
        new_full_name = request.form['fullName']
        new_grade = request.form['grade']
        new_section = request.form['section']

        # USB drive paths
        usb_drive_path = "/media/fras/FRAS/dataset"
        current_usb_section_path = os.path.join(usb_drive_path, student.section.replace("_", " "))
        new_usb_section_path = os.path.join(usb_drive_path, new_section.replace("_", " "))

        # Folder names and paths
        current_folder_name = f"{student.fullName.replace('_', ' ')}_{student.grade}_{student.section}"
        new_folder_name = f"{new_full_name.replace('_', ' ')}_{new_grade}_{new_section}"
        # For USB drive
        source_usb_folder_path = os.path.join(current_usb_section_path, current_folder_name)
        destination_usb_folder_path = os.path.join(new_usb_section_path, new_folder_name)

        # Update student information in the database
        student.lrn = new_lrn
        student.fullName = new_full_name
        student.grade = new_grade
        student.section = new_section

        # Commit the changes to the database
        db.session.commit()

        # Get the new folder path after the update
        new_folder_path = create_student_folder(new_full_name, new_grade, new_section, current_folder_path)
        try:
            # Move folder on USB drive
            if os.path.exists(source_usb_folder_path) and not os.path.exists(destination_usb_folder_path):
                os.makedirs(new_usb_section_path, exist_ok=True)
                shutil.move(source_usb_folder_path, destination_usb_folder_path)
                print(f"USB folder moved successfully from {source_usb_folder_path} to {destination_usb_folder_path}")
            else:
                print("USB source folder does not exist or destination folder already exists. Skipping folder move.")

        except Exception as e:
            print(f"Error moving folder: {e}")

            # train_model(new_section)

        return redirect(url_for('views.manage'))

    return render_template('update.html', student=student)


@views.route('/delete/<int:student_id>', methods=['GET'])
def delete(student_id):
    student = Students.query.get_or_404(student_id)

    # Get the folder path before deletion in the base dataset
    folder_path = create_student_folder(student.fullName, student.grade, student.section)

    # Compute the path of the copied folder on the USB drive
    usb_drive_path = "/media/fras/FRAS/dataset"
    section_folder_name = student.section.replace("_", " ")
    copied_folder_path = os.path.join(usb_drive_path, section_folder_name, os.path.basename(folder_path))

    db.session.delete(student)
    db.session.commit()

    # Call the deletion script for the original folder
    subprocess.run(["sudo", "python3", "/home/fras/website/delete_folder.py", folder_path])

    # Call the deletion script for the copied folder on the USB drive
    subprocess.run(["sudo", "python3", "/home/fras/website/delete_folder.py", copied_folder_path])

    # if student.section == 'Section A':
    # subprocess.run(["sudo", "python3", "/home/fras/facial_recog/train_modelA.py"])
    # elif student.section == 'Section B':
    # subprocess.run(["sudo", "python3", "/home/fras/facial_recog/train_modelB.py"])

    return redirect(url_for('views.manage'))


@views.route('/get_student_counts')
def get_student_counts():
    section_a_count = Students.query.filter_by(section='Section A').count()
    section_b_count = Students.query.filter_by(section='Section B').count()

    return jsonify({
        'sectionACount': section_a_count,
        'sectionBCount': section_b_count
    })


@views.route('/get_total_attendance')
def get_total_attendance():
    # Get the total current day attendance for Section A
    total_attendance_a = AttendanceDB.query.filter(
        AttendanceDB.date_time_taken >= date.today(),
        AttendanceDB.date_time_taken < date.today() + timedelta(days=1),
        AttendanceDB.section == 'Section A'
    ).count()

    # Get the total current day attendance for Section B
    total_attendance_b = AttendanceDB.query.filter(
        AttendanceDB.date_time_taken >= date.today(),
        AttendanceDB.date_time_taken < date.today() + timedelta(days=1),
        AttendanceDB.section == 'Section B'
    ).count()

    return jsonify({
        'totalAttendanceA': total_attendance_a,
        'totalAttendanceB': total_attendance_b
    })


@views.route('/update_attendance/<int:id>', methods=['GET', 'POST'])
def update_attendance(id):
    attendance_record = AttendanceDB.query.get(id)

    if request.method == 'POST':
        # Update the record with the new form data excluding date_time_taken
        attendance_record.fullName = request.form.get('fullName')
        attendance_record.grade = request.form.get('grade')
        attendance_record.section = request.form.get('section')
        attendance_record.status = request.form.get('status')

        # Assuming a 'time' field in the form for the time part of date_time_taken
        submitted_time = request.form.get('time')
        if submitted_time:  # Check if time was actually submitted to prevent errors
            # Parse the submitted time and update only the time part of date_time_taken
            new_time = datetime.strptime(submitted_time, '%H:%M').time()
            current_date = attendance_record.date_time_taken.date()
            attendance_record.date_time_taken = datetime.combine(current_date, new_time)

        # Commit the changes to the database
        db.session.commit()

        # Redirect to the attendance table page after updating
        return redirect(url_for('views.attendancetbl'))

    return render_template('updateAttendance.html', attendance_record=attendance_record)


@views.route('/delete_attendance/<int:id>', methods=['GET'])
def delete_attendance(id):
    attendance_record = AttendanceDB.query.get_or_404(id)

    # Delete the attendance record
    db.session.delete(attendance_record)
    db.session.commit()

    # Redirect to the attendance table page after deletion
    return redirect(url_for('views.attendancetbl'))


def get_schedule_data():
    return session.get('schedule_data', {})
    return session.get('schedule_dataB', {})


@views.route('/schedule')
def schedule():
    # Initialize schedule_data and schedule_dataB from session or config files
    if 'schedule_data' not in session or 'schedule_dataB' not in session:
        config = configparser.ConfigParser()
        config.read('/home/fras/website/config.ini')
        configB = configparser.ConfigParser()
        configB.read('/home/fras/website/configB.ini')
        session['schedule_data'] = {
            'present_time': config.get('AttendanceSettings', 'present_time', fallback='Not Set'),
            'late_time': config.get('AttendanceSettings', 'late_time', fallback='Not Set'),
            'absent_time': config.get('AttendanceSettings', 'absent_time', fallback='Not Set')
        }
        session['schedule_dataB'] = {
            'present_timeB': configB.get('AttendanceSettingsB', 'present_timeB', fallback='Not Set'),
            'late_timeB': configB.get('AttendanceSettingsB', 'late_timeB', fallback='Not Set'),
            'absent_timeB': configB.get('AttendanceSettingsB', 'absent_timeB', fallback='Not Set')
        }
        session.modified = True

    return render_template("sched.html", schedule_data=session['schedule_data'],
                           schedule_dataB=session['schedule_dataB'])


@views.route('/update_config', methods=['GET', 'POST'])
def update_config():
    if request.method == 'POST':
        present_time = request.form.get('present_time')
        late_time = request.form.get('late_time')
        absent_time = request.form.get('absent_time')

        # Update config.ini with the new values for Section A
        config = configparser.ConfigParser()
        config.read('/home/fras/website/config.ini')
        config['AttendanceSettings']['present_time'] = present_time
        config['AttendanceSettings']['late_time'] = late_time
        config['AttendanceSettings']['absent_time'] = absent_time

        with open('/home/fras/website/config.ini', 'w') as configfile:
            config.write(configfile)

        # Read the values directly for Section B
        configB = configparser.ConfigParser()
        configB.read('/home/fras/website/configB.ini')
        session['schedule_dataB'] = {
            'present_timeB': configB['AttendanceSettingsB']['present_timeB'],
            'late_timeB': configB['AttendanceSettingsB']['late_timeB'],
            'absent_timeB': configB['AttendanceSettingsB']['absent_timeB']
        }

        # Pass both schedule_data and schedule_dataB to sched.html and render the template
        session['schedule_data'] = {
            'present_time': present_time,
            'late_time': late_time,
            'absent_time': absent_time
        }
        session.modified = True
        return render_template('sched.html', schedule_data=session.get('schedule_data', {}),
                               schedule_dataB=session.get('schedule_dataB', {}))

    return render_template('SchedA.html')


@views.route('/updateconfig', methods=['GET', 'POST'])
def updateconfig():
    if request.method == 'POST':
        present_timeB = request.form.get('present_timeB')
        late_timeB = request.form.get('late_timeB')
        absent_timeB = request.form.get('absent_timeB')

        # Update configB.ini with the new values for Section B
        configB = configparser.ConfigParser()
        configB.read('/home/fras/website/configB.ini')
        configB['AttendanceSettingsB']['present_timeB'] = present_timeB
        configB['AttendanceSettingsB']['late_timeB'] = late_timeB
        configB['AttendanceSettingsB']['absent_timeB'] = absent_timeB

        with open('/home/fras/website/configB.ini', 'w') as configfile:
            configB.write(configfile)

        # Read the values directly for Section A
        config = configparser.ConfigParser()
        config.read('/home/fras/website/config.ini')
        session['schedule_data'] = {
            'present_time': config['AttendanceSettings']['present_time'],
            'late_time': config['AttendanceSettings']['late_time'],
            'absent_time': config['AttendanceSettings']['absent_time']
        }

        # Pass both schedule_data and schedule_dataB to sched.html and render the template
        session['schedule_dataB'] = {
            'present_timeB': present_timeB,
            'late_timeB': late_timeB,
            'absent_timeB': absent_timeB
        }
        session.modified = True
        return render_template('sched.html', schedule_data=session.get('schedule_data', {}),
                               schedule_dataB=session.get('schedule_dataB', {}))

    return render_template('SchedB.html')