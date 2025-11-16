# EchoCircle - Municipal Issue Management System

A comprehensive web application for managing municipal issues with social media features, built with Flask and MySQL.

## Features

### 🏠 User Portal
- **Dashboard**: Interactive map showing community issues
- **Social Feed**: Community-driven issue sharing with likes and comments
- **Issue Reporting**: Report municipal problems with location and images
- **Issue Tracking**: Monitor status of reported issues
- **Upvoting System**: Support community issues

### 👨‍💼 Admin Portal
- **Issue Management**: Assign issues to technicians
- **Analytics Dashboard**: Performance metrics and leaderboards
- **Technician Management**: Add/remove technicians
- **Data Export**: CSV and PDF reports
- **Weekly AI Summaries**: Automated performance reports

### 🔧 Technician Portal
- **Task Dashboard**: View assigned issues on interactive map
- **Issue Updates**: Update status with comments and proof images
- **Performance Tracking**: Monitor resolution statistics

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: MySQL
- **Frontend**: HTML, CSS, JavaScript, Tailwind CSS
- **Maps**: Leaflet.js
- **AI**: Google Gemini API
- **Charts**: Chart.js

## Installation

1. **Clone Repository**
```bash
git clone https://github.com/vjn6805/EchoCircle---Smart-Civic-Issue-Management-Application
cd EchoCircle
```

2. **Install Dependencies**
```bash
pip install flask mysql-connector-python bcrypt werkzeug reportlab google-generativeai
```

3. **Database Setup**
```bash
mysql -u root -p
CREATE DATABASE echocircle;
USE echocircle;
```

Run the SQL schema from `create_feed_tables.sql` and your main database schema.

4. **Configuration**
Create `config.py`:
```python
SECRET_KEY = 'your-secret-key'
GEMINI_API_KEY = 'your-gemini-api-key'

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your-password',
    'database': 'echocircle'
}
```

5. **Run Application**
```bash
python app.py
```

## Project Structure

```
EchoCircle/
├── app.py                 # Main application
├── config.py              # Configuration
├── routes/                # Route handlers
│   ├── auth.py           # Authentication
│   ├── user.py           # User features
│   ├── admin.py          # Admin features
│   └── technician.py     # Technician features
├── utils/                # Utilities
│   ├── db_connection.py  # Database connection
│   └── geolocation.py    # Location services
├── templates/            # HTML templates
├── static/               # CSS, JS, images
└── uploads/              # User uploaded files
```

## Database Schema

### Core Tables
- `users` - User accounts
- `admins` - Admin accounts  
- `technicians` - Technician accounts
- `issues` - Reported issues
- `upvotes` - Issue upvoting system
- `issue_updates` - Status update logs

### Social Features
- `likes` - Post likes
- `comments` - Issue comments

## API Endpoints

### Authentication
- `GET /` - Landing page
- `POST /register` - User registration
- `POST /login_user` - User login
- `POST /login_admin` - Admin login
- `POST /login_technician` - Technician login

### User Routes
- `GET /user/dashboard` - User dashboard
- `GET /user/feed` - Social feed
- `POST /user/report` - Report issue
- `POST /upvote/<id>` - Upvote issue
- `POST /like_post/<id>` - Like post
- `POST /add_comment/<id>` - Add comment

### Admin Routes
- `GET /admin/dashboard` - Admin dashboard
- `GET /admin/analytics` - Analytics page
- `GET /admin/technicians` - Manage technicians
- `GET /admin/export` - Export data

### Technician Routes
- `GET /technician/dashboard` - Technician dashboard
- `POST /technician/update_issue/<id>` - Update issue status

## Features Overview

### Social Media Integration
- Community feed with posts from reported issues
- Like and comment system
- User avatars and timestamps
- Real-time interaction updates

### Analytics & Gamification
- Technician leaderboards
- Performance metrics
- Resolution time tracking
- AI-generated weekly summaries

### Geographic Features
- Interactive maps with issue markers
- Location-based issue filtering
- City-wise user segregation

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

## License

This project is licensed under the MIT License.

## Support

For support or questions, please create an issue in the repository.