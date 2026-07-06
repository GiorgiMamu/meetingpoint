from gevent import monkey
monkey.patch_all()

from dotenv import load_dotenv
load_dotenv()

import os
from app import create_app, socketio

config_name = os.environ.get('FLASK_ENV', 'development')
if config_name == 'production':
    app = create_app('production')
else:
    app = create_app('development')

if __name__ == '__main__':
    socketio.run(app, debug=(config_name != 'production'),
                 use_reloader=False, allow_unsafe_werkzeug=True)