# What is MeetingPoint?

When you arrive in a new city and know nobody but still want to participate in some activities, there should be an easy way to find like-minded people. This project aims to fill the gap for casual meet-ups or gatherings made by regular people like you. It will allow any user to browse or create events of any kind – be it a movie night, a hike, or even a trip if such a prospect arises. Anyone who’s interested and is able to use a browser may benefit from it. A website with this kind of idea at the core would be quite unique among similar apps, as others are mostly focused on big events hosted by larger organizations (especially for a fee), or only offer a mobile app. This project proposes MeetingPoint, a comprehensive web-based platform designed to support both event discovery and event management within a unified user experience.
# MeetingPoint

A social event discovery and management web platform built with Flask. Users can create, discover and join local events, chat with participants, follow other users and receive personalised recommendations.

## Features

- User registration with email verification and secure authentication
- Create, edit and manage events with location, photos and capacity settings
- Interactive map (Leaflet.js + OpenStreetMap) for event discovery
- Advanced filtering: category, mood tags, price, location radius, date range
- Real-time group chat per event (Flask-SocketIO)
- Follow/unfollow users, invite followers to events
- Participant approval workflow (automatic or manual)
- Email notifications: confirmations, approvals, 24-hour reminders
- In-app notification centre
- Host analytics dashboard with Matplotlib charts
- Personalised event recommendations (interest + history + location based)
- Admin panel: user management, event oversight, reports, audit logs
- User reporting system for inappropriate content

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, Flask 3.x |
| Database | SQLite (dev) / PostgreSQL (production) |
| ORM | Flask-SQLAlchemy + Flask-Migrate |
| Auth | Flask-Login, Flask-Bcrypt |
| Forms | Flask-WTF |
| Real-time | Flask-SocketIO |
| Email | Flask-Mail (Gmail SMTP) |
| Maps | Leaflet.js, OpenStreetMap, Nominatim |
| Analytics | Pandas, NumPy, Matplotlib |
| Testing | Pytest, pytest-flask |
| Rate limiting | Flask-Limiter |

## Setup (local development)

### Prerequisites

- Python 3.11 or higher
- Git

### Installation

```bash
git clone https://github.com/GiorgiMamu/meetingpoint.git
cd meetingpoint

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

- SECRET_KEY=
- MAIL_USERNAME=
- MAIL_PASSWORD=
- MAIL_DEFAULT_SENDER=
- ADMIN_EMAIL=
- ADMIN_PASSWORD=
- ADMIN_NAME=

For Gmail, generate an App Password at: Google Account → Security → 2-Step Verification → App passwords

### Database setup

```bash
flask --app run.py db upgrade
python seed.py   # creates the admin account
```

### Run

```bash
python run.py
```

App runs at `http://127.0.0.1:5000`

## Running tests

```bash
pytest tests/ -v -p no:warnings
```

Tests use an in-memory SQLite database and never touch the production database.

## Project structure
```text
meetingpoint/
├── app/
│   ├── __init__.py          # app factory, extensions
│   ├── models.py            # SQLAlchemy models
│   ├── routes.py            # all HTTP routes
│   ├── forms.py             # Flask-WTF forms
│   ├── utils.py             # helpers (email, geocoding, image processing)
│   ├── decorators.py        # custom route decorators
│   ├── socket_events.py     # SocketIO event handlers
│   ├── scheduler.py         # APScheduler background jobs
│   ├── analytics.py         # Pandas/NumPy/Matplotlib analytics
│   ├── recommendations.py   # recommendation engine
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS, JS, images
├── tests/                   # pytest test suite
├── migrations/              # Flask-Migrate migration files
├── config.py                # configuration classes
├── run.py                   # application entry point
├── seed.py                  # admin account seeder
├── locustfile.py            # load testing
├── requirements.txt
├── .env                     # secrets (never committed)
└── README.md
```