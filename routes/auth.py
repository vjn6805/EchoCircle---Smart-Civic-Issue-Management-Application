from flask import render_template, request, redirect, session, url_for, flash
import bcrypt
from utils.db_connection import get_db_connection

def register_auth_routes(app):
    @app.route('/')
    def landing():
        return render_template('landing.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            phone = request.form['phone']
            city = request.form['city']

            hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO users (name, email, password, phone, city)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, email, hashed_pw, phone, city))
                conn.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for('login_user'))
            except Exception as e:
                print("Error:", e)
                flash("Error: Email already exists or invalid data.", "danger")
            finally:
                cursor.close()
                conn.close()

        return render_template('register.html')

    @app.route('/login_user', methods=['GET', 'POST'])
    def login_user():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()

            if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                session['user_id'] = user['user_id']
                session['role'] = 'user'
                return redirect(url_for('user_dashboard'))
            else:
                flash("Invalid email or password.", "danger")

            cursor.close()
            conn.close()

        return render_template('login_user.html')

    @app.route('/login_admin', methods=['GET', 'POST'])
    def login_admin():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM admins WHERE email=%s", (email,))
            admin = cursor.fetchone()

            if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password'].encode('utf-8')):
                session['admin_id'] = admin['admin_id']
                session['role'] = 'admin'
                return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid credentials.", "danger")

            cursor.close()
            conn.close()

        return render_template('login_admin.html')

    @app.route('/login_technician', methods=['GET', 'POST'])
    def login_technician():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM technicians WHERE email=%s", (email,))
            tech = cursor.fetchone()

            if tech and bcrypt.checkpw(password.encode('utf-8'), tech['password'].encode('utf-8')):
                session['technician_id'] = tech['technician_id']
                session['role'] = 'technician'
                return redirect(url_for('technician_dashboard'))
            else:
                flash("Invalid credentials.", "danger")

            cursor.close()
            conn.close()

        return render_template('login_technician.html')

    @app.route('/logout')
    def logout():
        session.clear()
        flash("Logged out successfully.", "info")
        return redirect(url_for('landing'))