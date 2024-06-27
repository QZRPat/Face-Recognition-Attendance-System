from flask import Blueprint, request, redirect, url_for, flash, render_template
from .models import Students
from . import db
from .views import create_student_folder, copy_student_folder, train_model
from .capture import capture_and_save_image
import os
import subprocess

import signal

registration_bp = Blueprint('registration', __name__)

@registration_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        lrn = request.form.get('lrn')
        full_name = request.form.get("fullName")
        grade = request.form.get("grade")
        section = request.form.get("section")
        
        # Check if LRN already exists
        existing_student = Students.query.filter_by(lrn=lrn).first()
        if existing_student:
            # Flash an error message
            flash('LRN already exists. Please use a different LRN.', 'danger')
            return redirect(url_for('registration.register'))

        # Create a new student and add it to the database
        new_student = Students(lrn=lrn, fullName=full_name, grade=grade, section=section)
        db.session.add(new_student)
        db.session.commit()

        # Commit changes to the database to get the new student's ID
        db.session.refresh(new_student)

        # Create the student's folder
        folder_path = create_student_folder(full_name, grade, section)
        # Capture an Image using OpenCV
        student_id = new_student.id
        capture_script_path = "/home/fras/website/capture.py"  # Update this path
        subprocess.run(['python3', capture_script_path, folder_path, str(student_id)], check=True)



        # Train the corresponding model based on the section
        #train_model(section)

        # Copy the folder to the USB flash drive based on the section
        usb_drive_path = "/media/fras/FRAS/dataset"
        destination_folder = os.path.join(usb_drive_path, section.replace("_", " "))
        copy_student_folder(folder_path, destination_folder)
        # Redirect to a different page after successful registration
        flash('Student successfully registered!', 'success')

        return redirect(url_for('registration.register'))
    return render_template("register.html")
    
