from dotenv import load_dotenv

load_dotenv()

from app import create_app, db
from app.models import User
import os

app = create_app('development')

with app.app_context():
    from app import bcrypt

    email = os.environ.get('ADMIN_EMAIL')
    password = os.environ.get('ADMIN_PASSWORD')
    name = os.environ.get('ADMIN_NAME', 'Admin')

    if not email or not password:
        print("ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env")
        exit(1)

    existing = User.query.filter_by(email=email).first()
    if existing:
        print(f"Admin user {email} already exists, skipping.")
    else:
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        admin = User(
            email=email,
            password_hash=hashed_pw,
            name=name,
            role='admin',
            is_active=True,
            is_blocked=False,
            is_profile_public=True,
            is_history_public=False,
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin user {email} created.")
