from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text)
    location = db.Column(db.String(150))
    interests = db.Column(db.Text)  # stored as JSON string
    profile_photo = db.Column(db.String(255))
    role = db.Column(db.String(20), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=True)
    is_profile_public = db.Column(db.Boolean, default=True)
    is_history_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    events = db.relationship('Event', backref='host', lazy=True,
                             foreign_keys='Event.host_id')
    participations = db.relationship('Participation', backref='user', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    messages = db.relationship('Message', backref='author', lazy=True)

    following = db.relationship('Follow', foreign_keys='Follow.follower_id',
                                backref='follower', lazy='dynamic')
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id',
                                backref='followed', lazy='dynamic')

    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.email}>'


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    host_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    event_time = db.Column(db.DateTime, nullable=False)
    location_text = db.Column(db.String(255))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    category = db.Column(db.String(50))
    mood_tags = db.Column(db.Text)  # stored as JSON string
    photo = db.Column(db.String(255))
    capacity_min = db.Column(db.Integer)
    capacity_max = db.Column(db.Integer)
    price = db.Column(db.Float, default=0.0)
    is_public = db.Column(db.Boolean, default=True)
    approval_mode = db.Column(db.String(20), default='automatic')
    participant_list_visible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participations = db.relationship('Participation', backref='event', lazy=True)
    messages = db.relationship('Message', backref='event', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='event', lazy=True)
    notifications = db.relationship('Notification', backref='related_event',
                                    lazy=True, foreign_keys='Notification.related_event_id')

    def __repr__(self):
        return f'<Event {self.title}>'


class Participation(db.Model):
    __tablename__ = 'participations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Participation user={self.user_id} event={self.event_id}>'


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message event={self.event_id} user={self.user_id}>'


class Bookmark(db.Model):
    __tablename__ = 'bookmarks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Bookmark user={self.user_id} event={self.event_id}>'


class Follow(db.Model):
    __tablename__ = 'follows'

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Follow {self.follower_id} -> {self.followed_id}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    related_event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification user={self.user_id} type={self.type}>'