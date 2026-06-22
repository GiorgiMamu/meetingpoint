from datetime import datetime

from flask_login import UserMixin

from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(UserMixin, db.Model):
    """Represents a registered user of MeetingPoint."""

    __tablename__ = 'users'
    __table_args__ = (
        db.Index('ix_users_role', 'role'),
    )
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text)
    location = db.Column(db.String(150))
    interests = db.Column(db.Text)  # stored as JSON string
    profile_photo = db.Column(db.String(255))
    role = db.Column(db.String(20), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    is_profile_public = db.Column(db.Boolean, default=True)
    is_history_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_reset_token = db.Column(db.String(255), nullable=True)

    events = db.relationship('Event', backref='host', lazy=True,
                             foreign_keys='Event.host_id',
                             cascade='all, delete-orphan')
    participations = db.relationship('Participation', backref='user', lazy=True,
                                     cascade='all, delete-orphan')
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True,
                                cascade='all, delete-orphan')
    notifications = db.relationship(
        'Notification',
        backref='user',
        lazy=True,
        foreign_keys='Notification.user_id',
        cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='author', lazy=True,
                               cascade='all, delete-orphan')

    following = db.relationship('Follow', foreign_keys='Follow.follower_id',
                                backref='follower', lazy='dynamic',
                                cascade='all, delete-orphan')
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id',
                                backref='followed', lazy='dynamic',
                                cascade='all, delete-orphan')

    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.email}>'


class Event(db.Model):
    """Represents an event created by a host user."""

    __tablename__ = 'events'
    __table_args__ = (
        db.Index('ix_events_host_id', 'host_id'),
        db.Index('ix_events_event_time', 'event_time'),
    )
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
    is_cancelled = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=False)
    currency = db.Column(db.String(10), default='GEL')
    approval_mode = db.Column(db.String(20), default='automatic')
    participant_list_visible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participations = db.relationship('Participation', backref='event', lazy=True,
                                     cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='event', lazy=True,
                               cascade='all, delete-orphan')
    bookmarks = db.relationship(
        'Bookmark',
        backref='event',
        lazy=True,
        cascade='all, delete-orphan',
        passive_deletes=True
    )
    notifications = db.relationship('Notification', backref='related_event',
                                    lazy=True, foreign_keys='Notification.related_event_id',
                                    cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.title}>'


class Participation(db.Model):
    """Tracks a user's participation in an event, including approval status."""

    __tablename__ = 'participations'
    __table_args__ = (
        db.Index('ix_participations_user_id', 'user_id'),
        db.Index('ix_participations_event_id', 'event_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey('events.id', ondelete='CASCADE'),
        nullable=False
    )
    status = db.Column(db.String(20), default='pending')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Participation user={self.user_id} event={self.event_id}>'


class Message(db.Model):
    """A chat message sent in an event's group chat."""

    __tablename__ = 'messages'
    __table_args__ = (
        db.Index('ix_messages_event_id', 'event_id'),
        db.Index('ix_messages_user_id', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message event={self.event_id} user={self.user_id}>'


class Bookmark(db.Model):
    """A saved/bookmarked event for a user."""

    __tablename__ = 'bookmarks'
    __table_args__ = (
        db.Index('ix_bookmarks_user_id', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Bookmark user={self.user_id} event={self.event_id}>'


class Follow(db.Model):
    """A follow relationship between two users."""

    __tablename__ = 'follows'
    __table_args__ = (
        db.Index('ix_follows_follower_id', 'follower_id'),
        db.Index('ix_follows_followed_id', 'followed_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Follow {self.follower_id} -> {self.followed_id}>'


class Notification(db.Model):
    """An in-app notification delivered to a user."""

    __tablename__ = 'notifications'
    __table_args__ = (
        db.Index('ix_notifications_user_id', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    related_event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    actor_user = db.relationship('User', foreign_keys=[actor_user_id], lazy='joined')

    def __repr__(self):
        return f'<Notification user={self.user_id} type={self.type}>'
