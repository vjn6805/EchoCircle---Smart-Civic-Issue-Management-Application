from flask import render_template, request, redirect, session, url_for, jsonify
import os
from werkzeug.utils import secure_filename
from utils.db_connection import get_db_connection

def register_technician_routes(app):
    @app.route('/technician/dashboard')
    def technician_dashboard():
        if 'technician_id' not in session:
            return redirect(url_for('login_technician'))

        technician_id = session['technician_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT name, city FROM technicians WHERE technician_id = %s", (technician_id,))
        tech = cursor.fetchone()
        if not tech:
            cursor.close()
            conn.close()
            return "Technician not found", 404

        technician_name = tech['name']
        city = tech['city']

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

        stats = {
            'pending': sum(1 for i in all_issues if i['status'] == 'Pending'),
            'in_progress': sum(1 for i in all_issues if i['status'] == 'In Progress'),
            'resolved': sum(1 for i in all_issues if i['status'] == 'Resolved')
        }

        latitudes = [float(i['latitude']) for i in all_issues if i['latitude']]
        longitudes = [float(i['longitude']) for i in all_issues if i['longitude']]
        lat = sum(latitudes) / len(latitudes) if latitudes else 23.0225
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

        cursor.execute("SELECT name FROM technicians WHERE technician_id = %s", (technician_id,))
        tech = cursor.fetchone()
        tech_name = tech['name'] if tech else 'Technician'

        cursor.execute("""
            UPDATE issues 
            SET status = %s, image_path = COALESCE(%s, image_path), updated_at = NOW()
            WHERE issue_id = %s AND technician_id = %s
        """, (status, image_path, issue_id, technician_id))

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
            SELECT issue_id, title, category, severity, status, created_at
            FROM issues
            WHERE technician_id = %s AND status = %s
            ORDER BY created_at DESC
        """, (technician_id, status))
        issues = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'issues': issues})