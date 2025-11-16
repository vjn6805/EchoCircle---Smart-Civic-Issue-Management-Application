from flask import render_template, request, redirect, session, url_for, flash, jsonify, send_file
import csv, io, datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import google.generativeai as genai
from datetime import datetime, timedelta
from collections import Counter
import bcrypt
from utils.db_connection import get_db_connection
from utils.geolocation import get_city_coordinates
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

def register_admin_routes(app):
    @app.route('/admin/dashboard')
    def admin_dashboard():
        if 'admin_id' not in session:
            return redirect(url_for('login_admin'))

        admin_id = session['admin_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT name, city, department FROM admins WHERE admin_id = %s", (admin_id,))
        admin = cursor.fetchone()
        if not admin:
            cursor.close()
            conn.close()
            return redirect(url_for('login_admin'))

        admin_name = admin['name']
        admin_city = admin['city']
        admin_dept = admin['department']

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

        lat, lon = get_city_coordinates(admin_city)

        return render_template(
            'admin/admin_dashboard.html',
            admin_name=admin_name,
            city=admin_city,
            department=admin_dept,
            issues=categorized_issues,
            stats=stats,
            lat=lat,
            lon=lon
        )
        
    @app.route('/admin/issue_data/<int:issue_id>')
    def get_issue_data(issue_id):
        if 'admin_id' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'})

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT i.*, u.name AS reported_by 
            FROM issues i 
            LEFT JOIN users u ON i.user_id = u.user_id
            WHERE i.issue_id = %s
        """, (issue_id,))
        issue = cursor.fetchone()

        if not issue:
            return jsonify({'success': False, 'message': 'Issue not found'})

        cursor.execute("""
            SELECT status, comment, updated_by, timestamp 
            FROM issue_updates 
            WHERE issue_id = %s 
            ORDER BY timestamp DESC
        """, (issue_id,))
        updates = cursor.fetchall()

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

        cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
        admin = cursor.fetchone()
        admin_city = admin['city']
        admin_dept = admin['department']

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
        password = request.form.get('password')
        city = request.form.get('city')
        department = request.form.get('department')

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO technicians (name, email, phone, password, city, department)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, phone, hashed_pw, city, department))
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

        cursor.execute("SELECT city, department FROM admins WHERE admin_id = %s", (admin_id,))
        admin = cursor.fetchone()
        city = admin['city']
        department = admin['department']

        cursor.execute("""
            SELECT status, COUNT(*) AS count 
            FROM issues 
            WHERE city = %s AND category = %s 
            GROUP BY status
        """, (city, department))
        status_data = cursor.fetchall()

        cursor.execute("""
            SELECT category, COUNT(*) AS count 
            FROM issues 
            WHERE city = %s
            GROUP BY category
        """, (city,))
        category_data = cursor.fetchall()

        cursor.execute("""
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM issues
            WHERE city = %s
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) DESC
            LIMIT 10
        """, (city,))
        trend_data = cursor.fetchall()

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

        cursor.execute("SELECT city, department, name FROM admins WHERE admin_id = %s", (admin_id,))
        admin = cursor.fetchone()
        city, department, admin_name = admin['city'], admin['department'], admin['name']

        one_week_ago = datetime.now() - timedelta(days=7)
        two_weeks_ago = datetime.now() - timedelta(days=14)

        cursor.execute("""
            SELECT issue_id, title, status, category, severity,
                   TIMESTAMPDIFF(HOUR, created_at, updated_at) AS resolution_time,
                   created_at
            FROM issues
            WHERE city = %s AND category = %s AND created_at >= %s
        """, (city, department, one_week_ago))
        issues = cursor.fetchall()

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

        resolved_times = [i['resolution_time'] for i in issues if i['resolution_time']]
        avg_res_time = round(sum(resolved_times) / len(resolved_times), 2) if resolved_times else 0

        prev_resolved_times = [i['resolution_time'] for i in previous_week if i['resolution_time']]
        prev_avg_time = round(sum(prev_resolved_times) / len(prev_resolved_times), 2) if prev_resolved_times else 0

        resolution_trend = "improved" if avg_res_time < prev_avg_time else "slowed down"

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