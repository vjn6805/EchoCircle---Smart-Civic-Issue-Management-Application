from flask import Flask,render_template,request, redirect, session, url_for, flash,send_from_directory,jsonify,send_file
import bcrypt
import os
from werkzeug.utils import secure_filename
import csv, io, datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import google.generativeai as genai
from datetime import datetime, timedelta
from collections import Counter


from config import SECRET_KEY,GEMINI_API_KEY
from utils.db_connection import get_db_connection
from utils.geolocation import get_city_coordinates

app=Flask(__name__)
app.secret_key=SECRET_KEY
genai.configure(api_key=GEMINI_API_KEY)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

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


@app.route('/user/dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch user city and name
    cursor.execute("SELECT name, city FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    user_name = user['name'] if user else 'User'
    user_city = user['city'] if user else 'Ahmedabad'
    
    #fetch number of resolved issues
    cursor.execute("SELECT Count(*) from issues where status='Resolved' and city = %s",(user_city,))
    total_resolved=cursor.fetchone()['Count(*)']

    # Get coordinates of city dynamically
    lat, lon = get_city_coordinates(user_city)

    # Fetch issues for map (include full details for modal)
    cursor.execute("""
        SELECT 
            i.issue_id, 
            i.title, 
            i.description,
            i.category, 
            i.severity,
            i.status, 
            i.city,
            i.latitude, 
            i.longitude, 
            i.upvotes, 
            i.image_path,
            CASE WHEN u.user_id IS NOT NULL THEN 1 ELSE 0 END AS user_voted
        FROM issues i
        LEFT JOIN upvotes u 
            ON i.issue_id = u.issue_id AND u.user_id = %s
        WHERE i.city = %s AND i.status NOT IN ('Resolved', 'Rejected')
        ORDER BY i.upvotes DESC
    """, (user_id, user_city))
    issues = cursor.fetchall()

    # Fetch feed posts (all issues from same city for social feed)
    cursor.execute("""
        SELECT 
            i.issue_id,
            i.title,
            i.description,
            i.category,
            i.severity,
            i.status,
            i.image_path,
            i.created_at,
            u.name AS author_name,
            (SELECT COUNT(*) FROM likes WHERE issue_id = i.issue_id) AS like_count,
            (SELECT COUNT(*) FROM comments WHERE issue_id = i.issue_id) AS comment_count,
            CASE WHEN l.user_id IS NOT NULL THEN 1 ELSE 0 END AS user_liked
        FROM issues i
        JOIN users u ON i.user_id = u.user_id
        LEFT JOIN likes l ON i.issue_id = l.issue_id AND l.user_id = %s
        WHERE i.city = %s
        ORDER BY i.created_at DESC
        LIMIT 20
    """, (user_id, user_city))
    feed_posts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/user_dashboard.html',
        issues=issues,
        name=user_name,
        city=user_city,
        lat=lat,
        lon=lon,
        total_resolved=total_resolved
    )

@app.route('/user/feed')
def user_feed():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch user city and name
    cursor.execute("SELECT name, city FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    user_name = user['name'] if user else 'User'
    user_city = user['city'] if user else 'Ahmedabad'

    # Fetch feed posts (all issues from same city except current user's posts)
    cursor.execute("""
        SELECT 
            i.issue_id,
            i.title,
            i.description,
            i.category,
            i.severity,
            i.status,
            i.image_path,
            i.created_at,
            u.name AS author_name,
            (SELECT COUNT(*) FROM likes WHERE issue_id = i.issue_id) AS like_count,
            (SELECT COUNT(*) FROM comments WHERE issue_id = i.issue_id) AS comment_count,
            CASE WHEN l.user_id IS NOT NULL THEN 1 ELSE 0 END AS user_liked
        FROM issues i
        JOIN users u ON i.user_id = u.user_id
        LEFT JOIN likes l ON i.issue_id = l.issue_id AND l.user_id = %s
        WHERE i.city = %s AND i.user_id != %s
        ORDER BY i.created_at DESC
        LIMIT 50
    """, (user_id, user_city, user_id))
    feed_posts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/user_feed.html',
        feed_posts=feed_posts,
        name=user_name,
        city=user_city
    )

@app.route('/upvote/<int:issue_id>', methods=['POST'])
def upvote_issue(issue_id):
    if 'user_id' not in session:
        return {'success': False, 'message': 'Not logged in'}, 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if user already voted
        cursor.execute("SELECT * FROM upvotes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
        if cursor.fetchone():
            return {'success': False, 'message': 'Already voted'}, 400
        
        # Add vote record
        cursor.execute("INSERT INTO upvotes (user_id, issue_id) VALUES (%s, %s)", (user_id, issue_id))
        
        # Update upvotes
        cursor.execute("UPDATE issues SET upvotes = upvotes + 1 WHERE issue_id = %s", (issue_id,))
        
        # Get updated upvotes count
        cursor.execute("SELECT upvotes FROM issues WHERE issue_id = %s", (issue_id,))
        result = cursor.fetchone()
        
        conn.commit()
        return {'success': True, 'upvotes': result['upvotes']}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': str(e)}, 500
    finally:
        cursor.close()
        conn.close()

@app.route('/user/my_issues')
def my_issues():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch all issues reported by this user with accurate upvote counts from upvotes table
        cursor.execute("""
            SELECT 
                i.issue_id,
                i.user_id,
                i.title,
                i.description,
                i.category,
                i.severity,
                i.status,
                i.image_path,
                i.created_at,
                i.city,
                i.latitude,
                i.longitude,
                COALESCE(u.cnt, 0) AS upvotes
            FROM issues i
            LEFT JOIN (
                SELECT issue_id, COUNT(*) AS cnt
                FROM upvotes
                GROUP BY issue_id
            ) u ON i.issue_id = u.issue_id
            WHERE i.user_id = %s
            ORDER BY i.created_at DESC
        """, (user_id,))
        issues = cursor.fetchall()

        # Fetch updates for each issue (grouped by issue_id)
        issue_updates = {}
        for issue in issues:
            cursor.execute("""
                SELECT status, comment, updated_by, timestamp
                FROM issue_updates
                WHERE issue_id = %s
                ORDER BY timestamp ASC
            """, (issue['issue_id'],))
            issue_updates[issue['issue_id']] = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'user/user_my_issues.html',
        issues=issues,
        issue_updates=issue_updates
    )

@app.route('/user/report', methods=['GET', 'POST'])
def report_issue():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        severity = request.form['severity']
        city = request.form['city']
        latitude = request.form['latitude']
        longitude = request.form['longitude']

        image_path = None
        # Handle image upload if provided
        if 'image' in request.files:
            image = request.files['image']
            if image.filename != '':
                # Create directory if it doesn't exist
                os.makedirs('uploads/issue_images', exist_ok=True)
                filename = secure_filename(image.filename)
                image_path = os.path.join('uploads/issue_images', filename)
                image.save(image_path)

        cursor.execute("""
            INSERT INTO issues 
            (user_id, title, description, category, severity, image_path, latitude, longitude, city, status, upvotes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending', 0)
        """, (user_id, title, description, category, severity, image_path, latitude, longitude, city))

        conn.commit()
        cursor.close()
        conn.close()
        flash('Issue reported successfully!', 'success')
        return redirect(url_for('user_dashboard'))

    cursor.close()
    conn.close()
    return render_template('user/report_issue.html')

@app.route('/like_post/<int:issue_id>', methods=['POST'])
def like_post(issue_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if user already liked
        cursor.execute("SELECT * FROM likes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
        existing_like = cursor.fetchone()
        
        if existing_like:
            # Unlike
            cursor.execute("DELETE FROM likes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
            action = 'unliked'
        else:
            # Like
            cursor.execute("INSERT INTO likes (user_id, issue_id) VALUES (%s, %s)", (user_id, issue_id))
            action = 'liked'
        
        # Get updated like count
        cursor.execute("SELECT COUNT(*) as count FROM likes WHERE issue_id = %s", (issue_id,))
        like_count = cursor.fetchone()['count']
        
        conn.commit()
        return jsonify({'success': True, 'action': action, 'like_count': like_count})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/add_comment/<int:issue_id>', methods=['POST'])
def add_comment(issue_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    comment_text = request.json.get('comment')
    
    if not comment_text or not comment_text.strip():
        return jsonify({'success': False, 'message': 'Comment cannot be empty'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            INSERT INTO comments (issue_id, user_id, comment_text) 
            VALUES (%s, %s, %s)
        """, (issue_id, user_id, comment_text.strip()))
        
        # Get the new comment with user name
        cursor.execute("""
            SELECT c.comment_text, c.created_at, u.name 
            FROM comments c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.comment_id = %s
        """, (cursor.lastrowid,))
        new_comment = cursor.fetchone()
        
        conn.commit()
        return jsonify({'success': True, 'comment': new_comment})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_comments/<int:issue_id>')
def get_comments(issue_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT c.comment_text, c.created_at, u.name 
            FROM comments c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.issue_id = %s
            ORDER BY c.created_at DESC
        """, (issue_id,))
        comments = cursor.fetchall()
        
        return jsonify({'success': True, 'comments': comments})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# Rout to serve uploaded images
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch admin details
    cursor.execute("SELECT name, city, department FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    if not admin:
        cursor.close()
        conn.close()
        return redirect(url_for('login_admin'))

    admin_name = admin['name']
    admin_city = admin['city']
    admin_dept = admin['department']

    # Fetch categorized issues by severity, sorted by upvotes
    severities = ['Critical', 'Moderate', 'Minor']
    categorized_issues = {}

    for severity in severities:
        cursor.execute("""
            SELECT 
                i.issue_id, i.title, i.category, i.severity, i.status, i.upvotes,
                i.city, i.created_at, i.image_path,
                u.name AS reported_by,
                t.name AS technician_name
            FROM issues i
            LEFT JOIN users u ON i.user_id = u.user_id
            LEFT JOIN technicians t ON i.technician_id = t.technician_id
            WHERE i.city = %s AND i.category = %s AND i.severity = %s AND i.status != 'Resolved'
            ORDER BY i.upvotes DESC
        """, (admin_city, admin_dept, severity))
        categorized_issues[severity] = cursor.fetchall()

    # Count stats for summary cards
    cursor.execute("""
        SELECT 
            SUM(status = 'Pending') AS pending,
            SUM(status = 'In Progress') AS in_progress,
            SUM(status = 'Resolved') AS resolved
        FROM issues
        WHERE city = %s AND category = %s
    """, (admin_city, admin_dept))
    stats = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        'admin/admin_dashboard.html',
        admin_name=admin_name,
        city=admin_city,
        department=admin_dept,
        issues=categorized_issues,
        stats=stats
    )
    
@app.route('/admin/issue_data/<int:issue_id>')
def get_issue_data(issue_id):
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get issue
    cursor.execute("""
        SELECT i.*, u.name AS reported_by 
        FROM issues i 
        LEFT JOIN users u ON i.user_id = u.user_id
        WHERE i.issue_id = %s
    """, (issue_id,))
    issue = cursor.fetchone()

    if not issue:
        return jsonify({'success': False, 'message': 'Issue not found'})

    # Get updates
    cursor.execute("""
        SELECT status, comment, updated_by, timestamp 
        FROM issue_updates 
        WHERE issue_id = %s 
        ORDER BY timestamp DESC
    """, (issue_id,))
    updates = cursor.fetchall()

    # Get technicians of same city and department
    cursor.execute("""
        SELECT technician_id, name 
        FROM technicians 
        WHERE city = %s AND department = %s
    """, (issue['city'], issue['category']))
    technicians = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({'success': True, 'issue': issue, 'updates': updates, 'technicians': technicians})


@app.route('/admin/update_issue/<int:issue_id>', methods=['POST'])
def update_issue(issue_id):
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    data = request.get_json()
    status = data.get('status')
    technician_id = data.get('technician_id')
    comment = data.get('comment', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            UPDATE issues 
            SET status = %s, technician_id = %s 
            WHERE issue_id = %s
        """, (status, technician_id or None, issue_id))

        cursor.execute("""
            INSERT INTO issue_updates (issue_id, status, comment, updated_by) 
            VALUES (%s, %s, %s, 'Admin')
        """, (issue_id, status, comment))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        conn.close()
        

@app.route('/admin/technicians')
def admin_technicians():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch admin city & department
    cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    admin_city = admin['city']
    admin_dept = admin['department']

    # Fetch all technicians for same city & department
    cursor.execute("""
        SELECT t.*, 
               (SELECT COUNT(*) FROM issues WHERE technician_id = t.technician_id) AS assigned_issues
        FROM technicians t
        WHERE t.city = %s AND t.department = %s
        ORDER BY t.created_at DESC
    """, (admin_city, admin_dept))
    technicians = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin/admin_technicians.html', technicians=technicians, city=admin_city, department=admin_dept)


@app.route('/admin/technician/add', methods=['POST'])
def add_technician():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    city = request.form.get('city')
    department = request.form.get('department')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO technicians (name, email, phone, city, department)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, email, phone, city, department))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Technician added successfully!", "success")
    return redirect(url_for('admin_technicians'))


@app.route('/admin/technician/delete/<int:tech_id>', methods=['POST'])
def delete_technician(tech_id):
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM technicians WHERE technician_id = %s", (tech_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Technician removed successfully!", "success")
    return redirect(url_for('admin_technicians'))

@app.route('/admin/analytics')
def admin_analytics():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch admin details
    cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    city = admin['city']
    department = admin['department']

    # 1️⃣ Issues by Status
    cursor.execute("""
        SELECT status, COUNT(*) AS count 
        FROM issues 
        WHERE city = %s AND category = %s 
        GROUP BY status
    """, (city, department))
    status_data = cursor.fetchall()

    # 2️⃣ Issues by Category
    cursor.execute("""
        SELECT category, COUNT(*) AS count 
        FROM issues 
        WHERE city = %s
        GROUP BY category
    """, (city,))
    category_data = cursor.fetchall()

    # 3️⃣ Issue Trends (last 10 days)
    cursor.execute("""
        SELECT DATE(created_at) AS date, COUNT(*) AS count
        FROM issues
        WHERE city = %s
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at) DESC
        LIMIT 10
    """, (city,))
    trend_data = cursor.fetchall()

    # 4️⃣ Top Technicians
    cursor.execute("""
        SELECT t.name, COUNT(i.issue_id) AS resolved_count
        FROM technicians t
        LEFT JOIN issues i ON t.technician_id = i.technician_id 
        AND i.status = 'Resolved'
        WHERE t.city = %s AND t.department = %s
        GROUP BY t.technician_id
        ORDER BY resolved_count DESC
        LIMIT 5
    """, (city, department))
    tech_data = cursor.fetchall()

    # 5️⃣ Leaderboard Data
    cursor.execute("""
        SELECT t.name, 
               COUNT(CASE WHEN i.status = 'Resolved' THEN 1 END) AS resolved_count,
               COUNT(CASE WHEN i.status = 'In Progress' THEN 1 END) AS in_progress_count,
               COUNT(i.issue_id) AS total_assigned,
               ROUND(AVG(CASE WHEN i.status = 'Resolved' THEN 
                   TIMESTAMPDIFF(HOUR, i.created_at, i.updated_at) END), 1) AS avg_resolution_time
        FROM technicians t
        LEFT JOIN issues i ON t.technician_id = i.technician_id
        WHERE t.city = %s AND t.department = %s
        GROUP BY t.technician_id, t.name
        ORDER BY resolved_count DESC, avg_resolution_time ASC
        LIMIT 10
    """, (city, department))
    leaderboard_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'admin/admin_analytics.html',
        city=city,
        department=department,
        status_data=status_data,
        category_data=category_data,
        trend_data=trend_data,
        tech_data=tech_data,
        leaderboard_data=leaderboard_data
    )

@app.route('/admin/export', methods=['GET'])
def admin_export():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    admin_id = session['admin_id']
    export_type = request.args.get('type', 'csv')
    status = request.args.get('status')
    category = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    city = admin['city']
    department = admin['department']

    # Build query dynamically based on filters
    query = """
        SELECT issue_id, title, category, status, severity, upvotes, city, created_at
        FROM issues
        WHERE city = %s AND category = %s
    """
    params = [city, department]

    if status:
        query += " AND status = %s"
        params.append(status)
    if start_date and end_date:
        query += " AND DATE(created_at) BETWEEN %s AND %s"
        params.extend([start_date, end_date])

    cursor.execute(query, tuple(params))
    issues = cursor.fetchall()
    cursor.close()
    conn.close()

    if not issues:
        return jsonify({'success': False, 'message': 'No issues found for selected filters.'})

    if export_type == 'csv':
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=issues[0].keys())
        writer.writeheader()
        writer.writerows(issues)
        output.seek(0)

        filename = f"issues_{city}_{department}_{datetime.date.today()}.csv"
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    elif export_type == 'pdf':
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(30, 750, f"Issue Report - {city} ({department})")
        p.setFont("Helvetica", 10)

        y = 720
        for i, issue in enumerate(issues, start=1):
            text = f"{i}. {issue['title']} | {issue['category']} | {issue['status']} | {issue['severity']} | {issue['created_at'].strftime('%Y-%m-%d')}"
            p.drawString(30, y, text)
            y -= 15
            if y < 50:
                p.showPage()
                y = 750

        p.save()
        buffer.seek(0)

        filename = f"Issues_Report_{city}_{department}_{datetime.date.today()}.pdf"
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

    return jsonify({'success': False, 'message': 'Invalid export type.'})

@app.route('/admin/heatmap_data')
def admin_heatmap_data():
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    city = admin['city']
    dept = admin['department']

    cursor.execute("""
        SELECT latitude, longitude, severity, status
        FROM issues
        WHERE city = %s AND category = %s AND status NOT IN ('Resolved', 'Rejected')
    """, (city, dept))
    issues = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({'success': True, 'issues': issues})

@app.route('/admin/weekly_summary')
def admin_weekly_summary():
    if 'admin_id' not in session:
        return redirect(url_for('login_admin'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 Fetch admin details (city & department scope)
    cursor.execute("SELECT city, department, name FROM admins WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()
    city, department, admin_name = admin['city'], admin['department'], admin['name']

    one_week_ago = datetime.now() - timedelta(days=7)
    two_weeks_ago = datetime.now() - timedelta(days=14)

    # 🔹 Fetch issues reported in the last 7 days
    cursor.execute("""
        SELECT issue_id, title, status, category, severity,
               TIMESTAMPDIFF(HOUR, created_at, updated_at) AS resolution_time,
               created_at
        FROM issues
        WHERE city = %s AND category = %s AND created_at >= %s
    """, (city, department, one_week_ago))
    issues = cursor.fetchall()

    # 🔹 Fetch data for the previous week (to compare trends)
    cursor.execute("""
        SELECT status, TIMESTAMPDIFF(HOUR, created_at, updated_at) AS resolution_time
        FROM issues
        WHERE city = %s AND category = %s 
          AND created_at BETWEEN %s AND %s
    """, (city, department, two_weeks_ago, one_week_ago))
    previous_week = cursor.fetchall()

    cursor.close()
    conn.close()
    total = len(issues)
    resolved = sum(1 for i in issues if i['status'] == 'Resolved')
    in_progress = sum(1 for i in issues if i['status'] == 'In Progress')
    pending = sum(1 for i in issues if i['status'] == 'Pending')
    rejected = sum(1 for i in issues if i['status'] == 'Rejected')

    # Resolution statistics
    resolved_times = [i['resolution_time'] for i in issues if i['resolution_time']]
    avg_res_time = round(sum(resolved_times) / len(resolved_times), 2) if resolved_times else 0

    prev_resolved_times = [i['resolution_time'] for i in previous_week if i['resolution_time']]
    prev_avg_time = round(sum(prev_resolved_times) / len(prev_resolved_times), 2) if prev_resolved_times else 0

    # Calculate improvement or regression in resolution speed
    resolution_trend = "improved" if avg_res_time < prev_avg_time else "slowed down"

    # Severity and category distribution
    from collections import Counter
    severity_dist = Counter([i['severity'] for i in issues])
    top_category = Counter([i['category'] for i in issues]).most_common(1)
    top_severity = Counter([i['severity'] for i in issues]).most_common(1)

    resolution_rate = round((resolved / total) * 100, 1) if total > 0 else 0

    try:
        prompt = f"""
        You are an AI analyst that generates weekly performance summaries for municipal service departments.

        Generate a professional, insightful weekly report for the **{department} Department** in **{city}**.
        Summarize this week's operational statistics, identify patterns, and give brief improvement suggestions.

        ### Weekly Data Overview:
        - Total issues: {total}
        - Resolved: {resolved}
        - In Progress: {in_progress}
        - Pending: {pending}
        - Rejected: {rejected}
        - Resolution Rate: {resolution_rate}%
        - Average Resolution Time: {avg_res_time} hours (last week: {prev_avg_time} hours → {resolution_trend})
        - Top Category: {top_category[0][0] if top_category else 'N/A'}
        - Severity Distribution: {dict(severity_dist)}

        ### Report Requirements:
        - Start with a summary paragraph highlighting total activity and performance.
        - Then mention notable improvements or challenges.
        - If resolution time worsened, suggest prioritizing resource allocation.
        - End with an optimistic outlook or plan-of-action tone.
        - Keep it under 180 words, factual and analytical.
        """

        model = genai.GenerativeModel("gemini-2.5-flash")  
        response = model.generate_content(prompt)
        summary_text = response.text.strip() if hasattr(response, 'text') else "(No summary generated.)"

    except Exception as e:
        summary_text = f"(AI Summary unavailable due to API error: {str(e)})"

    return render_template(
        'admin/admin_weekly_summary.html',
        summary_text=summary_text,
        total=total,
        resolved=resolved,
        in_progress=in_progress,
        pending=pending,
        rejected=rejected,
        avg_res_time=avg_res_time,
        prev_avg_time=prev_avg_time,
        resolution_trend=resolution_trend,
        resolution_rate=resolution_rate,
        severity_dist=severity_dist,
        top_category=top_category[0][0] if top_category else None,
        top_severity=top_severity[0][0] if top_severity else None,
        city=city,
        department=department,
        admin_name=admin_name
    )



@app.route('/technician/dashboard')
def technician_dashboard():
    if 'technician_id' not in session:
        return redirect(url_for('login_technician'))

    technician_id = session['technician_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ Fetch technician details
    cursor.execute("SELECT name, city FROM technicians WHERE technician_id = %s", (technician_id,))
    tech = cursor.fetchone()
    if not tech:
        cursor.close()
        conn.close()
        return "Technician not found", 404

    technician_name = tech['name']
    city = tech['city']

    # ✅ Fetch all issues assigned to this technician (for stats)
    cursor.execute("""
        SELECT issue_id, title, category, severity, status, latitude, longitude, description
        FROM issues
        WHERE technician_id = %s
        ORDER BY 
            CASE 
                WHEN status = 'Pending' THEN 1
                WHEN status = 'In Progress' THEN 2
                WHEN status = 'Resolved' THEN 3
                ELSE 4
            END, created_at DESC
    """, (technician_id,))
    all_issues = cursor.fetchall()
    
    # ✅ Fetch only non-resolved issues for the table
    cursor.execute("""
        SELECT issue_id, title, category, severity, status, latitude, longitude, description
        FROM issues
        WHERE technician_id = %s AND status != 'Resolved'
        ORDER BY 
            CASE 
                WHEN status = 'Pending' THEN 1
                WHEN status = 'In Progress' THEN 2
                ELSE 3
            END, created_at DESC
    """, (technician_id,))
    issues = cursor.fetchall()

    # ✅ Compute issue statistics (using all issues)
    stats = {
        'pending': sum(1 for i in all_issues if i['status'] == 'Pending'),
        'in_progress': sum(1 for i in all_issues if i['status'] == 'In Progress'),
        'resolved': sum(1 for i in all_issues if i['status'] == 'Resolved')
    }

    # ✅ Default map center (average of all assigned issue coordinates or fallback city)
    latitudes = [float(i['latitude']) for i in all_issues if i['latitude']]
    longitudes = [float(i['longitude']) for i in all_issues if i['longitude']]
    lat = sum(latitudes) / len(latitudes) if latitudes else 23.0225  # Ahmedabad fallback
    lon = sum(longitudes) / len(longitudes) if longitudes else 72.5714

    cursor.close()
    conn.close()

    return render_template(
        'technician/technician_dashboard.html',
        technician_name=technician_name,
        city=city,
        issues=issues,
        all_issues=all_issues,
        stats=stats,
        lat=lat,
        lon=lon
    )
    
@app.route('/technician/issue_data/<int:issue_id>')
def technician_issue_data(issue_id):
    if 'technician_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    technician_id = session['technician_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT i.*, u.name AS reported_by
        FROM issues i
        JOIN users u ON i.user_id = u.user_id
        WHERE i.issue_id = %s AND i.technician_id = %s
    """, (issue_id, technician_id))
    issue = cursor.fetchone()

    cursor.close()
    conn.close()

    if not issue:
        return jsonify({'success': False, 'message': 'Issue not found'}), 404

    return jsonify({'success': True, 'issue': issue})

@app.route('/technician/update_issue/<int:issue_id>', methods=['POST'])
def technician_update_issue(issue_id):
    if 'technician_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    technician_id = session['technician_id']
    status = request.form.get('status')
    comment = request.form.get('comment')
    image = request.files.get('image')

    image_path = None
    if image:
        filename = secure_filename(image.filename)
        upload_folder = os.path.join('static', 'uploads', 'issues')
        os.makedirs(upload_folder, exist_ok=True)
        image_path = os.path.join(upload_folder, filename)
        image.save(image_path)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get technician name
    cursor.execute("SELECT name FROM technicians WHERE technician_id = %s", (technician_id,))
    tech = cursor.fetchone()
    tech_name = tech['name'] if tech else 'Technician'

    # ✅ Update issue table
    cursor.execute("""
        UPDATE issues 
        SET status = %s, image_path = COALESCE(%s, image_path), updated_at = NOW()
        WHERE issue_id = %s AND technician_id = %s
    """, (status, image_path, issue_id, technician_id))

    # ✅ Log update in issue_updates table
    cursor.execute("""
    INSERT INTO issue_updates (issue_id, status, comment, updated_by, timestamp)
    VALUES (%s, %s, %s, %s, NOW())
""", (issue_id, status, comment, 'Technician'))


    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'success': True, 'message': 'Issue updated successfully'})

@app.route('/technician/issues_by_status/<status>')
def technician_issues_by_status(status):
    if 'technician_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    technician_id = session['technician_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        FROM issues
        SELECT issue_id, title, category, severity, status, created_at
        WHERE technician_id = %s AND status = %s
        ORDER BY created_at DESC
    """, (technician_id, status))
    issues = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({'success': True, 'issues': issues})









# ------------------------- MAIN ENTRY POINT -------------------------
if __name__=='__main__':
    app.run(debug=True)