from flask import render_template, request, redirect, session, url_for, flash, jsonify, send_from_directory
import os
from werkzeug.utils import secure_filename
from utils.db_connection import get_db_connection
from utils.geolocation import get_city_coordinates

def register_user_routes(app):
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory('uploads', filename)

    @app.route('/user/dashboard')
    def user_dashboard():
        if 'user_id' not in session:
            return redirect(url_for('login_user'))

        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT name, city FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        user_name = user['name'] if user else 'User'
        user_city = user['city'] if user else 'Ahmedabad'
        
        cursor.execute("SELECT Count(*) from issues where status='Resolved' and city = %s",(user_city,))
        total_resolved=cursor.fetchone()['Count(*)']

        lat, lon = get_city_coordinates(user_city)

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

        cursor.execute("SELECT name, city FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        user_name = user['name'] if user else 'User'
        user_city = user['city'] if user else 'Ahmedabad'

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
            cursor.execute("SELECT * FROM upvotes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
            if cursor.fetchone():
                return {'success': False, 'message': 'Already voted'}, 400
            
            cursor.execute("INSERT INTO upvotes (user_id, issue_id) VALUES (%s, %s)", (user_id, issue_id))
            cursor.execute("UPDATE issues SET upvotes = upvotes + 1 WHERE issue_id = %s", (issue_id,))
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

    @app.route('/like_post/<int:issue_id>', methods=['POST'])
    def like_post(issue_id):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not logged in'}), 401
        
        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM likes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
            existing_like = cursor.fetchone()
            
            if existing_like:
                cursor.execute("DELETE FROM likes WHERE user_id = %s AND issue_id = %s", (user_id, issue_id))
                action = 'unliked'
            else:
                cursor.execute("INSERT INTO likes (user_id, issue_id) VALUES (%s, %s)", (user_id, issue_id))
                action = 'liked'
            
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

    @app.route('/user/my_issues')
    def my_issues():
        if 'user_id' not in session:
            return redirect(url_for('login_user'))

        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
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
            if 'image' in request.files:
                image = request.files['image']
                if image.filename != '':
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