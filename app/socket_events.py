"""
socket_events.py — Flask-SocketIO event handlers for real-time chat.
"""
import logging
from datetime import datetime
from app.models import utcnow
from flask_login import current_user
from flask_socketio import join_room, leave_room, emit

logger = logging.getLogger(__name__)



def register_socket_events(socketio):
    """Register all SocketIO event handlers."""

    @socketio.on('join_chat')
    def handle_join(data):
        """User joins an event chat room."""
        from app.models import Event, Participation
        from flask_login import current_user

        event_id = data.get('event_id')
        if not event_id or not current_user.is_authenticated:
            return

        event = Event.query.get(event_id)
        if not event:
            return

        # Only host and approved participants can join chat
        is_host = event.host_id == current_user.id
        is_participant = Participation.query.filter_by(
            user_id=current_user.id,
            event_id=event_id,
            status='approved'
        ).first() is not None

        if not (is_host or is_participant):
            return

        room = f'event_{event_id}'
        join_room(room)
        logger.info(f'User {current_user.id} joined chat room {room}')

    @socketio.on('leave_chat')
    def handle_leave(data):
        """User leaves an event chat room."""
        event_id = data.get('event_id')
        if event_id:
            room = f'event_{event_id}'
            leave_room(room)

    @socketio.on('send_message')
    def handle_message(data):
        """Handle incoming chat message, save to DB, broadcast to room."""
        from app.models import Event, Participation, Message
        from app import db

        event_id = data.get('event_id')
        content = data.get('content', '').strip()

        if not event_id or not content or not current_user.is_authenticated:
            return

        if len(content) > 1000:
            content = content[:1000]

        event = Event.query.get(event_id)
        if not event:
            return

        is_host = event.host_id == current_user.id
        is_participant = Participation.query.filter_by(
            user_id=current_user.id,
            event_id=event_id,
            status='approved'
        ).first() is not None

        if not (is_host or is_participant):
            return

        msg = Message(
            event_id=event_id,
            user_id=current_user.id,
            content=content,
            timestamp=utcnow()
        )
        db.session.add(msg)
        db.session.commit()

        room = f'event_{event_id}'
        emit('new_message', {
            'id': msg.id,
            'content': content,
            'author_name': current_user.name,
            'author_id': current_user.id,
            'author_is_admin': current_user.is_admin(),
            'timestamp': msg.timestamp.isoformat(),
            'event_id': event_id
        }, room=room)

        logger.info(f'Message saved: event={event_id} user={current_user.id}')

    @socketio.on('delete_message')
    def handle_delete_message(data):
        """Host or message author can delete message."""
        from app.models import Event, Message
        from app import db

        msg_id = data.get('message_id')
        event_id = data.get('event_id')

        if not msg_id or not event_id or not current_user.is_authenticated:
            return

        msg = Message.query.get(msg_id)
        if not msg or msg.event_id != event_id:
            return

        event = Event.query.get(event_id)
        if not event:
            return

        is_host = event.host_id == current_user.id
        is_author = msg.user_id == current_user.id

        if is_host or is_author:
            db.session.delete(msg)
            db.session.commit()
            room = f'event_{event_id}'
            emit('message_deleted', {'message_id': msg_id}, room=room)
            logger.info(f'Message {msg_id} deleted by {current_user.id}')
